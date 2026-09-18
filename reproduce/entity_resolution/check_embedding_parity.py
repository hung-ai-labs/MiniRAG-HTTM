"""Cong kiem tra parity embedding truoc khi gop (E1, muc 3 cua don harden 17/09/2026).

Lay >=10 ban ghi VDB KHONG bi merge dong toi tu index goc, dung lai chinh xac chuoi `content`
theo dung cong thuc trong minirag/operate.py, nhung lai bang embedding function hien tai, roi
so voi vector da commit. Neu khong gan nhu dong nhat -> BLOCKER, khong duoc chay tiep.

    .venv/Scripts/python.exe reproduce/entity_resolution/check_embedding_parity.py

Luu y ve batch: minirag/llm/hf.py:177-188 tinh mean tren last_hidden_state theo CHIEU DAI DA
PAD va KHONG dung attention_mask, nen vector cua cung mot chuoi PHU THUOC vao cac chuoi khac
trong cung batch (pad dai hon -> trung binh bi keo ve vector cua token pad). Vi vay script do
ca hai che do:
  - "single": nhung tung chuoi mot minh (khong pad thua)
  - "batch" : nhung ca lo cung luc (pad theo chuoi dai nhat trong lo)
Bao cao ca hai de biet vector da commit tuong ung che do nao, va do nhay batch lon bao nhieu.
"""

import argparse
import base64
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from merge_entities import (  # noqa: E402
    DEFAULT_SOURCE, LOG_DIR, DEFAULT_MERGE_REVIEW, load_merge_review, read_graph,
    build_local_embedding_func,
)

PASS_COSINE = 0.999  # nguong "gan nhu dong nhat" cho trung vi cosine


def load_vdb_json(workingdir, namespace):
    o = json.load(open(os.path.join(workingdir, f"vdb_{namespace}.json"), encoding="utf-8"))
    m = o["matrix"]
    if isinstance(m, str):
        arr = np.frombuffer(base64.b64decode(m), dtype=np.float32)
        matrix = arr.reshape(-1, o["embedding_dim"])
    else:
        matrix = np.asarray(m, dtype=np.float32).reshape(-1, o["embedding_dim"])
    return o["data"], matrix


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1, n)


def pick_records(workingdir, touched_names, n_each):
    """Chon tat dinh (theo __id__ tang dan) cac ban ghi KHONG dinh toi ten bi merge."""
    graph = read_graph(workingdir)
    out = []

    data, matrix = load_vdb_json(workingdir, "entities_name")
    rows = sorted(((d["__id__"], i, d) for i, d in enumerate(data)), key=lambda x: x[0])
    for _id, i, d in rows:
        if len(out) >= n_each:
            break
        name = d.get("entity_name")
        if name in touched_names or not graph.has_node(name):
            continue
        out.append(("entities_name", _id, name, matrix[i]))

    data, matrix = load_vdb_json(workingdir, "entities")
    rows = sorted(((d["__id__"], i, d) for i, d in enumerate(data)), key=lambda x: x[0])
    picked = 0
    for _id, i, d in rows:
        if picked >= n_each:
            break
        name = d.get("entity_name")
        if name in touched_names or not graph.has_node(name):
            continue
        desc = graph.nodes[name].get("description", "")
        out.append(("entities", _id, name + " " + desc, matrix[i]))
        picked += 1

    data, matrix = load_vdb_json(workingdir, "relationships")
    rows = sorted(((d["__id__"], i, d) for i, d in enumerate(data)), key=lambda x: x[0])
    picked = 0
    for _id, i, d in rows:
        if picked >= n_each:
            break
        s, t = d.get("src_id"), d.get("tgt_id")
        if s in touched_names or t in touched_names or not graph.has_edge(s, t):
            continue
        e = graph.edges[s, t]
        content = f"{e.get('keywords', '')} {s} {t} {e.get('description', '')}"
        out.append(("relationships", _id, content, matrix[i]))
        picked += 1

    return out


async def embed_all(embedding_func, texts, mode):
    if mode == "single":
        vecs = [await embedding_func([t]) for t in texts]
        return np.concatenate(vecs)
    return await embedding_func(texts)


def recover_pad_length(texts, committed_vecs, max_pad=520):
    """Do parity CUA HAM embedding, tach khoi artefact padding.

    minirag/llm/hf.py:177-188 lay mean tren last_hidden_state theo chieu dai DA PAD va bo qua
    attention_mask, nen vector da commit phu thuoc vao do dai chuoi DAI NHAT trong batch luc
    index -- mot con so ngau nhien theo lo, khong tai tao duoc tu van ban. Ham nay do lai chuoi
    voi tung do dai pad va lay cosine tot nhat: neu dat ~1.0 tren mau thi day la bang chung ho tro
    manh gia thuyet batch-padding dependence (ham, model va content khop voi vector da commit khi
    tai tao dung che do padding). Khong phai chung minh tuyet doi cho toan bo kho.
    """
    from transformers import AutoModel, AutoTokenizer
    import torch

    mid = "sentence-transformers/all-MiniLM-L6-v2"
    tok = AutoTokenizer.from_pretrained(mid)
    mdl = AutoModel.from_pretrained(mid)
    pad_id = tok.pad_token_id
    out = []
    for text, committed in zip(texts, committed_vecs):
        ids = tok([text], truncation=True).input_ids[0]
        best = (-9.0, None)
        lengths = list(range(len(ids), min(len(ids) + 48, max_pad))) + \
                  [x for x in (64, 96, 128, 192, 256, 384, 512) if x > len(ids)]
        for L in lengths:
            x = torch.tensor([ids + [pad_id] * (L - len(ids))])
            with torch.no_grad():
                v = mdl(x).last_hidden_state.mean(dim=1).numpy()
            c = float(np.dot(unit(v).ravel(), unit(committed).ravel()))
            if c > best[0]:
                best = (c, L)
        out.append((best[0], best[1], len(ids)))
    return out


def report(records, fresh, mode):
    lines = []
    per_store = {}
    for (store, _id, _content, committed), new in zip(records, fresh):
        a, b = unit(committed), unit(new)
        cos = float(np.dot(a, b))
        mad = float(np.max(np.abs(a - b)))
        per_store.setdefault(store, []).append((cos, mad))
    for store, vals in sorted(per_store.items()):
        cs = [c for c, _ in vals]
        ms = [m for _, m in vals]
        lines.append(f"  {mode:6s} {store:15s} n={len(vals):3d} "
                     f"cosine min={min(cs):.6f} median={float(np.median(cs)):.6f} "
                     f"max_abs_diff max={max(ms):.6f}")
    all_cos = [c for vals in per_store.values() for c, _ in vals]
    all_mad = [m for vals in per_store.values() for _, m in vals]
    return lines, float(np.median(all_cos)), min(all_cos), max(all_mad)


def main():
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--workingdir", default=DEFAULT_SOURCE)
    ap.add_argument("--merge-review", default=DEFAULT_MERGE_REVIEW)
    ap.add_argument("--n-each", type=int, default=10)
    args = ap.parse_args()

    merges, rejects, _ = load_merge_review(args.merge_review)
    touched = {r.keep for r in merges} | {r.merge for r in merges}

    records = pick_records(args.workingdir, touched, args.n_each)
    texts = [c for _, _, c, _ in records]
    print(f"index: {args.workingdir}")
    print(f"ban ghi untouched duoc chon: {len(records)} "
          f"({args.n_each} moi kho: entities_name / entities / relationships)")

    embedding_func = build_local_embedding_func()
    out_lines, summary = [], {}
    for mode in ("single", "batch"):
        fresh = asyncio.run(embed_all(embedding_func, texts, mode))
        lines, med, mn, mad = report(records, fresh, mode)
        out_lines += lines
        summary[mode] = {"median_cosine": med, "min_cosine": mn, "max_abs_diff": mad}

    best = max(summary, key=lambda m: summary[m]["median_cosine"])
    asis_ok = summary[best]["median_cosine"] >= PASS_COSINE
    print("\n".join(out_lines))
    print(f"\nnhung nhu hien tai -- che do khop nhat: {best} "
          f"(median cosine {summary[best]['median_cosine']:.6f}, min {summary[best]['min_cosine']:.6f})")

    # Tach bach: ham/model/content co dung khong, neu bo qua artefact padding?
    rec = recover_pad_length([c for _, _, c, _ in records], [v for _, _, _, v in records])
    cos_best = [c for c, _, _ in rec]
    fn_median = float(np.median(cos_best))
    fn_min = float(min(cos_best))
    fn_ok = fn_median >= PASS_COSINE
    print(f"parity CUA HAM (tot nhat tren moi do dai pad): median {fn_median:.6f}, min {fn_min:.6f}")
    print("  vi du (cosine tot nhat @ pad_len / so token that):")
    for (store, _id, _c, _v), (c, L, ntok) in list(zip(records, rec))[:6]:
        print(f"    {store:15s} cosine={c:.6f} @ pad_len={L} (token that={ntok})")

    if fn_ok and not asis_ok:
        status = "BLOCKER_PADDING_REGIME"
        msg = ("bang chung ho tro manh gia thuyet batch-padding dependence: nhung lai nhu hien tai "
               "khong khop vector da commit, nhung khop gan tuyet doi khi quet do dai pad (hf.py mean "
               "qua ca vi tri pad, khong dung attention_mask). Quyet dinh che do nhung lai phai duoc "
               "nhom chot truoc khi do retrieval.")
    elif fn_ok:
        status = "PASS"
        msg = "vector tai tao khop voi vector da commit."
    else:
        status = "BLOCKER"
        msg = "ngay ca khi quet moi do dai pad van khong khop -- sai ham, sai model hoac sai content."
    print(f"STATUS: {status} -- {msg}")

    os.makedirs(LOG_DIR, exist_ok=True)
    payload = {"workingdir": args.workingdir, "n_records": len(records), "n_each": args.n_each,
               "threshold_median_cosine": PASS_COSINE, "modes": summary, "best_mode": best,
               "asis_parity_ok": asis_ok,
               "function_parity": {"median_cosine": fn_median, "min_cosine": fn_min, "ok": fn_ok},
               "recovered": [{"store": s, "id": i, "cosine": c, "pad_len": L, "real_tokens": n}
                              for (s, i, _c, _v), (c, L, n) in zip(records, rec)],
               "status": status, "message": msg,
               "detail_lines": out_lines}
    with open(os.path.join(LOG_DIR, "embedding_parity.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
