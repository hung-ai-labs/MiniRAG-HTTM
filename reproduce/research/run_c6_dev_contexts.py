"""C6=HYBRID_NO_GRAPH: CPU dense+BM25 contexts on frozen dev401; no keyword cache."""
import argparse
import json
import os
from pathlib import Path

import phased_qa

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/2wiki/modal/c6-dev-s101-c4'
REFERENCE = ROOT / 'runs/2wiki/analysis/c1-context-dev401-s101'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Run local retrieval only; no keywords, answers or judge.')
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    a = argparse.Namespace(dataset_id='2wiki', index=ROOT / 'indexes/2wiki-modal-n2000-s13-dev20test80',
        questions=ROOT / 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/internal_dev.csv',
        registration=ROOT / 'docs/research/RUN_2WIKI_DEV20_TEST80.md',
        serving_config=ROOT / 'configs/research/2wiki/serving_modal.json', out=OUT, seed=101, llm_max_async=4)
    if len(phased_qa.read_questions(a.questions)) != 401 or phased_qa.requires_keywords('C6'):
        raise ValueError('C6 must use dev401 without keyword parsing.')
    if phased_qa.config_env('C6') != phased_qa.config_env('C1') | {'MINIRAG_NO_GRAPH': '1'}:
        raise ValueError('Unexpected C6 configuration.')
    OUT.mkdir(parents=True, exist_ok=True)
    with phased_qa.qa_run.run_lock(OUT):
        phased_qa.ensure_run_identity(a)
        current = json.loads((OUT / 'run_manifest.json').read_text(encoding='utf-8'))
        reference = json.loads((REFERENCE / 'run_manifest.json').read_text(encoding='utf-8'))
        if {k: v for k, v in current.items() if k != 'source_sha256'} != {k: v for k, v in reference.items() if k != 'source_sha256'}:
            raise ValueError('Conditions outside documented source extension differ from C1.')
        phased_qa.ensure_phase_identity(OUT / 'source_amendment.json', {
            'reference_source_sha256': reference['source_sha256'], 'current_source_sha256': current['source_sha256'],
            'reason': 'DEV401-CTX-C6-001: direct original-query vector+BM25, no parser/graph operations.',
            'reference': str(REFERENCE.relative_to(ROOT)), 'keyword_cache_required': False,
            'generator_sha256': phased_qa.qa_run.file_hash(Path(__file__)),
            'extension_files': {str(p.relative_to(ROOT)): phased_qa.qa_run.file_hash(p) for p in
                                [ROOT / 'minirag/operate.py', ROOT / 'reproduce/research/phased_qa.py']}})
    print('Ready: C6=HYBRID_NO_GRAPH, dev401, seed101; no keyword cache/parser or graph retrieval; local embedding.', flush=True)
    if not args.execute:
        print('To run: .\\.venv\\Scripts\\python.exe reproduce/research/run_c6_dev_contexts.py --execute')
        return 0
    return phased_qa.main(['contexts', '--config', 'C6', '--dataset-id', '2wiki',
        '--index', str(a.index), '--questions', str(a.questions), '--registration', str(a.registration),
        '--serving-config', str(a.serving_config), '--out', str(OUT), '--seed', '101',
        '--llm-max-async', '4', '--workers', '1'])


if __name__ == '__main__':
    raise SystemExit(main())
