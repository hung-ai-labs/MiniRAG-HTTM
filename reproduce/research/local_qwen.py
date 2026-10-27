"""Strict loopback-only Qwen/Ollama adapter and logged local serving smoke.

Uses the already-installed GGUF Q4_K_M model. No .env, external API, cloud
fallback, model download, or default MiniRAG backend changes.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
import uuid

MODEL = 'qwen2.5:3b'
PINNED_MODEL_DIGEST = '357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b'
OPTIONS = {'num_ctx': 32768, 'temperature': .7, 'top_p': .8, 'top_k': 20,
           'repeat_penalty': 1.05, 'seed': 101}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, obj):
    path.write_bytes((json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'))


def append(path, obj):
    import os
    with path.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Local inference must not follow redirects')


class LocalQwen:
    def __init__(self, out, base='http://127.0.0.1:11434', timeout=180):
        parsed = urlparse(base)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != 11434 or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Only http://127.0.0.1:11434 is accepted')
        self.base, self.timeout, self.out = base, timeout, Path(out)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.semaphore = asyncio.Semaphore(1)

    def request(self, endpoint, payload=None):
        if endpoint not in ('/api/version', '/api/tags', '/api/show', '/api/chat', '/api/ps'):
            raise ValueError('Unexpected local endpoint')
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.base+endpoint, data=data, headers={'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=self.timeout) as response:
            return json.loads(response.read())

    def inspect(self):
        version = self.request('/api/version')
        tags = self.request('/api/tags')
        model = next((m for m in tags['models'] if m['name'] == MODEL), None)
        if model is None or model['digest'] != PINNED_MODEL_DIGEST:
            raise ValueError('Cached Qwen model is missing or its digest changed')
        info = self.request('/api/show', {'model': MODEL})
        if info['details']['quantization_level'] != 'Q4_K_M' or info['model_info'].get('general.finetune') != 'Instruct':
            raise ValueError('Unexpected model quantization or non-Instruct model')
        return {'version': version, 'tag': model, 'show': info,
                'condition': 'local_qwen2.5_3b_instruct_q4_k_m_not_modal_bf16',
                'hf_revision_verified': False, 'options': OPTIONS, 'client_concurrency': 1}

    def chat(self, messages, *, phase, max_tokens, keep_alive=0, query_id=None):
        request_id = str(uuid.uuid4())
        payload = {'model': MODEL, 'messages': messages, 'stream': False,
                   'keep_alive': keep_alive, 'options': {**OPTIONS, 'num_predict': max_tokens}}
        started = time.perf_counter()
        record = {'at': now(), 'request_id': request_id, 'query_id': query_id, 'phase': phase,
                  'request': payload, 'attempt': 1, 'model_digest': PINNED_MODEL_DIGEST}
        record['chunk_id'] = getattr(self, 'chunk_id', None)
        record['doc_id'] = getattr(self, 'doc_id', None)
        try:
            raw = self.request('/api/chat', payload)
            record['response'] = raw
            if raw.get('model') != MODEL or raw.get('done') is not True:
                raise ValueError('Unexpected/incomplete local model response')
            record['status'] = 'ok'
            return raw
        except Exception as exc:
            record['status'] = 'failed'
            record['error_type'] = type(exc).__name__
            raise
        finally:
            record['latency_s'] = time.perf_counter()-started
            append(self.out / 'requests.jsonl', record)

    async def complete(self, prompt, system_prompt=None, history_messages=None, **kwargs):
        phase = getattr(self, 'phase', 'answer')
        if phase == 'index':
            phase = 'glean' if history_messages else 'extract'
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.extend(history_messages or [])
        messages.append({'role': 'user', 'content': prompt})
        cap = 4096 if phase in ('extract', 'glean') else 1024
        async with self.semaphore:
            raw = await asyncio.to_thread(self.chat, messages, phase=phase, max_tokens=cap,
                                          keep_alive='30s', query_id=getattr(self, 'query_id', None))
        return raw['message']['content']

    def unload(self):
        # Documented native unload request; does not remove model files.
        return self.request('/api/chat', {'model': MODEL, 'messages': [], 'stream': False, 'keep_alive': 0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output exists; use a new run directory')
    args.out.mkdir(parents=True)
    client = LocalQwen(args.out)
    report = {'status': 'running', 'started_at': now(), 'purpose': 'local_serving_smoke_not_a_benchmark',
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write_json(args.out / 'run_manifest.json', report)
    try:
        metadata = client.inspect()
        write_json(args.out / 'runtime.json', metadata)
        raw = client.chat([{'role': 'user', 'content': 'Reply with exactly LOCAL_OK and nothing else.'}],
                          phase='runtime_smoke', max_tokens=16, keep_alive='30s')
        loaded = client.request('/api/ps')
        write_json(args.out / 'loaded_models.json', loaded)
        report['answer'] = raw['message']['content']
        report['prompt_tokens'] = raw.get('prompt_eval_count')
        report['completion_tokens'] = raw.get('eval_count')
        report['status'] = 'passed' if raw['message']['content'].strip() == 'LOCAL_OK' else 'unexpected_answer'
        report['loaded_models'] = [{k: m.get(k) for k in ('name', 'size', 'size_vram', 'context_length')}
                                   for m in loaded.get('models', [])]
    except Exception as exc:
        report['status'] = 'failed'
        report['error_type'] = type(exc).__name__
        raise
    finally:
        try:
            client.unload()
            report['unloaded_after_smoke'] = True
        except Exception:
            report['unloaded_after_smoke'] = False
        report['finished_at'] = now()
        write_json(args.out / 'run_manifest.json', report)
    print(json.dumps(report, ensure_ascii=False))
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
