"""Plan 2Wiki paired C0/C1 QA offline; --execute explicitly enables GPU/API work."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .common import DEFAULT_REPO, DEFAULT_OUTPUT, SPLIT, JUDGE_MODEL, now, read_json, run_lock, runtime_identity, sha, source_hashes, write_json

CONFIGS = ('C0', 'C1')


def positive(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError('Must be positive')
    return n


def verify_validation(path, index):
    """A small synthetic/smoke check can never unlock held-out evaluation."""
    report = read_json(path)
    split = read_json(SPLIT / 'split_manifest.json')
    n = split['counts']['internal_dev_count']
    if (report.get('status') != 'verified' or report.get('validation_scope') != 'all_2wiki_dev'
            or report.get('completed_queries') != n or report.get('total_queries') != n
            or report.get('logical_answer_contexts') != 2 * n or report.get('mismatches')
            or report.get('llm_calls') != 0):
        raise ValueError('Full frozen 2Wiki dev equivalence is required')
    identity = report['identity']
    if identity['source_hashes'] != source_hashes(DEFAULT_REPO) or identity['runtime'] != runtime_identity():
        raise ValueError('Source/runtime changed since validation')
    if identity['questions_sha256'] != sha(SPLIT / 'internal_dev.csv'):
        raise ValueError('Validation used different dev questions')
    from .validate import index_check
    if Path(identity['index_path']).resolve() != Path(index).resolve() or identity['index_manifest_sha256'] != index_check(index):
        raise ValueError('Validated index changed')
    if identity['keyword_sha256'] != sha(identity['keyword_path']):
        raise ValueError('Validation keyword cache changed')
    for name, expected in identity['reference_hashes'].items():
        if sha(Path(identity['reference']) / name) != expected:
            raise ValueError('Validation reference changed')
    return report


def plan(a):
    # Read split metadata only. No question/gold/test file, dotenv or client is
    # opened by this path; it is safe before an index/deployment exists.
    split = read_json(SPLIT / 'split_manifest.json')
    n = split['counts']['internal_' + a.partition + '_count']
    return {'execute': a.execute, 'dataset': '2wiki', 'partition': a.partition,
            'n_questions': n, 'configs': list(CONFIGS), 'seeds': a.seeds,
            'nominal_answers': n * 2 * len(a.seeds), 'nominal_judge_votes': n * 6 * len(a.seeds),
            'shared_retrieval_prefix': True, 'overlap_judging_with_next_seed': a.judge_model is not None,
            'judge_model': a.judge_model, 'judge_passes': 3,
            'gpu_concurrency': a.concurrency, 'cpu_workers': a.workers,
            'index': str(a.index), 'serving_config': str(a.serving_config),
            'validation': str(a.validation), 'out': str(a.out),
            'test_questions_opened': False, 'llm_calls_by_plan': 0,
            'gpu_stage_budget_seconds': a.gpu_stage_budget_seconds,
            'billing_caveat': 'Stage wall-time guard is not a Modal billing limit; warm idle GPU and storage may still cost.'}


def child_environment():
    return os.environ | {'PYTHONHASHSEED': '13', 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1',
                         'PYTHONDONTWRITEBYTECODE': '1'}


def gpu_child(command, log, budget_path, stage, limit):
    budget = read_json(budget_path) if budget_path.exists() else {'consumed_s': 0, 'stages': []}
    if budget.get('active'):
        raise ValueError('Interrupted GPU stage has no end marker; reconcile before resume')
    remaining = limit - budget['consumed_s']
    if remaining <= 0:
        raise ValueError('GPU stage runtime budget exhausted')
    budget['active'] = {'stage': stage, 'started_at': now()}
    write_json(budget_path, budget)
    started, proc = time.monotonic(), None
    try:
        with log.open('a', encoding='utf-8') as handle:
            proc = subprocess.Popen(command, cwd=DEFAULT_REPO, env=child_environment(),
                                    stdout=handle, stderr=subprocess.STDOUT)
            code = proc.wait(timeout=remaining)
            if code:
                raise RuntimeError(f'GPU child failed with exit code {code}; see stage log')
    except BaseException:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait()
        raise
    finally:
        elapsed = time.monotonic() - started
        budget['consumed_s'] += elapsed
        budget['stages'].append(budget.pop('active') | {'elapsed_s': elapsed,
                                'exit_code': proc.returncode if proc else None, 'finished_at': now()})
        write_json(budget_path, budget)


def execute(a):
    if not a.gpu_stage_budget_seconds:
        raise ValueError('Explicit --gpu-stage-budget-seconds is required to execute')
    if a.partition == 'test' and not a.method_frozen:
        raise ValueError('Held-out test requires --method-frozen after method registration is finalized')
    validation = verify_validation(a.validation, a.index)
    # A passed dev report is required even for optimized dev generation.
    # Initial smoke/reference creation uses the unoptimized phased runner.
    questions = SPLIT / f'internal_{a.partition}.csv'
    gold = SPLIT / f'internal_{a.partition}_gold.jsonl'
    split = read_json(SPLIT / 'split_manifest.json')
    for path in (questions, gold):
        if sha(path) != split['outputs'][path.name]:
            raise ValueError('Frozen split bytes changed')
    if a.index.resolve() == a.out.resolve() or a.index.resolve() in a.out.resolve().parents or a.out.resolve() in a.index.resolve().parents:
        raise ValueError('Run output and source index must not contain one another')
    if not a.index.name.startswith('2wiki-'):
        raise ValueError('An explicit 2wiki-* index is required')
    from .validate import index_check
    index_check(a.index)
    declaration = (a.index / 'index_manifest.json').read_text(encoding='utf-8')
    if any(marker in declaration for marker in ('Q4_K_M', 'ollama_native_local', 'local_quantized_Qwen')):
        raise ValueError('Build a separate Modal/bf16 index for this runner')
    from dotenv import dotenv_values
    config = dotenv_values(DEFAULT_REPO / '.env')
    endpoint = os.environ.get('MINIRAG_SLM_URL') or config.get('MINIRAG_SLM_URL')
    if not endpoint or not (os.environ.get('MINIRAG_SLM_KEY') or config.get('MINIRAG_SLM_KEY')):
        raise ValueError('Modal endpoint/key are missing')
    sys.path.insert(0, str(DEFAULT_REPO / 'reproduce/research'))
    import qa_run
    qa_run.read_serving_config(a.serving_config)
    identity = plan(a) | {'questions_sha256': sha(questions), 'gold_sha256': sha(gold),
               'split_sha256': sha(SPLIT / 'split_manifest.json'),
               'index_sha256': index_check(a.index), 'validation_sha256': sha(a.validation),
               'serving_sha256': sha(a.serving_config), 'protocol_sha256': sha(a.registration),
               'source_hashes': source_hashes(DEFAULT_REPO), 'runtime': runtime_identity(),
               'endpoint_sha256': qa_run.digest(endpoint)}
    # Check judge credentials/limiter before starting any GPU stage, in a
    # separate short-lived process; producer never loads Gemini as a backend.
    if a.judge_model:
        subprocess.run([sys.executable, '-m', 'reproduce.research.two_wiki_acceleration.judge_worker',
                        '--out', str(a.out), '--preflight'], cwd=DEFAULT_REPO,
                       env=child_environment(), check=True)
    a.out.mkdir(parents=True, exist_ok=True)
    with run_lock(a.out):
        manifest = a.out / 'RUN_MANIFEST.json'
        if manifest.exists():
            if read_json(manifest) != identity:
                raise ValueError('Run identity changed; use a fresh output directory')
        elif any(p.name != '.qa.lock' for p in a.out.iterdir()):
            raise ValueError('Existing output has no run manifest')
        else:
            write_json(manifest, identity)
        failure = a.out / 'PRODUCER_FAILED.json'
        if failure.exists():
            failure.rename(a.out / f'PRODUCER_FAILED.previous.{time.time_ns()}.json')
        consumer, judge_log = None, None
        try:
            if a.judge_model:
                judge_log = (a.out / 'judge_worker.log').open('a', encoding='utf-8')
                consumer = subprocess.Popen([sys.executable, '-m', 'reproduce.research.two_wiki_acceleration.judge_worker',
                                             '--out', str(a.out)], cwd=DEFAULT_REPO, env=child_environment(),
                                            stdout=judge_log, stderr=subprocess.STDOUT)
            from .validate import run_pairs
            for seed in a.seeds:
                if source_hashes(DEFAULT_REPO) != identity['source_hashes']:
                    raise ValueError('Source changed during execution')
                if consumer and consumer.poll() not in (None, 0):
                    raise RuntimeError('Judge consumer exited before QA completed; inspect judge_worker.log')
                folder = a.out / 'qa' / f's{seed}'
                folder.mkdir(parents=True, exist_ok=True)
                common = ['--dataset-id', '2wiki', '--index', str(a.index.resolve()),
                          '--questions', str(questions), '--registration', str(a.registration.resolve()),
                          '--serving-config', str(a.serving_config.resolve()), '--out', str(folder),
                          '--seed', str(seed), '--llm-max-async', str(a.concurrency)]
                base = [sys.executable, str(DEFAULT_REPO / 'reproduce/research/phased_qa.py')]
                write_json(a.out / 'STATUS.json', {'status': 'running', 'stage': 'keywords', 'seed': seed})
                gpu_child(base + ['keywords'] + common, folder / 'keywords.log', a.out / 'GPU_BUDGET.json',
                          f'keywords_s{seed}', a.gpu_stage_budget_seconds)
                write_json(a.out / 'STATUS.json', {'status': 'running', 'stage': 'shared_contexts', 'seed': seed})
                with run_lock(folder):
                    if run_pairs(DEFAULT_REPO, questions, folder / f'kw_s{seed}.jsonl', a.index, folder,
                                 seed=seed, workers=a.workers):
                        raise RuntimeError('Shared context phase failed')
                ready = {'questions_sha256': sha(questions), 'answers': {}}
                for c in CONFIGS:
                    write_json(a.out / 'STATUS.json', {'status': 'running', 'stage': 'answers', 'seed': seed, 'config': c})
                    gpu_child(base + ['answers', '--config', c] + common, folder / f'answers_{c}.log',
                              a.out / 'GPU_BUDGET.json', f'answers_{c}_s{seed}', a.gpu_stage_budget_seconds)
                    ready['answers'][c] = sha(folder / f'{c}_s{seed}/answers.jsonl')
                write_json(a.out / f'READY_s{seed}.json', ready)
            if consumer and consumer.wait() != 0:
                raise RuntimeError('Judge incomplete; inspect judge_worker.log and resume the same run')
            write_json(a.out / 'STATUS.json', {'status': 'completed', 'at': now(), 'judged': bool(a.judge_model)})
        except BaseException as exc:
            write_json(failure, {'at': now(), 'error_type': type(exc).__name__})
            write_json(a.out / 'STATUS.json', {'status': 'failed', 'at': now(), 'error_type': type(exc).__name__})
            raise
        finally:
            if consumer and consumer.poll() is None:
                consumer.terminate()
                consumer.wait()
            if judge_log:
                judge_log.close()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index', type=Path, default=DEFAULT_REPO / 'indexes/2wiki-modal-n2000-s13-dev20test80')
    p.add_argument('--serving-config', type=Path, default=DEFAULT_REPO / 'configs/research/2wiki/serving_modal.json')
    p.add_argument('--registration', type=Path, default=DEFAULT_REPO / 'docs/research/RUN_2WIKI_DEV20_TEST80.md')
    p.add_argument('--validation', type=Path, default=DEFAULT_OUTPUT / 'DEV_CONTEXT_VALIDATION.json')
    p.add_argument('--partition', choices=('dev', 'test'), default='dev')
    p.add_argument('--out', type=Path, default=DEFAULT_OUTPUT / 'dev')
    p.add_argument('--seeds', nargs='+', type=int, default=[101, 202, 303])
    p.add_argument('--workers', type=positive, default=1)
    p.add_argument('--concurrency', type=positive, default=4)
    p.add_argument('--judge-model', choices=(JUDGE_MODEL,),
                   help='Pinned 2Wiki judge gemini-3.5-flash-lite; omit for QA only')
    p.add_argument('--gpu-stage-budget-seconds', type=positive)
    p.add_argument('--method-frozen', action='store_true')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    if len(set(a.seeds)) != len(a.seeds) or a.concurrency > 32:
        p.error('Seeds must be unique and concurrency <= 32')
    if a.judge_model and not a.judge_model.startswith('gemini-'):
        p.error('Choose an explicit Gemini model ID for judging')
    print(json.dumps(plan(a), ensure_ascii=False, indent=2), flush=True)
    return execute(a) if a.execute else 0


if __name__ == '__main__':
    raise SystemExit(main())
