"""Which SLM the evidence-set pipeline runs on (MINIRAG_EVSET_SLM=qwen|phi, default qwen).

Each SLM has its OWN index (built by that SLM, as in the paper), its own keyword parser,
reader and output directory. Nothing is shared between the two except the code, the
corpus chunks (same chunker -> same chunk ids) and the gold labels.
"""
import os

from reproduce.graph_ablation.study import ROOT

SLM = os.environ.get('MINIRAG_EVSET_SLM', 'qwen')
_SPEC = {
    'qwen': {'index': 'LiHua-World-qwen-modal', 'out': '', 'url_file': 'slm_url',
             'model': 'Qwen/Qwen2.5-3B-Instruct', 'name': 'Qwen2.5-3B-Instruct'},
    'phi': {'index': 'LiHua-World-phi-modal', 'out': 'phi', 'url_file': 'phi_url',
            'model': 'microsoft/Phi-3.5-mini-instruct', 'name': 'Phi-3.5-mini-instruct'},
}
assert SLM in _SPEC, f'MINIRAG_EVSET_SLM must be one of {sorted(_SPEC)}'
SPEC = _SPEC[SLM]
BASE = ROOT / 'review/evidence_set_20261111'
OUT = BASE / SPEC['out'] if SPEC['out'] else BASE
INDEX = ROOT / SPEC['index']
GEN_MODEL = SPEC['model']
URL_FILE = SPEC['url_file']
