"""C5=B2_NO_ENT: derive header-only Entities from frozen C1; Sources byte-identical."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import phased_qa

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/2wiki/modal/c5-dev-s101-c4'
REFERENCE = ROOT / 'runs/2wiki/analysis/c1-context-dev401-s101'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def without_entity_rows(context):
    if context.count('-----Sources-----') != 1 or not context.startswith('\n-----Entities-----\n```csv\n'):
        raise ValueError('Unexpected C1 context structure; do not guess section boundaries.')
    header = io.StringIO()
    csv.writer(header).writerow(['entity', 'score', 'description'])
    sources = '-----Sources-----' + context.split('-----Sources-----', 1)[1]
    return '\n-----Entities-----\n```csv\n' + header.getvalue() + '\n```\n' + sources


def write_same_or_new(path, text):
    blob = text if isinstance(text, bytes) else text.encode('utf-8')
    if path.exists():
        if path.read_bytes() != blob:
            raise ValueError(f'Existing output differs; preserve and investigate: {path.name}')
    else:
        path.write_bytes(blob)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Derive CPU contexts only; no retrieval, embedding, LLM or judge calls.')
    args = parser.parse_args()
    a = argparse.Namespace(dataset_id='2wiki', index=ROOT / 'indexes/2wiki-modal-n2000-s13-dev20test80',
        questions=ROOT / 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/internal_dev.csv',
        registration=ROOT / 'docs/research/RUN_2WIKI_DEV20_TEST80.md',
        serving_config=ROOT / 'configs/research/2wiki/serving_modal.json', out=OUT, seed=101, llm_max_async=4)
    questions = phased_qa.read_questions(a.questions)
    contexts_path = REFERENCE / 'C1_s101/contexts.jsonl'
    contexts = phased_qa.read_jsonl(contexts_path)
    cache = REFERENCE / 'kw_s101.jsonl'
    keywords = phased_qa.read_jsonl(cache, key='query_id')
    expected = {q['query_id'] for q in questions}
    if len(questions) != 401 or set(contexts) != expected or set(keywords) != expected:
        raise ValueError('Complete C1 contexts and keyword cache for frozen dev401 are required.')
    answer_manifest = json.loads((REFERENCE / 'C1_s101/answer_manifest.json').read_text(encoding='utf-8'))
    if phased_qa.qa_run.file_hash(contexts_path) != answer_manifest['contexts_sha256']:
        raise ValueError('C1 measured contexts changed.')
    traces = [json.loads(line) for line in (REFERENCE / 'C1_s101/context.jsonl').read_text(encoding='utf-8').splitlines()]
    OUT.mkdir(parents=True, exist_ok=True)
    with phased_qa.qa_run.run_lock(OUT):
        phased_qa.ensure_run_identity(a)
        current = json.loads((OUT / 'run_manifest.json').read_text(encoding='utf-8'))
        reference = json.loads((REFERENCE / 'run_manifest.json').read_text(encoding='utf-8'))
        if {k: v for k, v in current.items() if k != 'source_sha256'} != {k: v for k, v in reference.items() if k != 'source_sha256'}:
            raise ValueError('C5 conditions differ outside documented source extension.')
        write_same_or_new(OUT / 'kw_s101.jsonl', cache.read_bytes())
        if (OUT / 'kw_s101.jsonl').read_bytes() != cache.read_bytes():
            raise ValueError('Keyword bytes differ.')
        phased_qa.ensure_phase_identity(OUT / 'source_amendment.json', {
            'reference_source_sha256': reference['source_sha256'], 'current_source_sha256': current['source_sha256'],
            'reason': 'DEV401-CTX-C5-001: add default-off header-only Entities flag/C5; derive from measured C1 contexts.',
            'reference_contexts_sha256': phased_qa.qa_run.file_hash(contexts_path),
            'generator_sha256': phased_qa.qa_run.file_hash(Path(__file__)),
            'keyword_sha256': phased_qa.qa_run.file_hash(cache)})
        print('Ready: C5=B2_NO_ENT, dev401, seed101; derive from C1 without retrieval or model calls.', flush=True)
        if not args.execute:
            print('To run: .\\.venv\\Scripts\\python.exe reproduce/research/run_c5_dev_contexts.py --execute')
            return 0
        from minirag.utils import encode_string_by_tiktoken
        derived, logs, checks = [], [], []
        for question in questions:
            qid = question['query_id']
            original = contexts[qid]
            if original['status'] != 'ok':
                raise ValueError('C1 early-exit requires explicit handling; cannot fabricate a derived context.')
            old = original['context']
            new = without_entity_rows(old)
            old_sources, new_sources = old.split('-----Sources-----', 1)[1], new.split('-----Sources-----', 1)[1]
            if old_sources.encode('utf-8') != new_sources.encode('utf-8'):
                raise ValueError('Sources changed.')
            matches = [t for t in traces if t['context_sha256'] == digest(old) and t['query'] == question['Question']]
            if not matches:
                raise ValueError('C1 context trace not found.')
            trace = matches[-1]
            header = new.split('```csv\n', 1)[1].split('```', 1)[0].removesuffix('\n')
            derived.append({'query_id': qid, 'status': 'ok', 'context': new, 'retrieval_s': None,
                            'derivation': 'C1 context with header-only Entities; no retrieval rerun'})
            logs.append(trace | {'context_sha256': digest(new), 'entities_tok': len(encode_string_by_tiktoken(header)),
                                 'retrieval_ms': None, 'bm25_ms': None, 'drop_entities': True,
                                 'derived_from_context_sha256': digest(old), 'source_retrieval_ms': trace['retrieval_ms']})
            checks.append({'query_id': qid, 'C1_sources_sha256': digest(old_sources),
                           'C5_sources_sha256': digest(new_sources), 'byte_identical': True})
        target = OUT / 'C5_s101'
        target.mkdir(exist_ok=True)
        for name, rows in [('contexts.jsonl', derived), ('context.jsonl', logs), ('sources_identity.jsonl', checks)]:
            write_same_or_new(target / name, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        phased_qa.ensure_phase_identity(target / 'context_manifest.json', {
            'config': phased_qa.config_env('C5'), 'keyword_cache_sha256': phased_qa.qa_run.file_hash(cache),
            'reference_contexts_sha256': phased_qa.qa_run.file_hash(contexts_path), 'derived_without_retrieval': True})
        phased_qa.qa_run.atomic_json(target / 'sources_identity_summary.json', {
            'n_expected': 401, 'n_verified': len(checks), 'all_sources_byte_identical': True,
            'contexts_sha256': phased_qa.qa_run.file_hash(target / 'contexts.jsonl'),
            'reference_contexts_sha256': phased_qa.qa_run.file_hash(contexts_path),
            'scope': 'Context derivation only; retrieval timing not remeasured. No QA or judge executed.'})
    print("contexts: {'ok': 401}; Sources byte-identical to C1: 401/401")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
