"""Audit frozen C1 cases and merged provenance, without retrieval or API calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import networkx as nx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from path_common import read, dev_rows


def split(value):
    return [s for s in str(value or '').split('<SEP>') if s]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    # Never overwrite a report, index, cache or a previous review.
    output = output.resolve()
    if output.exists():
        raise FileExistsError('Choose a new output directory')
    index = ROOT / 'LiHua-World-qwen-modal'
    paths = [index / 'graph_chunk_entity_relation.graphml', index / 'kv_store_text_chunks.json',
             index / 'kv_store_llm_response_cache.json', index / 'extracted_chunks.json',
             ROOT / 'logs/path_funnel/20261109/cases_to_review.jsonl',
             ROOT / 'logs/path_calibration/20261109_dev200/inputs.jsonl',
             ROOT / 'logs/path_affinity/20261109_dev200/replay.jsonl',
             ROOT / 'logs/diag_path2chunk.jsonl', ROOT / 'logs/devset.csv', Path(__file__)]
    before = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    graph = nx.read_graphml(paths[0])
    chunks = json.loads(paths[1].read_text())
    cache = json.loads(paths[2].read_text())
    checkpoint = json.loads(paths[3].read_text())
    cases = read(paths[4])
    inputs = {r['question']: r for r in read(paths[5])}
    replay = {r['question']: r for r in read(paths[6])}
    gold = {r['question']: r for r in read(paths[7]) if r.get('gold')}
    answers = {r['Question']: r['Gold Answer'] for r in dev_rows()}
    inventory = Counter()
    node_sources = {name: set(split(d.get('source_id'))) for name, d in graph.nodes(data=True)}
    source_nodes = {}
    source_edges = {}
    for name, sources in node_sources.items():
        for cid in sources:
            source_nodes.setdefault(cid, []).append(name)
    for u, v, d in graph.edges(data=True):
        for cid in set(split(d.get('source_id'))):
            source_edges.setdefault(cid, []).append((u, v))
    for kind, records in (('nodes', [d for _, d in graph.nodes(data=True)]),
                          ('edges', [d for _, _, d in graph.edges(data=True)])):
        inventory[kind] = len(records)
        for d in records:
            sources = set(split(d.get('source_id')))
            descriptions = set(split(d.get('description')))
            inventory[kind + '_multiple_sources'] += len(sources) > 1
            inventory[kind + '_multiple_sources_and_descriptions'] += len(sources) > 1 and len(descriptions) > 1
            inventory[kind + '_equal_multiple_counts_not_proven_alignment'] += len(sources) == len(descriptions) > 1
            inventory[kind + '_missing_source_chunks'] += len(sources - set(chunks))
            inventory[kind + '_explicit_witness_field'] += 'source_witnesses' in d

    output.mkdir(parents=True)
    packet = []
    # Add successful controls with the same Type, deterministic and not selected
    # by any proposed scoring mechanism. Still a case study, not a random sample.
    chosen = {(r['question'], r['gold_chunk']) for r in cases}
    controls = []
    types = {gold[r['question']]['type'] for r in cases}
    for typ in sorted(types):
        for q, r in sorted(gold.items()):
            sel = replay[q]['selections']
            if r['type'] != typ:
                continue
            candidates = [c for c in r['gold'] if c in sel['C1_affinity']['graph_a1']
                          and c in sel['corpus_dense']['graph_a1'] and (q, c) not in chosen]
            if candidates:
                controls.append({'question': q, 'gold_chunk': candidates[0], 'category': 'both_success_control'})
                if sum(c['question'] in gold and gold[c['question']]['type'] == typ for c in controls) == 3:
                    break
    for case in cases + controls:
        q, cid = case['question'], case['gold_chunk']
        r = inputs[q]
        seeds = list(r['entries'])
        supporters = [s for s in seeds if cid in r['entries'][s]['Path']]
        # Structural reachability is NOT a semantic proof or original selected path.
        targets = set(source_nodes.get(cid, []))
        routes = []
        route_count = 0
        for s in seeds:
            if s not in graph:
                continue
            for neighbor in graph.neighbors(s):
                candidates = [(s, neighbor)] if neighbor in targets else []
                candidates += [(s, neighbor, t) for t in graph.neighbors(neighbor)
                               if t in targets and t != s]
                for route in candidates:
                    route_count += 1
                    if len(routes) < 12:
                        routes.append(route)
        sel = replay[q]['selections']
        packet.append({'question': q, 'gold_answer': answers[q],
            'type': gold[q]['type'], 'category': case['category'],
            'gold_chunk': cid, 'all_gold_chunks': gold[q]['gold'],
            'content': chunks.get(cid, {}).get('content'),
            'dense_rank_top30': (sel['corpus_dense']['graph_top30'].index(cid) + 1
                                if cid in sel['corpus_dense']['graph_top30'] else None),
            'dense_deeper_rank': 'not computed; top30 miss is not corpus-wide absence',
            'C1_rank_top30': (sel['C1_affinity']['graph_top30'].index(cid) + 1
                             if cid in sel['C1_affinity']['graph_top30'] else None),
            'C1_retained': cid in sel['C1_affinity']['graph_a1'],
            'supporting_seeds': supporters, 'associated_nodes': source_nodes.get(cid, []),
            'associated_edges': source_edges.get(cid, []),
            'structural_route_count': route_count, 'structural_route_examples': routes,
            'route_warning': 'All two-hop structural routes; not necessarily paths voted/selected by retrieval',
            'review': {'annotation_valid': 'unreviewed', 'alternate_evidence': 'unreviewed',
                       'true_multihop': 'unreviewed', 'source_event_consistency': 'unknown',
                       'failure_taxonomy': 'unreviewed', 'supporting_quote': None}})
    (output / 'review_packet.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in packet))
    lines = ['# Source provenance review packet', '',
             '27 target pairs + successful controls. All semantic labels are unreviewed.',
             'Structural routes and source membership are not proof of a true relation.', '']
    for i, r in enumerate(packet, 1):
        lines += [f"## {i}. {r['category']} — {r['type']}", '',
                  r['question'], '', f"Gold answer: {r['gold_answer']}", '',
                  f"Chunk: `{r['gold_chunk']}`", '',
                  f"C1 retained: {r['C1_retained']}; supporting seed entries: {len(r['supporting_seeds'])}.", '',
                  'Annotation valid / alternate evidence / true multi-hop / event consistency: **unreviewed**.', '',
                  'Source text:', '']
        # Quote the data rather than treating embedded text as Markdown commands.
        lines += ['> ' + line for line in str(r['content']).splitlines()]
        lines += ['', 'See the JSONL for source entities, edges and structural route examples.', '']
    (output / 'REVIEW_PACKET.md').write_text('\n'.join(lines))
    report = {'original_cases': len(cases), 'original_questions': len({r['question'] for r in cases}),
        'controls': len(controls), 'categories': dict(Counter(r['category'] for r in cases)),
        'inventory': dict(inventory), 'llm_cache_entries': len(cache),
        'checkpoint_is_only_ids': isinstance(checkpoint, list) and all(isinstance(x, str) for x in checkpoint),
        'exact_merged_alignment_reconstructible': False,
        'reason': 'No paired raw extraction cache in the inspected index; cardinality equality is not alignment evidence',
        'compatibility_W_implemented': False, 'annotations_reviewed': 0,
        'new_retrieval_runs': 0, 'api_calls': 0}
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    assert all(digest(ROOT / n) == h for n, h in before.items())
    (output / 'manifest.json').write_text(json.dumps({'input_sha256': before, 'inputs_unchanged': True}, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    run(parser.parse_args().output)
