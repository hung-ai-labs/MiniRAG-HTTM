"""Offline exploratory audit: gold-title groups plus exact character-5-gram Jaccard.

No model calls, corpus selection, test question export or final split is performed.
Threshold is fixed at 0.85 before inspecting results. Compare question text and
gold paragraph BODY text (without title); all-context distractors are reported by
the existing split analysis but are not near-duplicate grouping inputs here.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import unicodedata


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in text).split())


def shingles(text):
    normalized = normalize(text)
    return {normalized[i:i+5] for i in range(max(1, len(normalized)-4))} if normalized else set()


def similar_pairs(sets):
    """Exact threshold join with lossless global-order prefix/length filtering."""
    frequency = Counter(token for tokens in sets for token in tokens)
    rank = {token: i for i, token in enumerate(sorted(frequency, key=lambda x: (frequency[x], x)))}
    postings = defaultdict(list)
    pairs, candidates = [], 0
    for i in sorted(range(len(sets)), key=lambda i: (len(sets[i]), i)):
        current = sets[i]
        if not current:
            continue
        prefix_length = len(current) - (85 * len(current) + 99) // 100 + 1
        prefix = sorted(current, key=rank.__getitem__)[:prefix_length]
        possible = {j for token in prefix for j in postings[token]}
        for j in sorted(possible):
            previous = sets[j]
            if len(previous) * 100 < 85 * len(current):
                continue
            candidates += 1
            intersection = len(current & previous)
            union = len(current) + len(previous) - intersection
            if 100 * intersection >= 85 * union:
                pairs.append((min(i, j), max(i, j)))
        for token in prefix:
            postings[token].append(i)
    return sorted(pairs), candidates


def merged_groups(rows, question_pairs, doc_pairs, titles):
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    owners = defaultdict(list)
    for i, q in enumerate(rows):
        for title in sorted({t for t, _ in q['supporting_facts']}):
            if owners[title]:
                union(i, owners[title][0])
            owners[title].append(i)
    for a, b in question_pairs:
        union(a, b)
    for a, b in doc_pairs:
        union(owners[titles[a]][0], owners[titles[b]][0])
    groups = defaultdict(list)
    for i in range(len(rows)):
        groups[find(i)].append(i)
    return sorted(groups.values(), key=lambda g: min(rows[i]['_id'] for i in g)), owners


def crosses_question_pairs(pairs, test):
    return sum((a in test) != (b in test) for a, b in pairs)


def crosses_document_pairs(pairs, owners, titles, dev, test):
    def sides(title):
        indices = set(owners[title])
        return bool(indices & dev), bool(indices & test)
    return sum((sides(titles[a])[0] and sides(titles[b])[1])
               or (sides(titles[a])[1] and sides(titles[b])[0]) for a, b in pairs)


def self_test():
    rng = random.Random(13)
    sample = [set(rng.sample(range(35), rng.randint(1, 30))) for _ in range(100)]
    sample += [{1, 2, 3}, {1, 2, 3}, set(range(20)), set(range(17)), set()]
    actual, _ = similar_pairs(sample)
    expected = [(i, j) for i in range(len(sample)) for j in range(i+1, len(sample))
                if sample[i] | sample[j] and 100 * len(sample[i] & sample[j]) >= 85 * len(sample[i] | sample[j])]
    assert actual == expected, 'Prefix filter differs from exhaustive Jaccard'
    assert shingles('ŻÓŁĆ, Hello!') == shingles('żółć hello')
    assert normalize('Ａ Ｂ') == 'a b'
    print('SELF-TEST OK: prefix join equals exhaustive search, threshold boundary, Unicode normalization')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--sizes', nargs='+', type=int, default=[200, 500, 1000, 2000])
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.repo is None or args.out is None:
        parser.error('Provide --repo and --out, or --self-test')
    if args.out.exists():
        parser.error('Output exists; use a new filename')
    root = args.repo.resolve()
    script = root / 'reproduce/research/analyze_2wiki_splits.py'
    spec = importlib.util.spec_from_file_location('split_module', script)
    split = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(split)
    measure_blob = (root / 'docs/research/env/2wiki_pool_measurements_seed13.json').read_bytes()
    measurements = json.loads(measure_blob)
    raw_blob = (root / 'dataset/2WikiMultiHopQA/raw/extracted/dev.json').read_bytes()
    if sha(raw_blob) != measurements['provenance']['raw_dev_sha256']:
        raise ValueError('Source checksum mismatch')
    rows = sorted(json.loads(raw_blob), key=lambda q: q['_id'])
    random.Random(13).shuffle(rows)
    known = {r['n_queries']: r for r in measurements['results']}
    results = []
    for n in sorted(set(args.sizes)):
        if n not in known:
            parser.error(f'Pool {n} was not measured')
        pool = rows[:n]
        if sha(json.dumps(sorted(q['_id'] for q in pool), ensure_ascii=False, separators=(',', ':')).encode()) != known[n]['query_ids_sha256']:
            raise ValueError('Pool identity mismatch')
        context = {t: s for q in pool for t, s in q['context']}
        titles = sorted({t for q in pool for t, _ in q['supporting_facts']})
        qp, qc = similar_pairs([shingles(q['question']) for q in pool])
        dp, dc = similar_pairs([shingles(' '.join(context[t])) for t in titles])
        groups, owners = merged_groups(pool, qp, dp, titles)
        base_dev, base_test, _ = split.candidate_split(pool, .2, 13)
        original_components = split.components
        try:
            split.components = lambda ignored: groups
            dev, test, _ = split.candidate_split(pool, .2, 13)
        finally:
            split.components = original_components
        assert crosses_question_pairs(qp, test) == 0
        assert crosses_document_pairs(dp, owners, titles, dev, test) == 0
        summary = split.summarize(pool, dev, test, groups)
        summary.pop('near_duplicate_text_check')
        # Existing summarizer calls these gold_components; corrected for combined groups.
        summary['combined_components'] = summary.pop('gold_components')
        summary['largest_combined_component'] = summary.pop('largest_gold_component')
        summary.update({'question_near_duplicate_pairs': len(qp), 'gold_body_near_duplicate_pairs': len(dp),
                        'gold_body_documents_checked': len(titles),
                        'exact_pair_comparisons': {'questions': qc, 'gold_bodies': dc},
                        'baseline_cross_split_question_near_duplicates': crosses_question_pairs(qp, base_test),
                        'baseline_cross_split_gold_body_near_duplicates': crosses_document_pairs(dp, owners, titles, base_dev, base_test),
                        'combined_cross_split_question_near_duplicates': 0,
                        'combined_cross_split_gold_body_near_duplicates': 0})
        results.append(summary)
        print(f"N={n}: question_pairs={len(qp)}, gold_body_pairs={len(dp)}, "
              f"dev={len(dev)}, test={len(test)}, largest_group={summary['largest_combined_component']}", flush=True)
    report = {'status': 'exploratory_audit_not_a_frozen_split', 'selected_n': None,
              'normalization': 'Unicode NFKC + casefold + replace non-alphanumeric with space + collapse whitespace',
              'similarity': 'exact Jaccard of character 5-gram sets; threshold >= 0.85; lossless prefix filter verified against exhaustive fixture',
              'scope': ['question text', 'gold paragraph body text excluding title'],
              'limitations': ['not a semantic paraphrase detector', 'all-context distractor bodies not near-duplicate grouped',
                              'shared corpus allows supporting titles to occur as distractors across the split'],
              'seed': 13, 'requested_test_fraction': .2, 'test_content_exported': False,
              'provenance': {'python_version': sys.version.split()[0], 'source_sha256': sha(raw_blob),
                             'measurement_report_sha256': sha(measure_blob),
                             'split_script_sha256': sha(script.read_bytes()), 'script_sha256': sha(Path(__file__).read_bytes())},
              'results': results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))


if __name__ == '__main__':
    main()
