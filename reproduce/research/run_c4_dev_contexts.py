"""Prepare/run C4=B2_NO_VECTOR (BM25 Sources) on frozen dev401; no inference."""
import argparse
import json
import os
import shutil
from pathlib import Path

import phased_qa

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/2wiki/modal/c4-dev-s101-c4'
REFERENCE = ROOT / 'runs/2wiki/analysis/c1-context-dev401-s101'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='CPU contexts only, with forbidden LLM and existing keyword cache.')
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    a = argparse.Namespace(dataset_id='2wiki', index=ROOT / 'indexes/2wiki-modal-n2000-s13-dev20test80',
        questions=ROOT / 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/internal_dev.csv',
        registration=ROOT / 'docs/research/RUN_2WIKI_DEV20_TEST80.md',
        serving_config=ROOT / 'configs/research/2wiki/serving_modal.json', out=OUT,
        seed=101, llm_max_async=4)
    rows = phased_qa.read_questions(a.questions)
    cache = REFERENCE / 'kw_s101.jsonl'
    keywords = phased_qa.read_jsonl(cache, key='query_id')
    if len(rows) != 401 or set(keywords) != {r['query_id'] for r in rows}:
        raise ValueError('Complete dev401 keyword cache required; no missing keywords will be generated.')
    c1, c4 = phased_qa.config_env('C1'), phased_qa.config_env('C4')
    if {k for k in c1 if c1[k] != c4[k]} != {'MINIRAG_CHUNK_FUSION'} or c4['MINIRAG_CHUNK_FUSION'] != 'bm25':
        raise ValueError('C4 must differ from C1 only in the Sources fusion switch.')
    OUT.mkdir(parents=True, exist_ok=True)
    with phased_qa.qa_run.run_lock(OUT):
        phased_qa.ensure_run_identity(a)
        current = json.loads((OUT / 'run_manifest.json').read_text(encoding='utf-8'))
        reference = json.loads((REFERENCE / 'run_manifest.json').read_text(encoding='utf-8'))
        if {k: v for k, v in current.items() if k != 'source_sha256'} != {k: v for k, v in reference.items() if k != 'source_sha256'}:
            raise ValueError('C4 conditions changed outside the documented source extension; investigate.')
        # Preserve old run/source identities. The new source revision adds only
        # a bm25 Sources branch and C4 mapping; it must not rewrite C1 metadata.
        target = OUT / 'kw_s101.jsonl'
        if target.exists():
            if target.read_bytes() != cache.read_bytes():
                raise ValueError('Existing C4 cache differs; preserve it and investigate.')
        else:
            shutil.copyfile(cache, target)
        phased_qa.qa_run.atomic_json(OUT / 'source_amendment.json', {
            'reference_source_sha256': reference['source_sha256'],
            'current_source_sha256': current['source_sha256'],
            'reason': 'DEV401-CTX-C4-001: add bm25-only Sources branch and explicit C4 mini mapping; no model/index changes.',
            'reference': str(REFERENCE.relative_to(ROOT)), 'keyword_sha256': phased_qa.qa_run.file_hash(cache),
            'extension_files': {str(p.relative_to(ROOT)): phased_qa.qa_run.file_hash(p) for p in
                                [ROOT / 'minirag/operate.py', ROOT / 'reproduce/research/phased_qa.py', Path(__file__)]},
            'pending_real_control': 'After retrieval compare C4 Entities, graph/vector candidates to measured C1; fixture tests do not replace this.'})
    print('Ready: C4=B2_NO_VECTOR, BM25 Sources, dev401, seed101, cached keywords, offline embedding, one CPU worker.', flush=True)
    if not args.execute:
        print('To run: .\\.venv\\Scripts\\python.exe reproduce/research/run_c4_dev_contexts.py --execute')
        return 0
    return phased_qa.main(['contexts', '--config', 'C4', '--dataset-id', '2wiki',
        '--index', str(a.index), '--questions', str(a.questions), '--registration', str(a.registration),
        '--serving-config', str(a.serving_config), '--out', str(OUT), '--seed', '101',
        '--llm-max-async', '4', '--workers', '1'])


if __name__ == '__main__':
    raise SystemExit(main())
