"""RAGAS wired to the same Gemini key pool and local embedder MiniRAG uses.

RAGAS would otherwise call Gemini directly, bypassing the multi-key pool and the
token-bucket limiter -- which is the whole reason indexing survives the free
tier. Both wrappers below delegate to those, so a RAGAS run is rate-limited and
key-rotated exactly like the rest of the pipeline.
"""

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

from langchain_core.outputs import Generation, LLMResult  # noqa: E402
from ragas.embeddings.base import BaseRagasEmbeddings  # noqa: E402
from ragas.llms.base import BaseRagasLLM  # noqa: E402

from minirag.llm.gemini import gemini_complete_if_cache  # noqa: E402

LOCAL_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class GeminiPoolLLM(BaseRagasLLM):
    """RAGAS LLM backed by minirag.llm.gemini (key pool + token bucket)."""

    def __init__(self, model: str = "gemini-flash-lite-latest"):
        super().__init__()
        self.model = model

    async def agenerate_text(
        self, prompt, n=1, temperature=0.01, stop=None, callbacks=None
    ) -> LLMResult:
        text = prompt.to_string()
        outs = []
        for _ in range(max(n, 1)):
            out = await gemini_complete_if_cache(
                self.model, text, temperature=temperature
            )
            outs.append(Generation(text=out or ""))
        return LLMResult(generations=[outs])

    def generate_text(
        self, prompt, n=1, temperature=0.01, stop=None, callbacks=None
    ) -> LLMResult:
        return asyncio.get_event_loop().run_until_complete(
            self.agenerate_text(prompt, n, temperature, stop, callbacks)
        )

    def is_finished(self, response: LLMResult) -> bool:
        return True


class LocalEmbeddings(BaseRagasEmbeddings):
    """all-MiniLM-L6-v2 on this machine -- answer relevancy costs no quota."""

    def __init__(self, model_name: str = LOCAL_EMBED_MODEL):
        super().__init__()
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed_query(self, text: str):
        return self._model.encode([text], normalize_embeddings=True)[0].tolist()

    def embed_documents(self, texts):
        return self._model.encode(list(texts), normalize_embeddings=True).tolist()

    async def aembed_query(self, text: str):
        return self.embed_query(text)

    async def aembed_documents(self, texts):
        return self.embed_documents(texts)
