"""One persistent Gemini pool consumes complete paired seed outputs in order."""
import argparse
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

from .common import DEFAULT_REPO, SPLIT, now, read_json, run_lock, sha, source_hashes, write_json


async def consume(out, request=None, poll_seconds=1):
    sys.path.insert(0, str(DEFAULT_REPO / 'reproduce/research'))
    import judge_2wiki as judge
    manifest = read_json(out / 'RUN_MANIFEST.json')
    questions = SPLIT / f"internal_{manifest['partition']}.csv"
    gold = SPLIT / f"internal_{manifest['partition']}_gold.jsonl"
    if sha(questions) != manifest['questions_sha256'] or sha(gold) != manifest['gold_sha256']:
        raise ValueError('Frozen judge input changed')
    call = request or judge.provider()
    for seed in manifest['seeds']:
        ready_path = out / f'READY_s{seed}.json'
        while not ready_path.exists():
            if (out / 'PRODUCER_FAILED.json').exists():
                raise RuntimeError('Producer failed before paired answers were ready')
            await asyncio.sleep(poll_seconds)
        if manifest.get('source_hashes') != source_hashes(DEFAULT_REPO):
            raise ValueError('Source changed during judging')
        ready = read_json(ready_path)
        if ready['questions_sha256'] != manifest['questions_sha256']:
            raise ValueError('Ready marker refers to different questions')
        for config in manifest['configs']:
            answers = out / 'qa' / f's{seed}' / f'{config}_s{seed}' / 'answers.jsonl'
            if sha(answers) != ready['answers'][config]:
                raise ValueError('Published paired answers changed')
            args = SimpleNamespace(questions=questions, gold=gold, answers=answers,
                                   out=out / 'judge' / f'{config}_s{seed}',
                                   model=manifest['judge_model'], concurrency=4)
            if await judge.execute_job(args, call):
                raise RuntimeError('Judge job has incomplete verdicts; resume without changing inputs')
            write_json(out / 'JUDGE_STATUS.json', {'status': 'running', 'seed': seed, 'config': config, 'at': now()})
    write_json(out / 'JUDGE_STATUS.json', {'status': 'completed', 'at': now()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--preflight', action='store_true')
    a = p.parse_args()
    sys.path.insert(0, str(DEFAULT_REPO / 'reproduce/research'))
    if a.preflight:
        import judge_2wiki
        judge_2wiki.provider()
        print('Judge credentials and limiter configured; no requests made')
        return 0
    with run_lock(a.out / 'judge_consumer'):
        asyncio.run(consume(a.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
