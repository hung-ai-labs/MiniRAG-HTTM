"""Measure candidate 2Wiki pools offline; does not select or split a final pool."""

import argparse
import ast
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def id_hash(ids):
    return sha(json.dumps(sorted(ids), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def components(groups):
    parent = list(range(len(groups)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for i, titles in enumerate(groups):
        for title in set(titles):
            if title in owner:
                a, b = find(i), find(owner[title])
                parent[a] = b
            else:
                owner[title] = i
    sizes = sorted(Counter(find(i) for i in range(len(groups))).values(), reverse=True)
    return {"count": len(sizes), "largest": max(sizes, default=0),
            "size_histogram": dict(sorted(Counter(sizes).items()))}


def load_chunker(root, model):
    # Execute ONLY the checked-in chunking function, without importing optional
    # storage backends or their automatic dependency installers.
    import tiktoken
    path = root / "minirag/operate.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "chunking_by_token_size")
    encoding = tiktoken.encoding_for_model(model)
    namespace = {"encode_string_by_tiktoken": lambda text, model_name: encoding.encode(text),
                 "decode_tokens_by_tiktoken": lambda ids, model_name: encoding.decode(ids)}
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[function.name], encoding, sha(ast.get_source_segment(source, function).encode("utf-8"))


def self_test():
    assert components([['a'], ['a', 'b'], ['b'], ['c']]) == {
        'count': 2, 'largest': 3, 'size_histogram': {1: 1, 3: 1}}
    assert components([[], []])['count'] == 2
    assert id_hash(['a', 'b']) == id_hash(['b', 'a'])
    print('SELF-TEST OK: transitive components, disconnected queries, canonical ID hashes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--sizes', nargs='+', type=int, default=[200, 500, 1000, 2000])
    parser.add_argument('--seed', type=int, default=13)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.repo is None or args.out is None:
        parser.error('Supply --repo and --out, or --self-test')
    if args.out.exists():
        parser.error('Output already exists; use a new report filename')
    root = args.repo.resolve()
    processed = root / 'dataset/2WikiMultiHopQA/processed'
    manifest_blob = (processed / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_blob)
    for name, expected in manifest['outputs'].items():
        if sha((processed / name).read_bytes()) != expected['sha256']:
            raise ValueError(f'Processed checksum mismatch: {name}')
    raw_path = root / 'dataset/2WikiMultiHopQA/raw/extracted/dev.json'
    raw_blob = raw_path.read_bytes()
    if sha(raw_blob) != manifest['inputs']['dev.json']:
        raise ValueError('Raw dev checksum mismatch')
    items = json.loads(raw_blob)
    if len(set(q['_id'] for q in items)) != len(items):
        raise ValueError('Duplicate source query IDs')
    items.sort(key=lambda q: q['_id'])
    random.Random(args.seed).shuffle(items)
    if any(n <= 0 or n > len(items) for n in args.sizes):
        parser.error('Pool sizes must be positive and fit official dev')
    docs = {r['doc_id']: r for r in map(json.loads, (processed / 'docs.jsonl').read_text(encoding='utf-8').splitlines())}
    model, chunk_size, overlap = 'gpt-4o-mini', 1200, 100
    chunker, encoding, chunker_hash = load_chunker(root, model)
    token_cache, chunk_cache = {}, {}
    results = []
    for n in sorted(set(args.sizes)):
        pool = items[:n]
        titles = sorted({t for q in pool for t, _ in q['context']})
        chunk_ids = set()
        chunks_per_doc = []
        for title in titles:
            if title not in token_cache:
                text = docs[title]['text']
                token_cache[title] = len(encoding.encode(text))
                chunks = chunker(text, overlap, chunk_size, model)
                chunk_cache[title] = [hashlib.md5(c['content'].encode('utf-8')).hexdigest() for c in chunks]
            chunk_ids.update(chunk_cache[title])
            chunks_per_doc.append(len(chunk_cache[title]))
        unmapped = sum(1 for q in pool for t, i in q['supporting_facts']
                       if not 0 <= i < len(dict(q['context'])[t]))
        row = {'n_queries': n, 'unique_docs': len(titles),
               'doc_tokens': sum(token_cache[t] for t in titles),
               'chunk_occurrences': sum(chunks_per_doc), 'unique_chunks': len(chunk_ids),
               'docs_with_multiple_chunks': sum(c > 1 for c in chunks_per_doc),
               'nominal_index_calls_extract_plus_one_glean': 2 * len(chunk_ids),
               'calls_note': 'static count before retry/cache; runtime must be measured in pilot',
               'types': dict(sorted(Counter(q['type'] for q in pool).items())),
               'unmapped_supporting_facts': unmapped,
               'query_ids_sha256': id_hash([q['_id'] for q in pool]),
               'doc_ids_sha256': id_hash(titles),
               'components_gold_titles': components([[t for t, _ in q['supporting_facts']] for q in pool]),
               'components_all_context_titles': components([[t for t, _ in q['context']] for q in pool])}
        results.append(row)
        print(f"N={n}: docs={row['unique_docs']}, tokens={row['doc_tokens']}, chunks={row['unique_chunks']}, "
              f"nominal_index_calls={row['nominal_index_calls_extract_plus_one_glean']}, "
              f"largest_gold_group={row['components_gold_titles']['largest']}", flush=True)
    report = {'status': 'candidate_measurements_only_no_pool_or_split_selected',
              'dataset': '2WikiMultiHopQA', 'source_split': 'official_dev',
              'sampling': {'seed': args.seed, 'algorithm': 'sort by original _id; Python random.Random(seed).shuffle; nested prefixes'},
              'chunking': {'tokenizer_model': model, 'encoding': encoding.name,
                           'chunk_size': chunk_size, 'overlap': overlap,
                           'chunker_function_sha256': chunker_hash},
              'provenance': {'raw_dev_sha256': sha(raw_blob), 'processed_manifest_sha256': sha(manifest_blob),
                             'script_sha256': sha(Path(__file__).read_bytes()),
                             'python_version': sys.version.split()[0],
                             'tiktoken_version': importlib.metadata.version('tiktoken')},
              'selected_n': None, 'results': results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'))
    print(f'Report: {args.out}')


if __name__ == '__main__':
    main()
