"""Deterministic, read-only temporal anchors over the loaded document/chunk stores."""
from collections import Counter, defaultdict
from datetime import date
import json
import os
from pathlib import Path
import re

from .prompt import GRAPH_FIELD_SEP

MONTHS = {name: i for i, name in enumerate(
    ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
     'september', 'october', 'november', 'december'), 1)}
MONTH_RE = r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)'
NUMERIC = re.compile(r'(?<!\d)(\d{4})([-/]?)(\d{2})\2(\d{2})(?!\d)')
MONTH_DAY = re.compile(rf'\b{MONTH_RE}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b', re.I)
DAY_MONTH = re.compile(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_RE}\.?(?:,?\s+(\d{{4}}))?\b', re.I)
MONTH_ONLY = re.compile(rf'\b{MONTH_RE}\.?(?:\s+(\d{{4}}))?\b', re.I)
YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')
_CACHE = {}


def month_number(value):
    value = value.lower().rstrip('.')[:3]
    return next(number for name, number in MONTHS.items() if name.startswith(value))


def day_node(d):
    return 'time:day:' + d.isoformat()


def month_node(year, month):
    return f'time:month:{year:04d}-{month:02d}'


def parse_query(query, corpus_years):
    """Return sorted anchors; no ambiguous year or invalid calendar date is inferred."""
    relative_year = re.search(r'\b(?:next|last|previous|this)\s+(?:year|month|week)\b', query, re.I)
    inferred = next(iter(corpus_years)) if len(corpus_years) == 1 and not relative_year else None
    anchors, spans, day_months = set(), [], set()
    for match in NUMERIC.finditer(query):
        try:
            d = date(int(match[1]), int(match[3]), int(match[4]))
        except ValueError:
            continue
        anchors.add(day_node(d)); day_months.add((d.year, d.month)); spans.append(match.span())
    for pattern, day_first in ((MONTH_DAY, False), (DAY_MONTH, True)):
        for match in pattern.finditer(query):
            if any(match.start() < end and match.end() > start for start, end in spans):
                continue
            month = month_number(match[2] if day_first else match[1])
            day = int(match[1] if day_first else match[2])
            year = int(match[3]) if match[3] else inferred
            if year is None:
                spans.append(match.span()); continue
            try:
                d = date(year, month, day)
            except ValueError:
                spans.append(match.span()); continue
            anchors.add(day_node(d)); day_months.add((year, month)); spans.append(match.span())
    for match in MONTH_ONLY.finditer(query):
        if any(match.start() < end and match.end() > start for start, end in spans):
            continue
        # A month name in a holiday or character name is not a date anchor.
        if re.match(r"['’]s\b", query[match.end():], re.I):
            continue
        year = int(match[2]) if match[2] else inferred
        prefix = query[max(0, match.start()-12):match.start()]
        if not match[2] and not re.search(r'\b(in|during|within|for|of)\s*$', prefix, re.I):
            continue
        if year is not None:
            month = month_number(match[1])
            if (year, month) not in day_months:
                anchors.add(month_node(year, month))
    return tuple(sorted(anchors))


def overlay(full_docs, chunks):
    by_time = defaultdict(list)
    years = set()
    doc_dates = {}
    for did, row in full_docs.items():
        match = re.match(r'^Time:\s*(\d{4})(\d{2})(\d{2})(?:_|\b)', row.get('content', ''))
        if match:
            try:
                doc_dates[did] = date(*map(int, match.groups()))
            except ValueError:
                pass
    for cid, row in sorted(chunks.items()):
        d = doc_dates.get(row.get('full_doc_id'))
        if d:
            years.add(d.year)
            by_time[day_node(d)].append(cid)
            by_time[month_node(d.year, d.month)].append(cid)
    return dict(by_time), years


def loaded_overlay(text_chunks_db):
    """Read the sibling full-doc JSON once; never mutate either storage object."""
    data = text_chunks_db._data
    path = Path(text_chunks_db._file_name).with_name('kv_store_full_docs.json')
    key = (str(path), id(data))
    if key not in _CACHE:
        with path.open(encoding='utf-8') as stream:
            _CACHE[key] = overlay(json.load(stream), data)
    return _CACHE[key]


def entity_h(graph, pairs):
    """pairs contains each (keyword, seed, cosine) once."""
    h = defaultdict(lambda: 1.0)
    unique = {}
    for keyword, seed, score in pairs:
        unique[(keyword, seed)] = max(unique.get((keyword, seed), float('-inf')), float(score))
    for (_, seed), score in sorted(unique.items()):
        if seed in graph:
            for cid in set(str(graph.nodes[seed].get('source_id', '')).split(GRAPH_FIELD_SEP)):
                if cid:
                    h[cid] += max(0.0, score)
    return h


def rank_temporal(base_scores, by_time, anchors, h, vector_ids, *, expand=True, h_one=False, limit=30):
    """Preserve Counter tie insertion order, then append new candidates by anchor/L_t."""
    scores = Counter(base_scores)
    original = set(scores)
    vector = set(vector_ids)
    lists = {}
    for anchor in sorted(anchors):
        adjacent = by_time.get(anchor, ())
        ordered = sorted(adjacent, key=lambda c: (-(1 if h_one else h.get(c, 1)),
                                                   -base_scores.get(c, 0), c))[:3]
        lists[anchor] = ordered
        if not ordered:
            continue
        boost = 2 * (10 if ordered[0] in vector else 1)
        for cid in ordered:
            if expand or cid in original:
                scores[cid] += boost * (1 if h_one else h.get(cid, 1))
    return [cid for cid, _ in scores.most_common(limit)], lists


def candidate_ids(graph_chunks, vector_ids, temporal_ids=(), *, expand=True):
    return graph_chunks & (set(vector_ids) | (set(temporal_ids) if expand else set()))


def active(query, text_chunks_db):
    if os.environ.get('MINIRAG_TEMPORAL', '0') != '1':
        return (), None
    by_time, years = loaded_overlay(text_chunks_db)
    anchors = parse_query(query, years)
    return anchors, by_time if anchors else None
