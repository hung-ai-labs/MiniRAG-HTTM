"""DeepSeek judge for the Table 1 ladder: every answer judged in 3 independent passes.

Same Step_2 rubric as the Gemini judge (judge_template, label parsing unchanged).
Body = {model: deepseek-flash, one user message, max_tokens 16, thinking disabled},
provider-default sampling, so the 3 passes are independent draws of the same prompt.
Blind: the judge sees question, gold and answer only; order is shuffled across arms.

Bookkeeping (append-only, resumable, safe under threads):
  <ledger>/calls.jsonl    one receipt per HTTP attempt (usage, cost, status)
  <split>/judgments_deepseek.jsonl   {id, prediction_sha256, judge_pass, verdict, raw}
Budget: the user lifted the earlier $1/800-request cap (11/11/2026, "deepseek 3 lượt và bỏ
giới hạn trần"). A runaway guard (approved_budget.json, max_usd) still stops the run.
"""
import json
import random
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from reproduce.graph_ablation.api import keys, judge_template
from reproduce.graph_ablation.study import ROOT, lines, append, write, read, sha
from reproduce.oracle_headroom.run import parse

MODEL = 'deepseek-flash'
URL = 'https://api.deepseek.com/chat/completions'
PRICE = {'input_miss_per_million': 0.30, 'input_hit_per_million': 0.006, 'output_per_million': 1.20}
LEDGER = ROOT / 'review/evidence_set_20261111/deepseek'
PASSES = (1, 2, 3)
GUARD = {'approved': True, 'max_usd': 15.0, 'local_date': '2026-11-11',
         'approval_quote': 'ok được rồi bắt đầu chạy đi, deepseek 3 lượt và bỏ giới hạn trần',
         'scope': 'evidence_set Table 1 ladder, Qwen2.5-3B and Phi-3.5-mini, 3 judge passes',
         'note': 'user lifted the cap; max_usd is only a runaway guard'}


def cost(usage):
    inp, out = usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0)
    hit = usage.get('prompt_cache_hit_tokens', 0)
    return ((inp - hit) * PRICE['input_miss_per_million'] + hit * PRICE['input_hit_per_million']
            + out * PRICE['output_per_million']) / 1e6


class Judge:
    def __init__(self):
        LEDGER.mkdir(parents=True, exist_ok=True)
        if not (LEDGER / 'approved_budget.json').exists():
            write(LEDGER / 'approved_budget.json', GUARD)
        self.budget = read(LEDGER / 'approved_budget.json')
        assert self.budget.get('approved')
        self.key = keys().get('DEEPSEEK_API_KEY', '')
        assert self.key, 'no DEEPSEEK_API_KEY in .env'
        self.lock = threading.Lock()
        self.spent = sum(r.get('cost_usd', 0.) for r in lines(LEDGER / 'calls.jsonl'))
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, prompt, tag):
        body = {'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 16,
                'thinking': {'type': 'disabled'}}
        data = json.dumps(body).encode()
        for attempt in range(1, 7):
            with self.lock:
                if self.spent >= self.budget['max_usd']:
                    raise SystemExit(f"DeepSeek runaway guard reached (${self.spent:.3f})")
            req = urllib.request.Request(URL, data=data, headers={'Authorization': 'Bearer ' + self.key,
                                                                  'Content-Type': 'application/json'})
            t0 = time.perf_counter()
            try:
                with self.opener.open(req, timeout=120) as r:
                    res = json.loads(r.read())
                text = res['choices'][0]['message']['content']
                c = cost(res['usage'])
                with self.lock:
                    self.spent += c
                    append(LEDGER / 'calls.jsonl', {'tag': tag, 'request_sha256': sha(data.decode()), 'attempt': attempt,
                                                    'ok': True, 'usage': res['usage'], 'cost_usd': c,
                                                    'model': res.get('model'), 'latency_s': time.perf_counter() - t0,
                                                    'finish_reason': res['choices'][0].get('finish_reason')})
                return text or '', res.get('model')
            except urllib.error.HTTPError as e:
                status = e.code
            except Exception as e:  # noqa: BLE001  transport errors: retried, never turned into a verdict
                status = type(e).__name__
            with self.lock:
                append(LEDGER / 'calls.jsonl', {'tag': tag, 'request_sha256': sha(data.decode()), 'attempt': attempt,
                                                'ok': False, 'status': status, 'cost_usd': 0.})
            if status in (400, 401, 402, 403, 422):
                raise SystemExit(f'DeepSeek HTTP {status}: not retryable')
            time.sleep(min(60, 5 * 2 ** attempt) + random.random())
        raise RuntimeError(f'DeepSeek failed 6 times for {tag}')


def judge_answers(answers, out_path, workers=32):
    """answers: iterable of dicts with id, question, gold, prediction, prediction_sha256."""
    unique = {}
    for a in answers:
        unique.setdefault((a['id'], a['prediction_sha256']), a)
    done = {(j['id'], j['prediction_sha256'], j['judge_pass']) for j in lines(out_path)}
    todo = [(k, p) for k in sorted(unique) for p in PASSES if (*k, p) not in done]
    random.Random(1309).shuffle(todo)  # blind, arm-agnostic order
    print(f'DeepSeek judge: {len(unique)} unique answers x {len(PASSES)} passes, {len(todo)} calls to make', flush=True)
    if not todo:
        return
    judge, template, wlock = Judge(), judge_template(), threading.Lock()

    def one(item):
        (i, h), p = item
        a = unique[i, h]
        raw, model = judge.call(template.format(question=a['question'], gold=a['gold'], pred=a['prediction']),
                                f'{out_path.parent.name}|{i}|{h[:12]}|{p}')
        with wlock:
            append(out_path, {'id': i, 'prediction_sha256': h, 'judge_pass': p, 'verdict': parse(raw),
                              'raw': raw[:64], 'judge_model': model or MODEL})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, t) for t in todo]
        for n, f in enumerate(as_completed(futs), 1):
            f.result()
            if n % 500 == 0 or n == len(futs):
                print(f'judged {n}/{len(futs)}  spent ${judge.spent:.3f}', flush=True)
