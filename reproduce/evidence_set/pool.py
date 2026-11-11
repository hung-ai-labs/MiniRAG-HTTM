"""Capture the FULL candidate ranking of the no-RRF baseline (0 LLM calls).

Baseline = profile `baseline` (C0 + source-time + A1@4000, no RRF, no path pruning).
The native pipeline cuts twice at top_k/2 = 30 (kwd2chunk, then rank_temporal).
This script runs the native retrieval unchanged and, through thin wrappers,
records what lies behind both cuts:

  graph_full     every chunk kwd2chunk scored (> 0), in native order
  graph_scores   its score
  final_full     every chunk after the source-time boost, in native order
                 (= graph_full when the question has no time anchor)
  date_chunks    every chunk whose Time header matches a query anchor
                 (rank_temporal boosts at most 3 per anchor)
  groups         query keyword -> seed entities -> (score, chunk path)
  dense_ids      the native dense top 30 (used by C0 only as a x10 boost)

Wrappers call the original functions twice, once with the native limit and
once unlimited, and assert that the native result is the prefix of the
unlimited one, so the baseline is provably untouched. Every native context
must also match the frozen BASELINE arm byte for byte.

Parser outputs come only from the frozen keyword cache (MINIRAG_KW_CACHE_ONLY=1);
embedding is local. The index is copied to a temporary directory.

    .venv/bin/python -m reproduce.evidence_set.pool [--limit N]
"""
import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import tempfile

from reproduce.graph_ablation.study import ROOT, read, lines, write, append, sha, hashfiles
from reproduce.evidence_set.slm import SLM, OUT, INDEX, URL_FILE, GEN_MODEL

FROZEN = ROOT / 'logs/p0_paths/20261109_dev200'
REFERENCE = ROOT / 'review/learned_selector_lihua_20261111/contexts200.jsonl'
UNLIMITED = 10 ** 9


def install_capture(capture):
    from minirag import operate as op, temporal
    orig_k, orig_t = op.kwd2chunk, temporal.rank_temporal

    def kwd2chunk(ent_from_query_dict, chunks_ids, chunk_nums, *, scores_out=None):
        native = orig_k(ent_from_query_dict, chunks_ids, chunk_nums, scores_out=scores_out)
        scores = Counter()
        full = orig_k(ent_from_query_dict, chunks_ids, UNLIMITED, scores_out=scores)
        assert full[:chunk_nums] == native, 'kwd2chunk prefix changed'
        capture.update(graph_full=full, graph_scores={c: float(s) for c, s in scores.items()},
                       dense_ids=list(chunks_ids), graph_limit=chunk_nums,
                       groups={k: [{'score': float(d['Score']), 'path': list(d['Path'])} for d in v]
                               for k, v in ent_from_query_dict.items()})
        return native

    def rank_temporal(base_scores, by_time, anchors, h, vector_ids, *, expand=True, h_one=False, limit=30):
        native, lists = orig_t(base_scores, by_time, anchors, h, vector_ids,
                               expand=expand, h_one=h_one, limit=limit)
        full, lists2 = orig_t(base_scores, by_time, anchors, h, vector_ids,
                              expand=expand, h_one=h_one, limit=None)
        assert full[:limit] == native and lists2 == lists, 'rank_temporal prefix changed'
        capture.update(final_full=full, anchors=sorted(anchors), boosted=lists,
                       date_chunks={a: sorted(by_time.get(a, ())) for a in sorted(anchors)})
        return native, lists

    op.kwd2chunk = kwd2chunk
    temporal.rank_temporal = rank_temporal


PARSER_SEED = 20260914  # same per-request seed as the frozen dev200 parser cache (screen_variant.SEED)


def nondev_questions():
    """The 435 distinct questions outside dev200, in query_set order. id = ordinal."""
    import csv
    with (ROOT / 'logs/devset.csv').open() as f:
        dev = {r['Question'] for r in csv.DictReader(f)}
    with (ROOT / 'dataset/LiHua-World/qa/query_set.csv').open() as f:
        allq = list(dict.fromkeys(r['Question'] for r in csv.DictReader(f)))
    out = [q for q in allq if q not in dev]
    assert len(out) == 435, len(out)
    return out


def slm_parser_env():
    """The SLM on Modal for the keyword parser only (one call per question)."""
    config = Path.home() / '.config/minirag'
    base = (config / URL_FILE).read_text().strip().rstrip('/')
    os.environ.update(GEMINI_API_BASE=base if base.endswith('/v1') else base + '/v1',
                      GEMINI_API_KEY_ONLY=(config / 'slm_key').read_text().strip(),
                      MINIRAG_MAX_TOKENS='1024', MINIRAG_SLM_SEED=str(PARSER_SEED),
                      GEMINI_RPM='100000', GEMINI_TPM='100000000')


async def run(limit, split='dev200', shard=(0, 1), profile='baseline'):
    from minirag import MiniRAG, QueryParam
    from minirag.production import apply_profile
    from reproduce.path.path_common import embedding, forbidden_llm, CACHE
    k, n_shards = shard
    if split == 'dev200' and SLM != 'qwen':
        # own index, own parser: the frozen Qwen parser cache and Qwen contexts do not apply
        questions = read(FROZEN / 'manifest.json')['questions'][:limit]
        reference = None
        slm_parser_env()
        import minirag.llm.gemini as gem
        gem.DEFAULT_MODEL = 'minirag-slm'
        kw_cache, llm, name = OUT / f'kw_cache_dev200_{k}of{n_shards}.jsonl', gem.gemini_complete, 'minirag-slm'
        path = OUT / f'pools_dev200_{k}of{n_shards}.jsonl'
        ctx_path = OUT / f'contexts_dev200_{k}of{n_shards}.jsonl'
    elif split == 'dev200':
        questions = read(FROZEN / 'manifest.json')['questions'][:limit]
        reference = {r['id']: r for r in lines(REFERENCE) if r['arm'] == 'BASELINE'}
        kw_cache, llm, name = CACHE, forbidden_llm, 'offline-frozen-parser'
        path = OUT / 'pools_dev200.jsonl'
        ctx_path = OUT / 'contexts_dev200.jsonl'
    else:
        questions = nondev_questions()[:limit]
        reference = None
        slm_parser_env()
        import minirag.llm.gemini as gem
        gem.DEFAULT_MODEL = 'minirag-slm'  # the keyword call carries no hashing_kv, so the name comes from here
        gemini_complete = gem.gemini_complete
        kw_cache, llm, name = OUT / f'kw_cache_nondev_{k}of{n_shards}.jsonl', gemini_complete, 'minirag-slm'
        path = OUT / f'pools_nondev_{k}of{n_shards}.jsonl'
        ctx_path = OUT / f'contexts_nondev_{k}of{n_shards}.jsonl'
    if profile == 'c0':
        # C0 = MiniRAG original (no source-time). Parser answers come only from the caches
        # written by the baseline capture, so this costs 0 LLM calls.
        reference = None
        if split == 'nondev':
            merged = OUT / 'kw_cache_nondev_all.jsonl'
            merged.write_text(''.join((OUT / f'kw_cache_nondev_{j}of4.jsonl').read_text() for j in range(4)))
            kw_cache = merged
        elif SLM != 'qwen':
            merged = OUT / 'kw_cache_dev200_all.jsonl'
            merged.write_text(''.join((OUT / f'kw_cache_dev200_{j}of4.jsonl').read_text() for j in range(4)))
            kw_cache = merged
        llm, name = forbidden_llm, 'offline-frozen-parser'
        tag = 'dev200' if split == 'dev200' else 'nondev'
        path = OUT / f'pools_{tag}_c0_{k}of{n_shards}.jsonl'
        ctx_path = OUT / f'contexts_{tag}_c0_{k}of{n_shards}.jsonl'
    before = hashfiles(INDEX)
    baseline_yaml = sha((ROOT / 'baseline.yaml').read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    done = {r['id'] for r in lines(path)}
    capture = {}
    install_capture(capture)
    with tempfile.TemporaryDirectory(prefix='evidence-set-pool-') as d:
        work = Path(d)
        for n in before:
            dst = work / n
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(INDEX / n, dst)
        rag = MiniRAG(working_dir=d, llm_model_func=llm, llm_model_name=name,
                      enable_llm_cache=False, embedding_func=embedding(), log_level='ERROR')
        apply_profile(profile)
        assert not os.environ['MINIRAG_CHUNK_FUSION'] and not os.environ['MINIRAG_TEMPORAL_RRF']
        assert not os.environ['MINIRAG_EXTRACTIVE_CONTEXT'] and not os.environ['MINIRAG_PATH_PRUNE']
        os.environ.update(MINIRAG_KW_CACHE=str(kw_cache))
        if (split == 'dev200' and SLM == 'qwen') or profile == 'c0':
            os.environ['MINIRAG_KW_CACHE_ONLY'] = '1'
        else:
            os.environ.pop('MINIRAG_KW_CACHE_ONLY', None)
        trace = work / 'trace.jsonl'
        for i, q in enumerate(questions):
            if i in done or i % n_shards != k:
                continue
            capture.clear()
            trace.unlink(missing_ok=True)
            os.environ.update(MINIRAG_CONTEXT_LOG=str(trace), MINIRAG_CHUNK_BUDGET_TRACE='1')
            ctx = await rag.aquery(q, QueryParam(mode='mini', top_k=60, only_need_context=True))
            t = lines(trace)
            assert len(t) == 1 and isinstance(ctx, str) and sha(ctx) == t[0]['context_sha256']
            t = t[0]
            if reference is not None:
                ref = reference[i]
                assert ref['question'] == q
                assert sha(ctx) == ref['context_sha256'], f'native context differs from frozen baseline at {i}'
                assert t['ranked_ids'] == ref['pool_ids'] and t['chunk_ids'] == ref['chunk_ids'], i
            final_full = capture.get('final_full', capture['graph_full'])
            assert final_full[:30] == t['ranked_ids'], i
            append(path, {'id': i, 'question': q, 'context_sha256': sha(ctx),
                          'baseline_pool': t['ranked_ids'], 'baseline_kept': t['chunk_ids'],
                          'final_full': final_full, 'graph_full': capture['graph_full'],
                          'graph_scores': capture['graph_scores'], 'dense_ids': capture['dense_ids'],
                          'anchors': capture.get('anchors', []), 'boosted': capture.get('boosted', {}),
                          'date_chunks': capture.get('date_chunks', {}), 'groups': capture['groups']})
            append(ctx_path, {'id': i, 'context': ctx, 'context_sha256': sha(ctx)})
            if (i + 1) % 10 == 0:
                print(json.dumps({'split': split, 'shard': k, 'question_index': i + 1, 'total': len(questions)}),
                      flush=True)
    assert hashfiles(INDEX) == before and sha((ROOT / 'baseline.yaml').read_bytes()) == baseline_yaml
    write(path.with_suffix('.manifest.json'), {
        'baseline': f'profile {profile}: ' + ('C0 original, A1@4000, no source-time' if profile == 'c0' else
                                             'C0 + source-time + A1@4000, no RRF, no path pruning'),
        'split': split, 'shard': list(shard), 'questions': len(lines(path)),
        'native_contexts_match_frozen_baseline': reference is not None, 'native_prefix_asserted': True,
        'slm': SLM, 'index': INDEX.name,
        'parser': 'frozen keyword cache only' if (split == 'dev200' and SLM == 'qwen') or profile == 'c0' else
                  f'{GEN_MODEL} (Modal, minirag-slm), seed {PARSER_SEED}, max_tokens 1024, cached in {kw_cache.name}',
        'parser_calls': 0 if (split == 'dev200' and SLM == 'qwen') or profile == 'c0' else len(lines(kw_cache)),
        'index_sha256': before, 'pools_sha256': sha(path.read_bytes())})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--split', choices=('dev200', 'nondev'), default='dev200')
    ap.add_argument('--limit', type=int, default=10 ** 6)
    ap.add_argument('--shard', default='0/1', help='k/N: this process handles questions with index %% N == k')
    ap.add_argument('--profile', choices=('baseline', 'c0'), default='baseline')
    a = ap.parse_args()
    k, n = map(int, a.shard.split('/'))
    asyncio.run(run(a.limit, a.split, (k, n), a.profile))
