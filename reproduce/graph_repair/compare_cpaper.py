"""Read-only paired C-paper/C0 dev-180 comparison. Run only after both offline arms finish."""
import json
from math import comb
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reproduce' / 'screening'))
from screen_variant import dev_rows, gold_map  # noqa: E402

BASE = ROOT / 'logs' / 'graph_repair' / 'cpaper'


def load(path):
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    return {row['question']: row for row in rows}


def exact_mcnemar(up, down):
    n = up + down
    return min(1., 2 * sum(comb(n, i) for i in range(min(up, down) + 1)) / 2**n) if n else 1.


def p90(values):
    values = sorted(values)
    return values[int(.9 * (len(values) - 1))]


def main():
    a = load(BASE / 'c0_off_reg' / 'C0_records.jsonl')
    b = load(BASE / 'c_paper' / 'C0_records.jsonl')
    gold = gold_map()
    rows = [r for r in dev_rows() if r['Question'] in gold]
    questions = [r['Question'] for r in rows]
    if len(questions) != 180 or set(a) != set(b) or set(a) != set(questions):
        raise SystemExit('Expected identical dev-180 question sets')
    full_a = {q: set(gold[q]) <= set(a[q].get('chunk_ids', [])) for q in questions}
    full_b = {q: set(gold[q]) <= set(b[q].get('chunk_ids', [])) for q in questions}
    up = sum(full_b[q] and not full_a[q] for q in questions)
    down = sum(full_a[q] and not full_b[q] for q in questions)
    micro = lambda data: sum(len(set(gold[q]) & set(data[q].get('chunk_ids', []))) for q in questions)
    result = {
        'n': 180, 'c0_full': sum(full_a.values()), 'cpaper_full': sum(full_b.values()),
        'up': up, 'down': down, 'mcnemar_exact_two_sided': exact_mcnemar(up, down),
        'gold_chunks_total': sum(len(gold[q]) for q in questions),
        'c0_gold_chunks_kept': micro(a), 'cpaper_gold_chunks_kept': micro(b),
        'by_type': {kind: {'n': sum(r.get('Type') == kind for r in rows),
                           'c0_full': sum(full_a[r['Question']] for r in rows if r.get('Type') == kind),
                           'cpaper_full': sum(full_b[r['Question']] for r in rows if r.get('Type') == kind)}
                    for kind in ('Single', 'Multi')},
        'median_sources_tokens': {name: statistics.median(data[q].get('sources_tok', 0) for q in questions)
                                  for name, data in (('C0', a), ('C-paper', b))},
        'retrieval_ms': {name: {'p50': statistics.median(data[q]['retrieval_ms'] for q in questions),
                                'p90': p90([data[q]['retrieval_ms'] for q in questions])}
                         for name, data in (('C0', a), ('C-paper', b))},
        'cpaper_pairs_capped': sum(b[q].get('path_pairs_capped', 0) for q in questions),
    }
    (BASE / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
