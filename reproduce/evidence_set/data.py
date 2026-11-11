"""Shared corpus, labels and folds for the evidence-set study.

Gold Evidence is a list of `Time:` stamps joined by `<and>`. Each stamp maps to
the chunk(s) whose text holds that header. A question has full evidence when
every stamp has at least one of its chunks present. Labels are for training,
diagnostics and scoring only; the selector never reads them.
"""
import csv
from functools import lru_cache
import hashlib
import json
import os
import re

from reproduce.graph_ablation.study import ROOT
from reproduce.evidence_set.slm import INDEX  # the running SLM's own index

QA = ROOT / 'dataset/LiHua-World/qa/query_set.csv'
BUDGET = 4000
FOLDS = 5


@lru_cache(maxsize=1)
def corpus():
    os.environ.setdefault('TIKTOKEN_CACHE_DIR', str(ROOT / '.cache/minirag/tiktoken'))
    from minirag.utils import encode_string_by_tiktoken
    raw = json.loads((INDEX / 'kv_store_text_chunks.json').read_text())
    chunks = {}
    for cid, r in raw.items():
        stamps = re.findall(r'Time: (\d{8}_\d{2}:\d{2})', r['content'])
        chunks[cid] = {'content': r['content'], 'doc': r['full_doc_id'], 'order': r['chunk_order_index'],
                       'tokens': len(encode_string_by_tiktoken(r['content'])), 'time': stamps[0] if stamps else None}
    by_time = {}
    for cid, c in chunks.items():
        for ts in re.findall(r'Time: (\d{8}_\d{2}:\d{2})', c['content']):
            by_time.setdefault(ts, set()).add(cid)
    by_doc = {}
    for cid, c in sorted(chunks.items(), key=lambda kv: (kv[1]['doc'], kv[1]['order'])):
        by_doc.setdefault(c['doc'], []).append(cid)
    return chunks, by_time, by_doc


@lru_cache(maxsize=1)
def questions():
    """Question text -> first query_set row (2 questions occur twice in the 637 rows)."""
    out = {}
    with QA.open() as f:
        for r in csv.DictReader(f):
            out.setdefault(r['Question'], r)
    return out


def gold(question):
    """(type, list of chunk-id sets per evidence stamp | None, status)."""
    q = questions()[question]
    if q['Type'] == 'Null':
        return q['Type'], None, 'null'
    _, by_time, _ = corpus()
    sets = [by_time.get(ts.strip(), set()) for ts in q['Evidence'].split('<and>')]
    if not all(sets):
        return q['Type'], None, 'unmapped'
    return q['Type'], sets, 'labelled'


def full(ids, sets):
    s = set(ids)
    return all(s & g for g in sets)


def a1(ids, budget=BUDGET):
    """Native A1: whole chunks in order until the next one would exceed the budget."""
    chunks, _, _ = corpus()
    t, out = 0, []
    for c in ids:
        if c not in chunks:
            continue
        t += chunks[c]['tokens']
        if t > budget:
            break
        out.append(c)
    return out


def folds(question_list):
    """Grouped folds: questions sharing a gold document always land in the same fold.

    Deterministic (sha256 order, then greedy balancing per question type).
    Null / unmapped questions are their own group.
    """
    chunks, _, _ = corpus()
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for q in question_list:
        _, sets, _ = gold(q)
        docs = sorted({chunks[c]['doc'] for g in sets for c in g}) if sets else []
        node = 'q:' + q
        find(node)
        for d in docs:
            parent[find(node)] = find('d:' + d)
    groups = {}
    for q in question_list:
        groups.setdefault(find('q:' + q), []).append(q)
    key = lambda g: hashlib.sha256('evidence-set-folds-v1:'.encode() + min(g).encode()).hexdigest()
    load = {}
    out = {}
    for g in sorted(groups.values(), key=lambda g: (-len(g), key(g))):
        t = gold(g[0])[0]
        f = min(range(FOLDS), key=lambda f: (load.get((t, f), 0), load.get(f, 0), f))
        for q in g:
            out[q] = f
        load[(t, f)] = load.get((t, f), 0) + len(g)
        load[f] = load.get(f, 0) + len(g)
    return out
