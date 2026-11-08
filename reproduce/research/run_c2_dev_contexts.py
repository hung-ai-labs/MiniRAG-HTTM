"""Prepare/run CPU-only C2 (B2_NO_BM25) contexts for frozen dev401, seed101."""
import argparse
import json
import os
import shutil
from pathlib import Path

import phased_qa

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/2wiki/modal/c2-dev-s101-c4'
REFERENCE = ROOT / 'runs/2wiki/analysis/c1-context-dev401-s101'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Run CPU retrieval only; never keywords, answers or judge.')
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    a = argparse.Namespace(dataset_id='2wiki', index=ROOT / 'indexes/2wiki-modal-n2000-s13-dev20test80',
        questions=ROOT / 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/internal_dev.csv',
        registration=ROOT / 'docs/research/RUN_2WIKI_DEV20_TEST80.md',
        serving_config=ROOT / 'configs/research/2wiki/serving_modal.json', out=OUT,
        seed=101, llm_max_async=4)
    questions = phased_qa.read_questions(a.questions)
    cache = REFERENCE / 'kw_s101.jsonl'
    keywords = phased_qa.read_jsonl(cache, key='query_id')
    if len(questions) != 401 or set(keywords) != {r['query_id'] for r in questions}:
        raise ValueError('Complete dev401 keyword cache required; do not generate missing keywords.')
    config0 = phased_qa.config_env('C1')
    config1 = phased_qa.config_env('C2')
    if {k for k in config0 if config0[k] != config1[k]} != {'MINIRAG_CHUNK_FUSION'}:
        raise ValueError('C1/C2 differ outside the registered fusion ablation.')
    OUT.mkdir(parents=True, exist_ok=True)
    with phased_qa.qa_run.run_lock(OUT):
        phased_qa.ensure_run_identity(a)
        current = json.loads((OUT / 'run_manifest.json').read_text(encoding='utf-8'))
        reference = json.loads((REFERENCE / 'run_manifest.json').read_text(encoding='utf-8'))
        if current != reference:
            raise ValueError('C2 conditions differ from measured C1; investigate before retrieval.')
        target = OUT / 'kw_s101.jsonl'
        if target.exists():
            if target.read_bytes() != cache.read_bytes():
                raise ValueError('Existing C2 keyword cache differs; preserve it and investigate.')
        else:
            shutil.copyfile(cache, target)
        phased_qa.qa_run.atomic_json(OUT / 'imported_keywords.json', {
            'source': str(cache.relative_to(ROOT)), 'sha256': phased_qa.qa_run.file_hash(cache),
            'n': len(keywords), 'reference': 'C1/B2_FULL', 'config': 'C2/B2_NO_BM25',
            'scope': 'CPU contexts only; no keyword/answer/judge requests'})
    print('Ready: C2/B2_NO_BM25, dev401, seed101, cached keywords, offline embedding, one CPU worker.', flush=True)
    if not args.execute:
        print('To run: .\\.venv\\Scripts\\python.exe reproduce/research/run_c2_dev_contexts.py --execute')
        return 0
    return phased_qa.main(['contexts', '--config', 'C2', '--dataset-id', '2wiki',
        '--index', str(a.index), '--questions', str(a.questions), '--registration', str(a.registration),
        '--serving-config', str(a.serving_config), '--out', str(OUT), '--seed', '101',
        '--llm-max-async', '4', '--workers', '1'])


if __name__ == '__main__':
    raise SystemExit(main())
