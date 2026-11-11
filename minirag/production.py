"""Production query profile: C0 + source-time + RRF + source-preserving selection.

Library/baseline defaults stay unchanged. Use this launcher or apply_profile()
explicitly before creating a query worker. Environment profiles are process-wide:
serve different profiles in different workers, never change them mid-request.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from .recomp_encoder import DEFAULT_MODEL_DIR, MODEL, REVISION, WEIGHTS_SHA256

PROFILES = ('production', 'baseline', 'c0')
CACHE_DIR = Path(__file__).resolve().parents[1] / '.cache' / 'minirag' / 'recomp'
MODEL_FILES = ('config.json', 'pytorch_model.bin', 'special_tokens_map.json',
               'tokenizer.json', 'tokenizer_config.json', 'vocab.txt')


def profile_env(profile='production', *, model_dir=None, cache_dir=None):
    if profile not in PROFILES:
        raise ValueError(f'Unknown profile: {profile}')
    env = {key: '' for key in (
        'MINIRAG_PATH_SCORE', 'MINIRAG_PATH_PROJECTION', 'MINIRAG_PATH_SELECTION',
        'MINIRAG_PATH_SCORE_CALIBRATION', 'MINIRAG_PATH_SCORE_NORMALIZATION',
        'MINIRAG_PATH_CONSENSUS', 'MINIRAG_PATH_RESEARCH', 'MINIRAG_PATH_RESEARCH_REVISION',
        'MINIRAG_P2_ENHANCE', 'MINIRAG_GRAPH_FLOW', 'MINIRAG_GRAPH_ARM',
        'MINIRAG_PATH_PRUNE', 'MINIRAG_CHUNK_CUT', 'MINIRAG_LEEF', 'MINIRAG_RERANK',
        'MINIRAG_SOURCE_EVENT_TIME')}
    env.update(MINIRAG_ANSWER_TYPE_FIX='1', MINIRAG_PATH2CHUNK_FIX='0',
        MINIRAG_PATH_SCORE_FLOW='0', MINIRAG_TEMPORAL='0' if profile == 'c0' else '1',
        MINIRAG_TEMPORAL_EXPAND='1', MINIRAG_TEMPORAL_H='0',
        MINIRAG_TEMPORAL_RRF='' if profile == 'c0' else '1',
        MINIRAG_CHUNK_FUSION='' if profile == 'c0' else 'rrf',
        MINIRAG_EXTRACTIVE_CONTEXT='neighbors' if profile == 'production' else '',
        MINIRAG_TRUNCATE_SOURCES='1', MINIRAG_MAX_TOKEN_TEXT_UNIT='4000')
    env['MINIRAG_RECOMP_MODEL_DIR'] = str(Path(model_dir or DEFAULT_MODEL_DIR).resolve())
    env['MINIRAG_RECOMP_CACHE'] = str(Path(cache_dir or CACHE_DIR).resolve())
    return env


def apply_profile(profile='production', *, environ=None, model_dir=None, cache_dir=None):
    target = os.environ if environ is None else environ
    env = profile_env(profile, model_dir=model_dir or target.get('MINIRAG_RECOMP_MODEL_DIR'),
                      cache_dir=cache_dir or target.get('MINIRAG_RECOMP_CACHE'))
    target.update(env)
    return env


def prepare_model(directory):
    """Explicit public checkpoint download only; no inference or paid API."""
    from huggingface_hub import snapshot_download
    directory = Path(directory)
    snapshot_download(MODEL, revision=REVISION, local_dir=directory,
                      allow_patterns=list(MODEL_FILES))
    actual = hashlib.sha256((directory / 'pytorch_model.bin').read_bytes()).hexdigest()
    if actual != WEIGHTS_SHA256:
        raise ValueError('RECOMP checkpoint checksum mismatch')
    return {'model': MODEL, 'revision': REVISION, 'weights_sha256': actual,
            'directory': str(directory.resolve()), 'inference_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, default='production',
                        help='baseline = C0+source-time+RRF+A1; c0 = project C0')
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--prepare-model', action='store_true',
                        help='Explicitly download/check the pinned public encoder; then exit')
    parser.add_argument('command', nargs=argparse.REMAINDER,
                        help='-- python reproduce/Step_1_QA.py ... (run in this profile)')
    args = parser.parse_args()
    env = apply_profile(args.profile, model_dir=args.model_dir, cache_dir=args.cache_dir)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if args.prepare_model:
        if command:
            parser.error('--prepare-model is a separate setup step, without a query command')
        print(json.dumps(prepare_model(env['MINIRAG_RECOMP_MODEL_DIR']), indent=2))
        return
    if not command:
        print(json.dumps({'profile': args.profile, 'top_k': 60, 'source_budget': 4000,
                          'environment': env}, indent=2))
        return
    if args.profile == 'production':
        missing = [name for name in MODEL_FILES
                   if not (Path(env['MINIRAG_RECOMP_MODEL_DIR']) / name).is_file()]
        if missing:
            parser.error('Encoder missing. Run python -m minirag.production --prepare-model first')
    os.execvpe(command[0], command, os.environ.copy())


if __name__ == '__main__':
    main()
