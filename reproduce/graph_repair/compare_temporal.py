"""Compare the registered dev-180 retrieval arms; invoked only by run_temporal.sh."""
import argparse
from collections import defaultdict
from math import comb
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from minirag.temporal import overlay, parse_query
OUT = ROOT / 'logs/graph_repair/temporal'
GOLD = ROOT.parents[1] / 'logs/graph_repair/phase1/t2_summary.jsonl'


def records(path):
    with path.open(encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    data = {r.get('question', r.get('query')): r for r in rows}
    if len(rows) != len(data) or len(data) != 180:
        raise ValueError(f'{path}: expected 180 unique questions')
    return data


def mcnemar(b, c):
    n = b + c
    return min(1.0, 2 * sum(comb(n, k) for k in range(min(b, c) + 1)) / 2**n) if n else 1.0


def compare(label, before, after, gold, temporal):
    if set(before) != set(after) or set(before) != set(gold):
        raise ValueError(f'{label}: question sets differ')
    b = c = left = right = same = total = 0
    for q in before:
        a, z = before[q], after[q]
        x = gold[q] <= set(a['chunk_ids'])
        y = gold[q] <= set(z['chunk_ids'])
        left += x; right += y; b += y and not x; c += x and not y
        if not temporal[q]:
            total += 1
            same += (a.get('context_sha256') == z.get('context_sha256'))
    print(f'{label}: {left}->{right}/180; b={b}, c={c}, p={mcnemar(b,c):.8g}; non-temporal context {same}/{total}')
    if same != total:
        raise AssertionError(f'{label}: non-temporal context changed')
    return right


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=('c0', 'all'), required=True)
    ap.add_argument('--index', type=Path, required=True)
    ap.add_argument('--paper-baseline', type=Path)
    args = ap.parse_args()
    docs = json.loads((args.index / 'kv_store_full_docs.json').read_text(encoding='utf-8'))
    chunks = json.loads((args.index / 'kv_store_text_chunks.json').read_text(encoding='utf-8'))
    _, years = overlay(docs, chunks)
    gold = defaultdict(set)
    with GOLD.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                gold[row['question']].add(row['gold_chunk'])
    c0 = records(OUT / 'c0_off/C0_records.jsonl')
    temporal = {q: bool(parse_query(q, years)) for q in c0}
    full = records(OUT / 'c0_full/C0_records.jsonl')
    retained = compare('C0 Full vs -V_t', c0, full, gold, temporal)
    if retained != 91:
        raise AssertionError(f'C0 temporal screen expected 91/180, got {retained}/180')
    if args.stage == 'c0':
        return
    c0_h = records(OUT / 'c0_h1/C0_records.jsonl')
    c0_noexpand = records(OUT / 'c0_noexpand/C0_records.jsonl')
    compare('C0 Full vs -interaction', c0_h, full, gold, temporal)
    compare('C0 Full vs -candidate expansion', c0_noexpand, full, gold, temporal)
    if args.paper_baseline is None:
        raise ValueError('--paper-baseline required for all')
    paper = records(args.paper_baseline)
    paper_full = records(OUT / 'paper_full/C0_records.jsonl')
    paper_h = records(OUT / 'paper_h1/C0_records.jsonl')
    paper_noexpand = records(OUT / 'paper_noexpand/C0_records.jsonl')
    compare('C-paper Full vs -V_t', paper, paper_full, gold, temporal)
    compare('C-paper Full vs -interaction', paper_h, paper_full, gold, temporal)
    compare('C-paper Full vs -candidate expansion', paper_noexpand, paper_full, gold, temporal)


if __name__ == '__main__':
    main()
