"""Dev-only C0 temporal replay from frozen diagnostic contributions; no retrieval/model."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import networkx as nx
import tiktoken

from c0_sim import load_diag, pack, simulate
from minirag.temporal import overlay, parse_query, entity_h, rank_temporal

INDEX = ROOT.parents[1] / 'LiHua-World-qwen-modal'
DIAG = ROOT.parents[1] / 'logs/graph_repair/phase1/t0_on/diag.jsonl'
FROZEN = ROOT / 'logs/c_ablation/graph/C0/C0_records.jsonl'
DEV = ROOT / 'logs/devset.csv'
GOLD = ROOT.parents[1] / 'logs/graph_repair/phase1/t2_summary.jsonl'


def replay(diag, graph, by_time, years, chunks, encoder, *, h_one=False, expand=True):
    anchors = parse_query(diag['query'], years)
    original = simulate(diag, chunks, encoder)[1]
    if not anchors:
        return original
    scores = Counter({cid: sum(e['contribution'] for e in entries)
                      for cid, entries in diag['contributions'].items()})
    pairs = {(m['keyword'], name, float(m['score']))
             for name, seed in diag['seeds'].items() if not seed['short_path_removed']
             for m in seed['matches']}
    h = entity_h(graph, pairs)
    ranking, _ = rank_temporal(scores, by_time, anchors, h, diag['vector_ids'],
                               h_one=h_one, expand=expand, limit=int(diag['top_k']) // 2)
    return pack(ranking, chunks, encoder=encoder)


def main():
    chunks = json.loads((INDEX / 'kv_store_text_chunks.json').read_text(encoding='utf-8'))
    docs = json.loads((INDEX / 'kv_store_full_docs.json').read_text(encoding='utf-8'))
    by_time, years = overlay(docs, chunks)
    graph = nx.read_graphml(INDEX / 'graph_chunk_entity_relation.graphml')
    diag = load_diag(DIAG)
    frozen = {r['question']: r for r in load_diag(FROZEN)}
    dev = {r['Question']: r for r in csv.DictReader(DEV.open(encoding='utf-8-sig', newline=''))}
    if set(frozen) - set(dev):
        raise AssertionError('frozen C0 contains a non-dev question')
    gold = defaultdict(set)
    for item in load_diag(GOLD):
        gold[item['question']].add(item['gold_chunk'])
    encoder = tiktoken.get_encoding('o200k_base')
    base_ok = full_ok = control_ok = up = down = unchanged = 0
    for row in diag:
        question = row['query']
        base = simulate(row, chunks, encoder)[1]
        if base != frozen[question]['chunk_ids']:
            raise AssertionError(f'C0 mismatch: {question}')
        anchors = parse_query(question, years)
        full = replay(row, graph, by_time, years, chunks, encoder)
        control = replay(row, graph, by_time, years, chunks, encoder, h_one=True)
        if not anchors:
            unchanged += int(full == base)
        wanted = gold[question]
        before, after, ctrl = (bool(wanted) and wanted <= set(ids) for ids in (base, full, control))
        base_ok += before; full_ok += after; control_ok += ctrl
        up += after and not before; down += before and not after
    print(f'C0 {base_ok} -> temporal {full_ok}/180; {up} up / {down} down; h=1 {control_ok}/180; non-temporal unchanged {unchanged}')
    return 0 if (base_ok, full_ok, up, down, control_ok, unchanged) == (75, 91, 16, 0, 86, 154) else 1


if __name__ == '__main__':
    raise SystemExit(main())
