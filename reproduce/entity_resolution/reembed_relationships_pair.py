"""Nhung lai TOAN BO kho quan he cho CA HAI nhanh bang cung mot chinh sach tat dinh.

Can cu: preregistration.md, muc "Amendment 17/09/2026 -- before retrieval measurement".

Van de: hf_embed (minirag/llm/hf.py:177-188) lay mean qua ca vi tri padding va bo qua
attention_mask, nen vector phu thuoc chuoi dai nhat trong lo luc index. Ban gop E1 nhung lai
143/1.463 ban ghi quan he -> hai che do nhung lan lon trong cung mot kho, dung tren duong
relationships_vdb.query (operate.py:1411). Cach xu ly: nhung lai TOAN BO kho quan he o CA control
lan treatment voi batch = 1, de ca hai nhanh chiu cung mot phep bien doi.

Vi sao batch = 1: nano_vector_db_impl.py:138 nhung truy van bang embedding_func([query]) -- luon
mot phan tu. Batch = 1 dat vector luu tru vao dung cung che do padding voi vector truy van.

KHONG doi: model, ham nhung, cong thuc content, graph, vdb_entities_name, vdb_chunks, text
chunks, full docs. KHONG dung attention-mask pooling moi.

    .venv/Scripts/python.exe reproduce/entity_resolution/reembed_relationships_pair.py --force
    .venv/Scripts/python.exe reproduce/entity_resolution/reembed_relationships_pair.py --force --verify-deterministic
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from merge_entities import (  # noqa: E402
    DEFAULT_SOURCE, DEFAULT_DEST, LOG_DIR, GRAPHML_NAME, UNCHANGED_FILES,
    DEFAULT_MERGE_REVIEW, load_merge_review, read_graph, file_sha256,
    build_local_embedding_func, chunk_count_and_ids,
)
from check_embedding_parity import load_vdb_json, unit  # noqa: E402
from minirag.kg.nano_vector_db_impl import NanoVectorDBStorage  # noqa: E402

DEFAULT_PAIR_ROOT = os.path.join(LOG_DIR, "pair")
CONTROL = "control"
TREATMENT = "entres"
COSINE_TOL = 1e-6      # control vs treatment tren ban ghi khong bi E1 dong toi
MAXDIFF_TOL = 1e-5


def open_rel_vdb(workingdir, embedding_func, batch_num=1):
    """embedding_batch_num = 1 -> NanoVectorDBStorage cat contents thanh tung lo 1 phan tu
    (nano_vector_db_impl.py:88,109-112), nen khong co padding cheo giua cac ban ghi."""
    return NanoVectorDBStorage(
        namespace="relationships",
        global_config={"working_dir": workingdir, "embedding_batch_num": batch_num,
                        "vector_db_storage_cls_kwargs": {}},
        embedding_func=embedding_func,
        meta_fields={"src_id", "tgt_id"},
    )


def rel_content(graph, src, tgt):
    """Dung lai dung cong thuc upstream (operate.py:399-407), giu nguyen orientation src/tgt."""
    e = graph.edges[src, tgt]
    return f"{e.get('keywords', '')} {src} {tgt} {e.get('description', '')}"


async def reembed_arm(workingdir, embedding_func):
    graph = read_graph(workingdir)
    vdb = open_rel_vdb(workingdir, embedding_func, batch_num=1)
    records = list(vdb.client_storage["data"])

    missing = [(d["__id__"], d.get("src_id"), d.get("tgt_id")) for d in records
               if not graph.has_edge(d.get("src_id"), d.get("tgt_id"))]
    if missing:
        raise SystemExit(f"{workingdir}: {len(missing)} ban ghi quan he khong ung voi canh nao "
                         f"trong graph, vi du {missing[:3]}")

    payload = {}
    for d in records:
        src, tgt = d["src_id"], d["tgt_id"]           # GIU NGUYEN orientation da co
        payload[d["__id__"]] = {"src_id": src, "tgt_id": tgt,
                                "content": rel_content(graph, src, tgt)}

    t0 = time.perf_counter()
    await vdb.upsert(payload)
    await vdb.index_done_callback()
    return {"records": len(payload), "seconds": round(time.perf_counter() - t0, 1),
            "edges": graph.number_of_edges()}


def build_arm(src_index, dest_dir, force):
    if os.path.abspath(src_index) == os.path.abspath(dest_dir):
        raise SystemExit("source va dest trung nhau")
    if os.path.exists(dest_dir):
        if not force:
            raise SystemExit(f"da ton tai: {dest_dir} -- dung --force (chi xoa dest)")
        shutil.rmtree(dest_dir)
    os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
    shutil.copytree(src_index, dest_dir)


def content_map(workingdir):
    """{__id__: (src, tgt, content)} dung de xac dinh ban ghi nao KHONG bi E1 doi noi dung."""
    graph = read_graph(workingdir)
    data, _ = load_vdb_json(workingdir, "relationships")
    return {d["__id__"]: (d["src_id"], d["tgt_id"], rel_content(graph, d["src_id"], d["tgt_id"]))
            for d in data}


def vectors_by_id(workingdir):
    data, matrix = load_vdb_json(workingdir, "relationships")
    return {d["__id__"]: matrix[i] for i, d in enumerate(data)}


def cross_arm_check(control_dir, treatment_dir):
    """Ban ghi ton tai o CA HAI nhanh va co content y het (khong bi E1 dong toi) thi vector phai
    trung khop -- do la bang chung hai nhanh chiu cung phep bien doi nhung."""
    cc, ct = content_map(control_dir), content_map(treatment_dir)
    vc, vt = vectors_by_id(control_dir), vectors_by_id(treatment_dir)
    common = [i for i in cc if i in ct and cc[i] == ct[i]]
    cos, mad = [], []
    for i in common:
        a, b = unit(vc[i]).ravel(), unit(vt[i]).ravel()
        cos.append(float(np.dot(a, b)))
        mad.append(float(np.max(np.abs(a - b))))
    return {
        "control_records": len(cc), "treatment_records": len(ct),
        "common_untouched": len(common),
        "changed_or_absent": len(ct) - len(common),
        "min_cosine": min(cos) if cos else None,
        "median_cosine": float(np.median(cos)) if cos else None,
        "max_abs_diff": max(mad) if mad else None,
    }


def arm_invariants(arm, work_dir, ref_dir, merges, rejects):
    """So tung file bat bien giua nhanh va index tham chieu cua no."""
    out = []

    def add(name, ok, detail=""):
        out.append({"name": f"[{arm}] {name}", "passed": bool(ok), "detail": str(detail)})

    g_work = os.path.join(work_dir, GRAPHML_NAME)
    g_ref = os.path.join(ref_dir, GRAPHML_NAME)
    add("graphml giong het index tham chieu", file_sha256(g_work) == file_sha256(g_ref))
    add("vdb_entities_name.json giong het (khong nhung lai)",
        file_sha256(os.path.join(work_dir, "vdb_entities_name.json"))
        == file_sha256(os.path.join(ref_dir, "vdb_entities_name.json")))
    add("vdb_chunks.json giong het (khong nhung lai)",
        file_sha256(os.path.join(work_dir, "vdb_chunks.json"))
        == file_sha256(os.path.join(ref_dir, "vdb_chunks.json")))
    for name in UNCHANGED_FILES:
        add(f"file bat bien giong het: {name}",
            file_sha256(os.path.join(work_dir, name)) == file_sha256(os.path.join(ref_dir, name)))

    n_work, ids_work = chunk_count_and_ids(work_dir)
    n_ref, ids_ref = chunk_count_and_ids(ref_dir)
    add("chunk count va danh sach id giong het", n_work == n_ref and ids_work == ids_ref,
        f"{n_work} vs {n_ref}")

    # id / src / tgt cua kho quan he phai giu y nguyen: chi vector va created_at duoc phep doi
    dw, _ = load_vdb_json(work_dir, "relationships")
    dr, _ = load_vdb_json(ref_dir, "relationships")
    key = lambda d: (d["__id__"], d["src_id"], d["tgt_id"])  # noqa: E731
    add("id/src_id/tgt_id cua kho quan he khong doi",
        sorted(map(key, dw)) == sorted(map(key, dr)), f"{len(dw)} vs {len(dr)} ban ghi")

    graph = read_graph(work_dir)
    add("so ban ghi quan he == so canh", len(dw) == graph.number_of_edges(),
        f"{len(dw)} vs {graph.number_of_edges()}")

    if arm == TREATMENT:
        for r in merges:
            add(f"nhom {r.group}: alias da bi xoa", not graph.has_node(r.merge))
            add(f"nhom {r.group}: keep con lai", graph.has_node(r.keep))
        for r in rejects:
            add(f"nhom REJECT {r.group}: ca hai node con lai",
                graph.has_node(r.keep) and graph.has_node(r.merge))
    else:
        for r in merges:
            add(f"control giu nguyen ca hai node cua nhom {r.group}",
                graph.has_node(r.keep) and graph.has_node(r.merge))
    return out


def matrices_equal(dir_a, dir_b):
    da, ma = load_vdb_json(dir_a, "relationships")
    db, mb = load_vdb_json(dir_b, "relationships")
    ka = {d["__id__"]: (d["src_id"], d["tgt_id"]) for d in da}
    kb = {d["__id__"]: (d["src_id"], d["tgt_id"]) for d in db}
    if ka != kb:
        return {"ids_and_meta_equal": False, "max_abs_diff": None}
    ia = {d["__id__"]: i for i, d in enumerate(da)}
    ib = {d["__id__"]: i for i, d in enumerate(db)}
    diff = max(float(np.max(np.abs(ma[ia[i]] - mb[ib[i]]))) for i in ka)
    return {"ids_and_meta_equal": True, "max_abs_diff": diff}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE, help="index goc (control, chi doc)")
    ap.add_argument("--treatment-src", default=DEFAULT_DEST, help="index da gop E1 (chi doc)")
    ap.add_argument("--out", default=DEFAULT_PAIR_ROOT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify-deterministic", action="store_true",
                    help="dung them mot ban thu hai vao <out>_verify roi so vector")
    args = ap.parse_args()

    # Chot an toan: --out khong duoc nam trong (hoac trung) index nguon -- build_arm co xoa thu muc.
    out_abs = os.path.abspath(args.out)
    for label, protected in (("source", args.source), ("treatment-src", args.treatment_src)):
        p = os.path.abspath(protected)
        if out_abs == p or out_abs.startswith(p + os.sep) or p.startswith(out_abs + os.sep):
            raise SystemExit(f"--out ({out_abs}) long nhau voi {label} ({p}) -- tu choi de khong xoa index nguon")

    merges, rejects, _ = load_merge_review(DEFAULT_MERGE_REVIEW)
    src_hash_before = file_sha256(os.path.join(args.source, GRAPHML_NAME))

    embedding_func = build_local_embedding_func()
    arms = {CONTROL: args.source, TREATMENT: args.treatment_src}

    def build_pair(root):
        stats = {}
        for arm, ref in arms.items():
            dest = os.path.join(root, arm)
            print(f"  [{arm}] copy {ref} -> {dest}", flush=True)
            build_arm(ref, dest, force=True)
            print(f"  [{arm}] nhung lai kho quan he, batch = 1 ...", flush=True)
            stats[arm] = asyncio.run(reembed_arm(dest, embedding_func))
            print(f"  [{arm}] xong: {stats[arm]['records']} ban ghi trong {stats[arm]['seconds']}s",
                  flush=True)
        return stats

    if os.path.exists(args.out) and not args.force:
        raise SystemExit(f"da ton tai: {args.out} -- dung --force")
    print(f"dung cap nhanh tai {args.out}")
    stats = build_pair(args.out)

    control_dir = os.path.join(args.out, CONTROL)
    treatment_dir = os.path.join(args.out, TREATMENT)

    checks = []
    checks += arm_invariants(CONTROL, control_dir, args.source, merges, rejects)
    checks += arm_invariants(TREATMENT, treatment_dir, args.treatment_src, merges, rejects)

    cross = cross_arm_check(control_dir, treatment_dir)
    cross_ok = (cross["common_untouched"] > 0
                and cross["min_cosine"] is not None
                and cross["min_cosine"] >= 1 - COSINE_TOL
                and cross["max_abs_diff"] <= MAXDIFF_TOL)
    checks.append({"name": "[cross] vector trung khop tren quan he khong bi E1 dong toi",
                   "passed": cross_ok,
                   "detail": f"n={cross['common_untouched']} min_cosine={cross['min_cosine']} "
                             f"max_abs_diff={cross['max_abs_diff']}"})

    determinism = None
    if args.verify_deterministic:
        vroot = args.out.rstrip("/\\") + "_verify"
        print(f"kiem tat dinh: dung lai lan hai tai {vroot}")
        build_pair(vroot)
        determinism = {arm: matrices_equal(os.path.join(args.out, arm), os.path.join(vroot, arm))
                       for arm in arms}
        for arm, d in determinism.items():
            ok = d["ids_and_meta_equal"] and d["max_abs_diff"] == 0.0
            checks.append({"name": f"[{arm}] chay lai cho vector y het (tat dinh)",
                           "passed": ok,
                           "detail": f"ids/meta={d['ids_and_meta_equal']} max_abs_diff={d['max_abs_diff']}"})
        shutil.rmtree(vroot)

    src_hash_after = file_sha256(os.path.join(args.source, GRAPHML_NAME))
    checks.append({"name": "[source] LiHua-World-qwen-modal khong bi ghi vao",
                   "passed": src_hash_before == src_hash_after, "detail": ""})

    all_pass = all(c["passed"] for c in checks)
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      capture_output=True, text=True).stdout.strip(),
        "policy": {"embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                    "embedding_func": "minirag.llm.hf.hf_embed (khong doi)",
                    "embedding_batch_num": 1,
                    "reembedded_stores": ["relationships"],
                    "untouched_stores": ["entities_name", "chunks", "entities"]},
        "arms": {CONTROL: {"source": args.source, "dir": control_dir, **stats[CONTROL]},
                  TREATMENT: {"source": args.treatment_src, "dir": treatment_dir, **stats[TREATMENT]}},
        "cross_arm": cross,
        "determinism": determinism,
        "checks": checks,
        "status": "PASS" if all_pass else "FAIL",
    }
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "reembed_pair_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    lines = [
        f"Paired deterministic relationship re-embedding -- {report['timestamp']} (commit {report['git_commit'][:10]})",
        f"Chinh sach: {report['policy']['embedding_model']} + hf_embed, batch = {report['policy']['embedding_batch_num']}; "
        f"chi nhung lai kho 'relationships'",
        f"control  : {control_dir} -- {stats[CONTROL]['records']} ban ghi / {stats[CONTROL]['edges']} canh "
        f"({stats[CONTROL]['seconds']}s)",
        f"treatment: {treatment_dir} -- {stats[TREATMENT]['records']} ban ghi / {stats[TREATMENT]['edges']} canh "
        f"({stats[TREATMENT]['seconds']}s)",
        f"quan he chung khong bi E1 dong toi: {cross['common_untouched']} "
        f"(doi noi dung hoac chi co o mot nhanh: {cross['changed_or_absent']})",
        f"  cosine min {cross['min_cosine']} - trung vi {cross['median_cosine']} - max_abs_diff {cross['max_abs_diff']}",
        "",
    ] + [f"{'PASS' if c['passed'] else 'FAIL'}  {c['name']}  {c['detail']}" for c in checks] + [
        "", f"FINAL: {report['status']}"]
    with open(os.path.join(LOG_DIR, "reembed_pair_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines[:6]))
    fails = [c for c in checks if not c["passed"]]
    print(f"\nchecks: {len(checks)} tong, {len(fails)} FAIL")
    for c in fails:
        print("  FAIL", c["name"], c["detail"])
    print(f"STATUS: {report['status']}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
