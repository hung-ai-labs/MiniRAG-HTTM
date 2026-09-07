"""Step 5 - trace one query through MiniRAG's retrieval, stage by stage.

The code map says what each stage *should* do; this shows what it actually does on
a real question. Every stage is wrapped in place rather than reimplemented, so the
trace cannot drift away from the code it documents.

Queries worth tracing come from the baseline's own failures -- a Multi-hop the
system got wrong tells you more than a Single-hop it got right.

    python reproduce/Step_5_trace.py --workingdir ./LiHua-World-gemini \
        --tracefile ./logs/trace_queries.txt --out ./docs/QUERY_TRACE.md
"""

import argparse
import asyncio
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

from gemini_common import build_rag, build_query_param, get_args as _base_args  # noqa: E402

import minirag.operate as OP  # noqa: E402
import minirag.utils as UT  # noqa: E402

TRACE = {}


def _short(x, n=90):
    s = str(x).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def wrap_module_fn(mod, name, key, summarize):
    """Record a module-level function's output without changing its behaviour."""
    orig = getattr(mod, name)

    if asyncio.iscoroutinefunction(orig):
        async def wrapped(*a, **kw):
            out = await orig(*a, **kw)
            TRACE.setdefault(key, []).append(summarize(a, kw, out))
            return out
    else:
        def wrapped(*a, **kw):
            out = orig(*a, **kw)
            TRACE.setdefault(key, []).append(summarize(a, kw, out))
            return out

    setattr(mod, name, wrapped)
    return orig


def wrap_method(obj, name, key, summarize):
    orig = getattr(obj, name)

    async def wrapped(*a, **kw):
        out = await orig(*a, **kw)
        TRACE.setdefault(key, []).append(summarize(a, kw, out))
        return out

    setattr(obj, name, wrapped)
    return orig


def install(rag):
    g = rag.chunk_entity_relation_graph

    # (1) Query Semantic Mapping happens inside minirag_query itself, which
    # minirag.py imported by value -- patching it here would not take effect.
    # The keywords it produces are visible anyway: they are the inputs to (2)
    # and (4) below.

    # (2) Entity Matching
    wrap_method(
        rag.entity_name_vdb, "query", "entity_match",
        lambda a, kw, out: {
            "input_entity": a[0],
            "top_k": kw.get("top_k"),
            "matched": [(r["entity_name"], round(r["distance"], 3)) for r in out[:8]],
            "n_matched": len(out),
        },
    )

    # (3) Starting Entities
    wrap_method(
        g, "get_neighbors_within_k_hops", "hops",
        lambda a, kw, out: {"node": a[0], "k": a[1], "n_paths": len(out),
                            "sample": [list(p) for p in out[:3]]},
    )

    # (4) Candidate Answer Entities
    wrap_method(
        g, "get_node_from_types", "answer_pool",
        lambda a, kw, out: {"types": a[0], "n_candidates": len(out),
                            "sample": [n["entity_name"] for n in out[:10]]},
    )

    # (5a/5b) Reasoning Path scoring
    wrap_module_fn(
        OP, "cal_path_score_list", "path_score",
        lambda a, kw, out: {
            "n_entities": len(out),
            "n_paths": sum(len(v["Path"]) for v in out.values()),
        },
    )
    wrap_module_fn(
        OP, "edge_vote_path", "edge_vote",
        lambda a, kw, out: {"n_good_edges": len(a[1]),
                            "n_paths_with_edge": len(out[1])},
    )

    # (6) Topology-Enhanced Retrieval
    wrap_module_fn(
        OP, "path2chunk", "path2chunk",
        lambda a, kw, out: {
            "max_chunks": kw.get("max_chunks"),
            "chunks_per_entity": {k: v["Path"][:3] for k, v in list(out.items())[:5]},
        },
    )

    # (7) Chunk Retrieval
    wrap_module_fn(
        OP, "kwd2chunk", "final_chunks",
        lambda a, kw, out: {"chunk_nums": kw.get("chunk_nums", a[2] if len(a) > 2 else None),
                            "final_chunk_ids": out},
    )


def render(question, gold, verdict, answer):
    L = []
    L.append(f"## Query: {question}\n")
    L.append(f"- **Gold answer:** {gold}")
    L.append(f"- **Verdict baseline:** `{verdict}`\n")

    em = TRACE.get("entity_match", [])
    L.append("### ② Entity Matching\n")
    if not em:
        L.append("*(không có — bước ① không trả về thực thể nào)*\n")
    for e in em:
        L.append(f"**`{e['input_entity']}`** → {e['n_matched']} node (top_k={e['top_k']})\n")
        L.append("| node khớp | cosine |")
        L.append("|---|---|")
        for n, d in e["matched"]:
            L.append(f"| {n} | {d} |")
        L.append("")

    hops = TRACE.get("hops", [])
    if hops:
        dead = sum(1 for h in hops if h["n_paths"] == 0)
        L.append("### ③ Starting Entities\n")
        L.append(f"{len(hops)} node mở rộng 2-hop · **{dead} node cụt** "
                 f"(không đường đi nào) · {len(hops)-dead} node có đường\n")
        L.append("| node | số đường 2-hop |")
        L.append("|---|---|")
        for h in hops[:12]:
            L.append(f"| {h['node']} | {h['n_paths']} |")
        L.append("")

    ap = TRACE.get("answer_pool", [])
    if ap:
        a = ap[0]
        L.append("### ④ Candidate Answer Entities\n")
        L.append(f"- Loại đáp án LLM đoán: `{a['types']}`")
        L.append(f"- Ứng viên tìm được: **{a['n_candidates']}** node")
        L.append(f"- Ví dụ: {', '.join(a['sample'][:8])}\n")

    ps, ev = TRACE.get("path_score", []), TRACE.get("edge_vote", [])
    if ps:
        L.append("### ⑤ Reasoning Path\n")
        L.append(f"- Chấm điểm: {ps[0]['n_entities']} thực thể · "
                 f"**{ps[0]['n_paths']} đường đi**")
        if ev:
            L.append(f"- Bỏ phiếu cạnh: {ev[0]['n_good_edges']} cạnh liên quan → "
                     f"**{ev[0]['n_paths_with_edge']} đường được cộng phiếu**\n")

    p2c = TRACE.get("path2chunk", [])
    if p2c:
        L.append("### ⑥ Topology-Enhanced Retrieval\n")
        L.append(f"`max_chunks={p2c[0]['max_chunks']}` mỗi thực thể\n")
        L.append("| thực thể | chunk lấy ra |")
        L.append("|---|---|")
        for k, v in p2c[0]["chunks_per_entity"].items():
            L.append(f"| {_short(k,40)} | {', '.join(c[:16] for c in v) or '—'} |")
        L.append("")

    fc = TRACE.get("final_chunks", [])
    if fc:
        L.append("### ⑦ Chunk Retrieval\n")
        L.append(f"- Lấy cuối cùng: **{len(fc[0]['final_chunk_ids'])}** chunk "
                 f"(chunk_nums={fc[0]['chunk_nums']})")
        L.append(f"- ID: {', '.join(c[:16] for c in fc[0]['final_chunk_ids'][:10])}\n")

    L.append("### Câu trả lời sinh ra\n")
    L.append(f"> {_short(answer, 700)}\n")
    return "\n".join(L)


async def main():
    ap = argparse.ArgumentParser(parents=[], add_help=False)
    args = _base_args("Trace một query qua retrieval")
    tracefile = os.environ.get("TRACE_FILE", "./logs/trace_queries.txt")
    outpath = os.environ.get("TRACE_OUT", "./docs/QUERY_TRACE.md")

    with open(tracefile, encoding="utf-8") as f:
        specs = [json.loads(l) for l in f if l.strip()]

    rag = build_rag(args)
    qparam = build_query_param(args)
    install(rag)

    parts = ["# Query Trace — ba câu hỏi thật đi qua MiniRAG\n",
             "> Sinh tự động bởi `reproduce/Step_5_trace.py`. Mỗi bước được bọc "
             "tại chỗ quanh hàm thật, không viết lại logic.\n",
             "> Xem [`RETRIEVAL_CODE_MAP.md`](RETRIEVAL_CODE_MAP.md) để biết mỗi "
             "bước nằm ở file/hàm nào.\n"]

    for s in specs:
        TRACE.clear()
        print("TRACING:", s["question"][:70])
        answer = await rag.aquery(s["question"], param=qparam)
        parts.append(render(s["question"], s["gold"], s["verdict"], answer))
        parts.append("\n---\n")

    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print("wrote", outpath)


asyncio.run(main())
