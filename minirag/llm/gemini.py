"""
Google Gemini LLM Interface Module
==================================

Talks to Gemini through its OpenAI-compatible endpoint, so it reuses the same
AsyncOpenAI client as `minirag.llm.openai` and needs no extra SDK.

Environment:
    GEMINI_API_KEY (or GOOGLE_API_KEY) - required
    GEMINI_API_BASE                    - optional, defaults to the public endpoint

Usage:
    from minirag.llm.gemini import gemini_complete, gemini_embed
"""

__version__ = "1.0.0"

import asyncio
import os
import re
import time

import numpy as np
import pipmaster as pm

if not pm.is_installed("openai"):
    pm.install("openai")

from openai import (
    AsyncOpenAI,
    APIConnectionError,
    RateLimitError,
    APITimeoutError,
    InternalServerError,
    AuthenticationError,
    PermissionDeniedError,
)
from tenacity import (
    retry,
    stop_after_delay,
    wait_exponential,
    retry_if_exception_type,
)

from minirag.utils import (
    wrap_embedding_func_with_attrs,
    locate_json_string_body_from_string,
    safe_unicode_decode,
    logger,
)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-flash-lite-latest"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIM = 3072


class _KeyPool:
    """Round-robin pool of API keys, rate-limited by tokens as well as requests.

    Measured on the free tier (Feb 2026): each key allows ~15 requests/minute
    AND ~18k tokens/minute, metered per project, so N keys give N times that.
    Token/minute is the binding constraint for MiniRAG: its entity-extraction
    template alone is ~2.5k tokens, so counting requests only lets a run blow
    the token budget and collect 429s at ~40% of all calls.

    Each key carries two leaky buckets. A request takes the key that can pay for
    it soonest; a 429 parks that key for `cooldown` seconds so the pool routes
    around it. Tune with GEMINI_RPM / GEMINI_TPM (and the EMBED variants).
    """

    def __init__(self, keys, rpm: int, tpm: int, cooldown: float = 60.0,
                 burst: float = 0.25):
        self.keys = list(keys)
        self.rpm = max(rpm, 1)
        self.tpm = max(tpm, 1)
        self.cooldown = cooldown
        # Buckets refill at rpm/tpm per minute but never bank a full minute of
        # credit: a full bucket would release a whole minute's quota in one
        # instant burst, which is exactly what the upstream window rejects.
        self.burst_req = max(1.0, self.rpm * burst)
        self.burst_tok = max(1.0, self.tpm * burst)
        now = time.monotonic()
        # key -> [available requests, available tokens, last refill, parked until]
        self._state = {
            k: [self.burst_req, self.burst_tok, now, 0.0] for k in self.keys
        }
        self._strikes = {k: 0 for k in self.keys}
        self._lock = asyncio.Lock()

    def _refill(self, key, now):
        st = self._state[key]
        elapsed = now - st[2]
        if elapsed > 0:
            st[0] = min(self.burst_req, st[0] + self.rpm * elapsed / 60.0)
            st[1] = min(self.burst_tok, st[1] + self.tpm * elapsed / 60.0)
            st[2] = now
        return st

    def _ready_at(self, key, cost, now):
        """When this key could pay for `cost` tokens and one request."""
        st = self._refill(key, now)
        need_req = max(0.0, 1.0 - st[0]) * 60.0 / self.rpm
        need_tok = max(0.0, cost - st[1]) * 60.0 / self.tpm
        return max(st[3], now + need_req, now + need_tok)

    async def acquire(self, cost: int = 1) -> str:
        cost = max(1, min(cost, int(self.burst_tok)))  # a single oversized call still has to go
        async with self._lock:
            now = time.monotonic()
            key = min(self.keys, key=lambda k: self._ready_at(k, cost, now))
            wait = self._ready_at(key, cost, now) - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            st = self._refill(key, now)
            st[0] -= 1
            st[1] -= cost
            if os.environ.get("GEMINI_DEBUG_POOL"):
                logger.warning(
                    "POOL kind=%s cost=%d waited=%.1fs keys=%d",
                    getattr(self, "kind", "?"), cost, max(0.0, wait), len(self.keys),
                )
            return key

    def penalize(self, key: str):
        """Called on 429: park this key, backing off further each time in a row.

        A per-minute 429 clears in a minute, but a per-DAY quota 429 looks
        identical and never clears. A flat cooldown keeps re-picking exhausted
        keys and starves the ones still alive, so double the park on each
        consecutive strike (60s -> 2m -> 4m ... capped at an hour).
        """
        if key in self._state:
            self._strikes[key] = min(self._strikes[key] + 1, 6)
            park = min(self.cooldown * 2 ** (self._strikes[key] - 1), 3600.0)
            self._state[key][3] = max(self._state[key][3], time.monotonic() + park)

    def succeeded(self, key: str):
        """Called on a successful response: the key is healthy again."""
        if key in self._strikes:
            self._strikes[key] = 0

    def disable(self, key: str):  # noqa: D401
        """Called on 401/403: drop a dead key for good, unless it is the last one."""
        if key in self._state and len(self.keys) > 1:
            self.keys.remove(key)
            del self._state[key]
            self._strikes.pop(key, None)
            logger.warning(
                "Gemini key rejected (auth/permission); %d key(s) left in pool",
                len(self.keys),
            )


_encoder = None


def _estimate_tokens(text: str) -> int:
    """Rough token count for budgeting; tiktoken is close enough for Gemini here."""
    global _encoder
    if _encoder is None:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
    return len(_encoder.encode(text))


_NUMBERED_KEY_RE = re.compile(r"^GEMINI_API_KEY_(\d+)$")


def _resolve_api_keys(api_key: str = None):
    """Collect every configured key, in priority order.

    Accepts an explicit `api_key`, a comma-separated GEMINI_API_KEYS, numbered
    GEMINI_API_KEY_1..N vars, and the plain GEMINI_API_KEY / GOOGLE_API_KEY.
    """
    if api_key:
        return [api_key]

    # When the client is pointed at something that is not Gemini -- a local
    # Ollama, or vLLM on a rented GPU -- exactly one key is valid and the rest
    # of the pool is worse than useless: every rotation onto a Gemini key comes
    # back as an auth failure and evicts it, so throughput collapses while the
    # real cause looks like a permissions problem.
    only = os.environ.get("GEMINI_API_KEY_ONLY", "").strip()
    if only:
        return [only]

    keys = []
    raw = os.environ.get("GEMINI_API_KEYS", "")
    keys += [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]

    numbered = []
    for name, value in os.environ.items():
        m = _NUMBERED_KEY_RE.match(name)
        if m and value.strip():
            numbered.append((int(m.group(1)), value.strip()))
    keys += [v for _, v in sorted(numbered)]

    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            keys.append(value)

    # preserve order, drop duplicates
    seen = set()
    keys = [k for k in keys if not (k in seen or seen.add(k))]

    if not keys:
        raise ValueError(
            "No Gemini API key found. Set GEMINI_API_KEYS (comma separated), "
            "GEMINI_API_KEY_1..N, or GEMINI_API_KEY."
        )
    return keys


_pools = {}


def _get_pool(kind: str = "chat", api_key: str = None) -> _KeyPool:
    # One pool for chat AND embeddings: the free tier meters them against the
    # same per-project budget, so separate pools quietly spend it twice and the
    # run sits at a permanent ~30% 429 floor.
    if "all" not in _pools:
        rpm = int(os.environ.get("GEMINI_RPM", "13"))
        # Swept on the real pipeline (5 min per setting): 5000 -> 17 ok/min at
        # 16% 429, 3000 -> 26 ok/min at 4%, 2000 -> 22 at 12%, 1200 -> 16 at 21%.
        # Throttling tighter than the ceiling finishes faster, because time lost
        # to backoff after a 429 costs more than the requests it holds back.
        tpm = int(os.environ.get("GEMINI_TPM", "3000"))
        _pools["all"] = _KeyPool(_resolve_api_keys(api_key), rpm, tpm)
        _pools["all"].kind = "all"
    return _pools["all"]


_clients = {}


def _client(key: str, base_url: str = None) -> AsyncOpenAI:
    # One client per (key, base_url) so httpx connection pools are reused across
    # the thousands of requests an indexing run makes.
    url = base_url or os.environ.get("GEMINI_API_BASE", GEMINI_BASE_URL)
    if (key, url) not in _clients:
        # max_retries=0: the SDK's own retries would fire extra HTTP requests
        # behind the key pool's back and blow the rate budget. Retrying is the
        # pool's job, so every HTTP request passes the limiter exactly once.
        _clients[(key, url)] = AsyncOpenAI(api_key=key, base_url=url, max_retries=0)
    return _clients[(key, url)]


@retry(
    # Keep retrying rather than giving up: MiniRAG has no checkpoint inside a
    # document, so one exhausted call throws away the whole document's work and
    # the run livelocks, redoing and re-failing the same document forever.
    stop=stop_after_delay(1800),
    wait=wait_exponential(multiplier=2, min=5, max=90),
    retry=retry_if_exception_type(
        (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            # retried so the pool can fail over to another key after evicting a dead one
            AuthenticationError,
            PermissionDeniedError,
        )
    ),
)
async def gemini_complete_if_cache(
    model=DEFAULT_MODEL,
    prompt=None,
    system_prompt=None,
    history_messages=[],
    base_url=None,
    api_key=None,
    **kwargs,
) -> str:
    kwargs.pop("hashing_kv", None)
    kwargs.pop("keyword_extraction", None)
    kwargs.pop("response_format", None)  # not supported the same way on the compat API
    kwargs.pop("mode", None)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    pool = _get_pool("chat", api_key)
    cost = _estimate_tokens("".join(m["content"] for m in messages)) + 1000
    key = await pool.acquire(cost)

    logger.debug("===== Query Input to Gemini =====")
    logger.debug(f"Model: {model}")
    logger.debug(f"Query: {prompt}")

    try:
        response = await _client(key, base_url).chat.completions.create(
            model=model, messages=messages, **kwargs
        )
    except RateLimitError:
        pool.penalize(key)
        raise
    except (AuthenticationError, PermissionDeniedError):
        pool.disable(key)
        raise
    pool.succeeded(key)

    if not response or not getattr(response, "choices", None):
        logger.error("No valid choices returned. Full response: %s", response)
        return ""

    content = response.choices[0].message.content
    if content is None:
        logger.error("The message content is None. Full response: %s", response)
        return ""
    if r"\u" in content:
        content = safe_unicode_decode(content.encode("utf-8"))
    return content


async def gemini_complete(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
) -> str:
    """Generic entry point: model name comes from MiniRAG's `llm_model_name`."""
    keyword_extraction = kwargs.pop("keyword_extraction", keyword_extraction)
    hashing_kv = kwargs.get("hashing_kv", None)
    model_name = DEFAULT_MODEL
    if hashing_kv is not None:
        model_name = hashing_kv.global_config.get("llm_model_name", DEFAULT_MODEL)

    result = await gemini_complete_if_cache(
        model_name,
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )
    if keyword_extraction:
        return locate_json_string_body_from_string(result)
    return result


async def gemini_flash_lite_complete(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
) -> str:
    keyword_extraction = kwargs.pop("keyword_extraction", keyword_extraction)
    result = await gemini_complete_if_cache(
        "gemini-flash-lite-latest",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )
    if keyword_extraction:
        return locate_json_string_body_from_string(result)
    return result


async def gemini_flash_complete(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
) -> str:
    keyword_extraction = kwargs.pop("keyword_extraction", keyword_extraction)
    result = await gemini_complete_if_cache(
        "gemini-3.6-flash",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )
    if keyword_extraction:
        return locate_json_string_body_from_string(result)
    return result


@wrap_embedding_func_with_attrs(
    embedding_dim=DEFAULT_EMBEDDING_DIM, max_token_size=2048
)
@retry(
    # Keep retrying rather than giving up: MiniRAG has no checkpoint inside a
    # document, so one exhausted call throws away the whole document's work and
    # the run livelocks, redoing and re-failing the same document forever.
    stop=stop_after_delay(1800),
    wait=wait_exponential(multiplier=2, min=5, max=90),
    retry=retry_if_exception_type(
        (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            # retried so the pool can fail over to another key after evicting a dead one
            AuthenticationError,
            PermissionDeniedError,
        )
    ),
)
async def gemini_embed(
    texts: list[str],
    model: str = DEFAULT_EMBEDDING_MODEL,
    base_url: str = None,
    api_key: str = None,
) -> np.ndarray:
    pool = _get_pool("embed", api_key)
    key = await pool.acquire(_estimate_tokens("".join(texts)))
    try:
        response = await _client(key, base_url).embeddings.create(
            model=model, input=texts
        )
    except RateLimitError:
        pool.penalize(key)
        raise
    except (AuthenticationError, PermissionDeniedError):
        pool.disable(key)
        raise
    pool.succeeded(key)
    return np.array([dp.embedding for dp in response.data])
