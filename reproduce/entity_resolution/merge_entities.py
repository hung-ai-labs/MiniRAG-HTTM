"""Entity Resolution E1 — hop nhat node trung ten tren graph Qwen da commit.

Doc dac ta day du: docs/phan-cong/THANH_VIEN_2_HOP_NHAT_THUC_THE.md
Danh sach quyet dinh (nguon su that): reproduce/entity_resolution/merge_review.csv
Dang ky truoc:                        reproduce/entity_resolution/preregistration.md

    .venv/Scripts/python.exe reproduce/entity_resolution/merge_entities.py --dry-run
    .venv/Scripts/python.exe reproduce/entity_resolution/merge_entities.py

Script nay CHI doc LiHua-World-qwen-modal/ (--source), khong bao gio ghi vao do.
Toan bo thay doi nam trong ban copy --dest (mac dinh LiHua-World-qwen-entres/).
Khong goi LLM. Embedding dung sentence-transformers/all-MiniLM-L6-v2 cuc bo (giong
het model dung khi dung index goc), chi de nhung lai ~vai chuc ban ghi VDB bi anh
huong boi merge.

PHASE A  load_merge_review + validate_against_graph  (khong ghi gi)
PHASE B  copy_index + snapshot "before"
PHASE C  merge_graph (thao tac tren nx.Graph trong bo nho, ghi lai graphml 1 lan)
PHASE D  rebuild_vdb (delete + upsert qua chinh NanoVectorDBStorage, khong hack JSON)
PHASE E  integrity_checks
PHASE F  ghi merge_report.json / integrity_report.txt / graph_stats_before|after.txt
"""

import argparse
import asyncio
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from graph_stats import norm_key  # noqa: E402  (dung lai dung khoa so trung cua doi soat)

from minirag.prompt import GRAPH_FIELD_SEP  # noqa: E402
from minirag.utils import compute_mdhash_id, split_string_by_multi_markers, EmbeddingFunc  # noqa: E402
from minirag.kg.networkx_impl import NetworkXStorage  # noqa: E402
from minirag.kg.nano_vector_db_impl import NanoVectorDBStorage  # noqa: E402

DEFAULT_SOURCE = os.path.join(ROOT, "LiHua-World-qwen-modal")
DEFAULT_DEST = os.path.join(ROOT, "LiHua-World-qwen-entres")
DEFAULT_MERGE_REVIEW = os.path.join(HERE, "merge_review.csv")
GRAPHML_NAME = "graph_chunk_entity_relation.graphml"
LOG_DIR = os.path.join(ROOT, "logs", "entity_resolution")

# Cac file KHONG duoc dong den (chunk id / noi dung chunk phai giu nguyen 100%).
UNCHANGED_FILES = [
    "kv_store_text_chunks.json",
    "vdb_chunks.json",
    "kv_store_full_docs.json",
    "kv_store_doc_status.json",
    "extracted_chunks.json",
]


# --------------------------------------------------------------------------- Phase A
@dataclass
class MergeGroup:
    group: str
    norm_key: str
    keep: str
    merge: str
    decision: str
    reason: str


def load_merge_review(path=DEFAULT_MERGE_REVIEW):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [MergeGroup(**{k: v for k, v in r.items()}) for r in csv.DictReader(f)]

    unknown = [r for r in rows if r.decision not in ("MERGE", "REJECT")]
    if unknown:
        raise SystemExit(f"decision khong hop le o nhom {[r.group for r in unknown]}")

    merges = [r for r in rows if r.decision == "MERGE"]
    rejects = [r for r in rows if r.decision == "REJECT"]

    alias_to_keep = {}
    for r in merges:
        if r.keep == r.merge:
            raise SystemExit(f"nhom {r.group}: keep == merge ({r.keep!r})")
        if r.merge in alias_to_keep and alias_to_keep[r.merge] != r.keep:
            raise SystemExit(
                f"alias {r.merge!r} map toi hai canonical khac nhau: "
                f"{alias_to_keep[r.merge]!r} va {r.keep!r}"
            )
        alias_to_keep[r.merge] = r.keep

    keeps = {r.keep for r in merges}
    aliases = set(alias_to_keep)
    chained = keeps & aliases
    if chained:
        raise SystemExit(f"chain mapping ngoai du kien: {chained} vua la keep vua la alias o nhom khac")

    return merges, rejects, alias_to_keep


def read_graph(workingdir):
    path = os.path.join(workingdir, GRAPHML_NAME)
    if not os.path.exists(path):
        raise SystemExit(f"khong thay graphml: {path}")
    return nx.read_graphml(path)


def validate_against_graph(graph, merges, rejects):
    """Kiem tra keep/merge co trong graph truoc khi dong vao bat ky thu gi. FAIL FAST."""
    rows = []
    errors = []
    for r in merges:
        k_in, m_in = graph.has_node(r.keep), graph.has_node(r.merge)
        if not k_in:
            errors.append(f"nhom {r.group}: keep {r.keep!r} khong co trong graph")
        if not m_in:
            errors.append(f"nhom {r.group}: merge {r.merge!r} khong co trong graph")
        rows.append(
            {
                "group": r.group,
                "norm_key": r.norm_key,
                "keep": r.keep,
                "merge": r.merge,
                "decision": r.decision,
                "degree_keep": graph.degree(r.keep) if k_in else None,
                "degree_merge": graph.degree(r.merge) if m_in else None,
                "entity_type_keep": graph.nodes[r.keep].get("entity_type") if k_in else None,
                "entity_type_merge": graph.nodes[r.merge].get("entity_type") if m_in else None,
            }
        )
    for r in rejects:
        k_in, m_in = graph.has_node(r.keep), graph.has_node(r.merge)
        if not k_in or not m_in:
            errors.append(f"nhom REJECT {r.group}: thieu node trong graph (keep_in={k_in}, merge_in={m_in})")
        rows.append(
            {
                "group": r.group,
                "norm_key": r.norm_key,
                "keep": r.keep,
                "merge": r.merge,
                "decision": r.decision,
                "degree_keep": graph.degree(r.keep) if k_in else None,
                "degree_merge": graph.degree(r.merge) if m_in else None,
                "entity_type_keep": graph.nodes[r.keep].get("entity_type") if k_in else None,
                "entity_type_merge": graph.nodes[r.merge].get("entity_type") if m_in else None,
            }
        )

    if errors:
        raise SystemExit("VALIDATION FAILED:\n" + "\n".join(errors))
    return rows


def print_dry_run_table(rows):
    cols = ["group", "norm_key", "keep", "merge", "degree_keep", "degree_merge",
            "entity_type_keep", "entity_type_merge", "decision"]
    print(" | ".join(cols))
    for row in rows:
        print(" | ".join(str(row[c]) for c in cols))


# --------------------------------------------------------------------------- Phase B
def file_sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def hash_dir(path):
    """sha256 tat dinh cua toan bo cay file (ten tuong doi + noi dung). Dung de xac nhan
    source index khong bi dong den (CHECK 15)."""
    h = hashlib.sha256()
    for root, _dirs, files in os.walk(path):
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, path).replace(os.sep, "/")
            h.update(rel.encode("utf-8"))
            with open(full, "rb") as fh:
                h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()


def copy_index(source, dest, force):
    if not os.path.isdir(source):
        raise SystemExit(f"source khong ton tai: {source}")
    if os.path.abspath(source) == os.path.abspath(dest):
        raise SystemExit("source va dest trung nhau")
    if os.path.exists(dest):
        if not force:
            raise SystemExit(
                f"dest da ton tai: {dest} -- dung --force de ghi de (chi xoa dest, KHONG dung source)"
            )
        shutil.rmtree(dest)
    shutil.copytree(source, dest)


def get_types_from_graph(graph):
    types, types_case = set(), set()
    for _, data in graph.nodes(data=True):
        t = data.get("entity_type")
        if t is not None:
            types.add(t.lower())
            types_case.add(t)
    return sorted(types), sorted(types_case)


def chunk_count_and_ids(workingdir):
    data = json.load(open(os.path.join(workingdir, "kv_store_text_chunks.json"), encoding="utf-8"))
    return len(data), sorted(data.keys())


def vdb_count(workingdir, namespace):
    p = os.path.join(workingdir, f"vdb_{namespace}.json")
    return len(json.load(open(p, encoding="utf-8"))["data"])


def snapshot(workingdir, source_dir=None):
    g = read_graph(workingdir)
    types, types_case = get_types_from_graph(g)
    n_chunks, chunk_ids = chunk_count_and_ids(workingdir)
    return {
        "workingdir": workingdir,
        "source_dir": source_dir or workingdir,
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "types_lower": types,
        "types_with_case": types_case,
        "chunk_count": n_chunks,
        "chunk_ids_sorted": chunk_ids,
        "vdb_counts": {
            ns: vdb_count(workingdir, ns) for ns in ("entities", "entities_name", "relationships", "chunks")
        },
    }


def write_graph_stats_txt(snap, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"index: {snap['workingdir']}\n")
        f.write(f"node {snap['nodes']} - canh {snap['edges']}\n")
        f.write(f"entity_type (lower) khac nhau: {len(snap['types_lower'])}\n")
        f.write(f"entity_type (with-case) khac nhau: {len(snap['types_with_case'])}\n")
        f.write(f"chunk_count: {snap['chunk_count']}\n")
        f.write(f"vdb_counts: {snap['vdb_counts']}\n")


# --------------------------------------------------------------------------- Phase C
def _split_ids(blob):
    return split_string_by_multi_markers(blob or "", [GRAPH_FIELD_SEP])


def merge_node_attrs(keep_data, alias_data):
    """Hop nhat node attrs. Quyet dinh thiet ke (ghi vao audit, KHONG tai su dung nguyen van
    minirag.operate._merge_nodes_then_upsert cho truong entity_type):

    - description: giong het upstream -- GRAPH_FIELD_SEP.join(sorted(set(hai blob day du))).
      Day la phep noi 2-phan-tu, KHONG tach nho tung cau mo ta ben trong moi blob (upstream
      cung khong tach o buoc nay khi ben "already_node" la mot node da ton tai).
    - source_id: tach ca hai blob thanh tung chunk id roi hop + khu trung + SAP XEP truoc khi
      join. Upstream dung set() tho (thu tu phu thuoc PYTHONHASHSEED, khong tat dinh giua cac
      lan chay) -- day la sai lech CO CHU DICH de dat "deterministic / safe-to-rerun" (yeu cau
      cua thi nghiem nay), khong doi ban chat: moi noi thi tap hop id duoc dung theo id thanh
      vien (set membership), khong noi thu tu.
    - entity_type: mode tren dung 2 gia tri cap-node (keep, alias), moi ben 1 phieu. KHONG bung
      alias thanh nhieu "vote" theo so chunk lich su cua no -- lam vay se bien phep bo phieu
      thanh "ben nao tung gap nhieu chunk hon thi thang", khong phai "mode trong group" nhu tai
      lieu giao viec yeu cau. Vi hai gia tri khac nhau thi luon hoa 1-1, phai co tie-break:
      HOA -> GIU entity_type CUA CANONICAL (keep). Chot 17/09/2026.
      Ly do (khong chon theo thu tu Counter cua upstream): merge hau kiem tren hai node DA TON
      TAI khong co thu tu tu nhien "nodes_data vs already_node" -- ca hai ben deu la node cu,
      viec gan alias vao vai "du lieu moi" la vo can cu. Keep-wins la can thiep toi thieu va
      khong doi answer_type cua chinh node canonical (thu duoc get_node_from_types dung de so
      khop, networkx_impl.py:173). Moi truong hop hoa deu ghi vao audit (type_ties).
    """
    keep_type = keep_data.get("entity_type")
    alias_type = alias_data.get("entity_type")
    if keep_type == alias_type or not alias_type:
        entity_type, tie = keep_type, "same_or_alias_empty"
    elif not keep_type:
        entity_type, tie = alias_type, "keep_empty"
    else:
        entity_type, tie = keep_type, "tie_keep_wins"

    desc_parts = sorted({keep_data.get("description", "") or "", alias_data.get("description", "") or ""} - {""})
    description = GRAPH_FIELD_SEP.join(desc_parts)

    src_ids = sorted(set(_split_ids(keep_data.get("source_id"))) | set(_split_ids(alias_data.get("source_id"))))
    source_id = GRAPH_FIELD_SEP.join(src_ids)

    return {"entity_type": entity_type, "description": description, "source_id": source_id}, tie


def merge_edge_attrs(existing, alias_edge):
    """existing=None -> canh moi (alias co, keep chua co). existing=dict -> collapse (ca hai
    deu co canh toi cung neighbor): weight cong don, description/keywords/source_id noi kieu
    sorted(set(...)) nhu merge_node_attrs (cung ly do tat dinh hoa, xem docstring o tren)."""
    if existing is None:
        weight = alias_edge.get("weight", 1.0)
        desc_parts = sorted({alias_edge.get("description", "") or ""} - {""})
        kw_parts = sorted({alias_edge.get("keywords", "") or ""} - {""})
        src_ids = sorted(set(_split_ids(alias_edge.get("source_id"))))
    else:
        weight = float(existing.get("weight", 0.0)) + float(alias_edge.get("weight", 1.0))
        desc_parts = sorted({existing.get("description", "") or "", alias_edge.get("description", "") or ""} - {""})
        kw_parts = sorted({existing.get("keywords", "") or "", alias_edge.get("keywords", "") or ""} - {""})
        src_ids = sorted(set(_split_ids(existing.get("source_id"))) | set(_split_ids(alias_edge.get("source_id"))))
    return {
        "weight": weight,
        "description": GRAPH_FIELD_SEP.join(desc_parts),
        "keywords": GRAPH_FIELD_SEP.join(kw_parts),
        "source_id": GRAPH_FIELD_SEP.join(src_ids),
    }


def merge_graph(graph, merges):
    """Thao tac tai cho tren nx.Graph. Xu ly tuan tu tung nhom (khong song song): moi nhom doc
    lai trang thai HIEN TAI cua graph (khong dung snapshot tinh tu truoc), nen day chuyen
    alias-alias lien tiep (neu co) van duoc xu ly dung."""
    stats = {"groups": [], "self_loops_removed": 0, "collapsed_edges": 0,
             "touched_pairs": set(), "type_ties": []}

    for r in merges:
        keep, alias = r.keep, r.merge
        if not graph.has_node(alias):
            raise RuntimeError(f"nhom {r.group}: alias {alias!r} da bi xoa truoc do (chain khong mong doi)")
        keep_data = dict(graph.nodes[keep])
        alias_data = dict(graph.nodes[alias])
        merged, tie = merge_node_attrs(keep_data, alias_data)
        graph.nodes[keep].update(merged)
        if tie == "tie_keep_wins":
            stats["type_ties"].append(
                {"group": r.group, "keep": keep, "alias": alias,
                 "keep_type": keep_data.get("entity_type"), "alias_type": alias_data.get("entity_type")}
            )

        for u, v, data in list(graph.edges(alias, data=True)):
            neighbor = v if u == alias else u
            if neighbor == keep:
                stats["self_loops_removed"] += 1
                continue
            existing = dict(graph.edges[keep, neighbor]) if graph.has_edge(keep, neighbor) else None
            if existing is not None:
                stats["collapsed_edges"] += 1
            merged_edge = merge_edge_attrs(existing, data)
            graph.add_edge(keep, neighbor, **merged_edge)
            stats["touched_pairs"].add(frozenset((keep, neighbor)))

        graph.remove_node(alias)
        stats["groups"].append({"group": r.group, "keep": keep, "alias": alias})

    return stats


# --------------------------------------------------------------------------- Phase D
def build_local_embedding_func():
    """Giong het nhanh --embedmodel local cua reproduce/gemini_common.py: cung model, cung
    ham hf_embed (mean pooling tho, khong dung attention_mask -- day la dac diem/hanh vi da
    co san cua index goc, KHONG duoc doi o day de embedding con so sanh duoc)."""
    from transformers import AutoModel, AutoTokenizer
    from minirag.llm.hf import hf_embed

    name = "sentence-transformers/all-MiniLM-L6-v2"
    tokenizer = AutoTokenizer.from_pretrained(name)
    embed_model = AutoModel.from_pretrained(name)
    return EmbeddingFunc(
        embedding_dim=384,
        max_token_size=1000,
        func=lambda texts: hf_embed(texts, tokenizer=tokenizer, embed_model=embed_model),
    )


def open_vdb(workingdir, namespace, meta_fields, embedding_func):
    return NanoVectorDBStorage(
        namespace=namespace,
        global_config={"working_dir": workingdir, "embedding_batch_num": 32,
                        "vector_db_storage_cls_kwargs": {}},
        embedding_func=embedding_func,
        meta_fields=meta_fields,
    )


def resolve_orientations(rel_records, alias_to_keep, live_pairs, keep_set):
    """Chon (src_id, tgt_id) cho tung ban ghi rel- MOI, GIU NGUYEN orientation cua ban ghi cu.

    Chot 17/09/2026: KHONG canonicalize bang sorted(pair). Graph van vo huong; orientation chi
    anh huong toi chuoi content (keywords + src + tgt + description) va tới id
    compute_mdhash_id(src + tgt). Giu orientation cu => ngoai viec thay alias -> keep, van ban
    duoc nhung khong doi gi khac, nen vector moi so sanh duoc voi vector da commit.

    Quy tac chon khi nhieu ban ghi cu gop ve cung mot cap:
      1. Uu tien ban ghi "canonical-existing" -- ban ghi cu khong dinh alias nao (tuc la cap
         (keep, neighbor) von da ton tai truoc merge). Giu y nguyen orientation cua no.
      2. Neu khong co, lay ban ghi nguon dau tien theo thu tu tat dinh (__id__ tang dan) roi
         thay alias -> keep DUNG VI TRI (src o lai o src, tgt o lai o tgt).
      3. Neu khong co ban ghi cu nao (khong nen xay ra: index goc co dung 1 rel- record moi
         canh) -> fallback (keep, neighbor), dem vao 'fallbacks' de bao cao.
    """
    by_pair = {}
    for d in rel_records:
        src, tgt = d.get("src_id"), d.get("tgt_id")
        new_src = alias_to_keep.get(src, src)
        new_tgt = alias_to_keep.get(tgt, tgt)
        if new_src == new_tgt:
            continue  # canh alias-keep: bi bo nhu self-loop, khong co ban ghi ke thua
        pair = frozenset((new_src, new_tgt))
        if pair not in live_pairs:
            continue
        canonical_existing = (src == new_src and tgt == new_tgt)
        by_pair.setdefault(pair, []).append((0 if canonical_existing else 1, d["__id__"], (new_src, new_tgt)))

    orientations, provenance, fallbacks = {}, {"canonical_existing": 0, "alias_inherited": 0, "fallback": 0}, []
    for pair in live_pairs:
        cands = by_pair.get(pair)
        if cands:
            cands.sort()  # (0 truoc 1, roi __id__ tang dan) -> tat dinh
            orientations[pair] = cands[0][2]
            provenance["canonical_existing" if cands[0][0] == 0 else "alias_inherited"] += 1
        else:
            nodes = tuple(pair)
            keep = next((n for n in nodes if n in keep_set), nodes[0])
            other = nodes[0] if nodes[1] == keep else nodes[1]
            orientations[pair] = (keep, other)
            provenance["fallback"] += 1
            fallbacks.append((keep, other))
    return orientations, provenance, fallbacks


async def rebuild_vdb(workingdir, merges, alias_to_keep, touched_pairs, graph, embedding_func):
    ent_vdb = open_vdb(workingdir, "entities", {"entity_name"}, embedding_func)
    ename_vdb = open_vdb(workingdir, "entities_name", {"entity_name"}, embedding_func)
    rel_vdb = open_vdb(workingdir, "relationships", {"src_id", "tgt_id"}, embedding_func)

    alias_set = {r.merge for r in merges}
    counts = {"deletes": {"entities": 0, "entities_name": 0, "relationships": 0},
              "upserts": {"entities": 0, "entities_name": 0, "relationships": 0}}

    # -- entities / entities_name: xoa moi ban ghi cua alias (tim theo entity_name, khong tu
    #    tinh lai id) --
    del_ent = [d["__id__"] for d in ent_vdb.client_storage["data"] if d.get("entity_name") in alias_set]
    del_ename = [d["__id__"] for d in ename_vdb.client_storage["data"] if d.get("entity_name") in alias_set]
    if del_ent:
        await ent_vdb.delete(del_ent)
    if del_ename:
        await ename_vdb.delete(del_ename)
    counts["deletes"]["entities"] = len(del_ent)
    counts["deletes"]["entities_name"] = len(del_ename)

    # -- entities: upsert lai ban ghi ent- cho tung keep (description da doi). Ename- cua keep
    #    KHONG doi (ten keep khong doi) nen khong dong den. --
    ent_upsert = {}
    for r in merges:
        keep = r.keep
        desc = graph.nodes[keep].get("description", "")
        ent_upsert[compute_mdhash_id(keep, prefix="ent-")] = {"content": keep + " " + desc, "entity_name": keep}
    if ent_upsert:
        await ent_vdb.upsert(ent_upsert)
    counts["upserts"]["entities"] = len(ent_upsert)

    # -- relationships: xoa moi ban ghi dung toi alias (src hoac tgt), CONG VOI moi ban ghi cu
    #    cua cap (keep, neighbor) bi thay the (truong hop collapse: keep da co canh nay tu
    #    truoc, gio bi ghi de bang ban ghi moi) --
    all_rel = list(rel_vdb.client_storage["data"])
    keep_set = {r.keep for r in merges}
    # touched_pairs la nhat ky theo thoi diem; cap bi mot nhom merge sau viet lai khong con la
    # canh nao ca -> loai truoc khi giai orientation, neu khong bo dem 'fallback' se bi thoi len.
    live_pairs = {p for p in touched_pairs if graph.has_edge(*tuple(p))}
    orientations, provenance, fallbacks = resolve_orientations(all_rel, alias_to_keep, live_pairs, keep_set)
    counts["orientation_provenance"] = provenance
    counts["orientation_fallbacks"] = [list(p) for p in fallbacks]

    del_rel_ids = []
    for d in all_rel:
        pair = frozenset((d.get("src_id"), d.get("tgt_id")))
        if d.get("src_id") in alias_set or d.get("tgt_id") in alias_set or pair in touched_pairs:
            del_rel_ids.append(d["__id__"])
    if del_rel_ids:
        await rel_vdb.delete(del_rel_ids)
    counts["deletes"]["relationships"] = len(del_rel_ids)

    rel_upsert = {}
    non_sorted = 0
    counts["stale_pairs_skipped"] = len(touched_pairs) - len(live_pairs)
    for pair in live_pairs:
        s, t = orientations[pair]
        data = graph.edges[s, t]
        content = f"{data.get('keywords', '')} {s} {t} {data.get('description', '')}"
        rel_upsert[compute_mdhash_id(s + t, prefix="rel-")] = {"src_id": s, "tgt_id": t, "content": content}
        non_sorted += (s, t) != tuple(sorted((s, t)))
    if rel_upsert:
        await rel_vdb.upsert(rel_upsert)
    counts["upserts"]["relationships"] = len(rel_upsert)
    counts["orientation_not_sorted"] = non_sorted  # so ban ghi khac voi quy uoc sorted() cu

    await ent_vdb.index_done_callback()
    await ename_vdb.index_done_callback()
    await rel_vdb.index_done_callback()
    return counts


# --------------------------------------------------------------------------- Phase E
def integrity_checks(before, after_graph, after_workingdir, merges, rejects,
                      source_hash_before, source_hash_after, touched_pairs):
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": str(detail)})

    after_types, after_types_case = get_types_from_graph(after_graph)
    add("CHECK1 get_types() lower giong het truoc/sau", after_types == before["types_lower"],
        f"before={len(before['types_lower'])} after={len(after_types)}")
    add("CHECK1b get_types() with-case giong het truoc/sau", after_types_case == before["types_with_case"],
        f"before={len(before['types_with_case'])} after={len(after_types_case)}")

    for r in merges:
        add(f"CHECK2 nhom {r.group}: alias {r.merge!r} da bi xoa khoi graph", not after_graph.has_node(r.merge))
        add(f"CHECK2 nhom {r.group}: keep {r.keep!r} con ton tai", after_graph.has_node(r.keep))

    for r in rejects:
        add(f"CHECK3/12 nhom REJECT {r.group}: ca hai node con ton tai (khong bi merge)",
            after_graph.has_node(r.keep) and after_graph.has_node(r.merge))

    # CHECK11/12: phan loai cac nhom trung ten CON LAI sau merge. Ky vong:
    #   approved (thuoc 18 nhom MERGE)  = 0
    #   rejected (thuoc 3 nhom REJECT)  = 3   <- HOP LE, khong phai loi
    #   ngoai whitelist                 = 0
    groups_after = {}
    for n in after_graph:
        groups_after.setdefault(norm_key(n), []).append(n)
    dup_after = {k: v for k, v in groups_after.items() if k and len(v) > 1}
    approved_keys = {r.norm_key for r in merges}
    rejected_keys = {r.norm_key for r in rejects}
    approved_left = sorted(k for k in dup_after if k in approved_keys)
    rejected_left = sorted(k for k in dup_after if k in rejected_keys)
    outside = sorted(k for k in dup_after if k not in approved_keys and k not in rejected_keys)
    add("CHECK11 approved duplicate groups remaining = 0", not approved_left, approved_left)
    add("CHECK12 rejected duplicate groups remaining = 3 (whitelist, hop le)",
        len(rejected_left) == len(rejects), f"{len(rejected_left)}: {rejected_left}")
    add("CHECK12b khong phat sinh duplicate ngoai whitelist", not outside, outside)

    n_chunks, chunk_ids = chunk_count_and_ids(after_workingdir)
    add("CHECK9 chunk count giong het", n_chunks == before["chunk_count"], f"{n_chunks} vs {before['chunk_count']}")
    add("CHECK10 chunk id list (sorted) giong het", chunk_ids == before["chunk_ids_sorted"])

    for name in UNCHANGED_FILES:
        src_file = os.path.join(before["source_dir"], name)
        dst_file = os.path.join(after_workingdir, name)
        same = os.path.exists(src_file) and os.path.exists(dst_file) and file_sha256(src_file) == file_sha256(dst_file)
        add(f"file bat bien giong het source: {name}", same)

    add("CHECK15 source index khong doi (hash cay thu muc)", source_hash_before == source_hash_after)

    dangling = [(u, v) for u, v in after_graph.edges() if u not in after_graph or v not in after_graph]
    add("CHECK13 khong con dangling graph edge", not dangling, dangling[:5])

    ent = json.load(open(os.path.join(after_workingdir, "vdb_entities.json"), encoding="utf-8"))["data"]
    ename = json.load(open(os.path.join(after_workingdir, "vdb_entities_name.json"), encoding="utf-8"))["data"]
    rel = json.load(open(os.path.join(after_workingdir, "vdb_relationships.json"), encoding="utf-8"))["data"]
    alias_set = {r.merge for r in merges}

    bad_ent = [d["__id__"] for d in ent if d.get("entity_name") in alias_set]
    bad_ename = [d["__id__"] for d in ename if d.get("entity_name") in alias_set]
    bad_rel = [d["__id__"] for d in rel if d.get("src_id") in alias_set or d.get("tgt_id") in alias_set]
    add("CHECK4 khong con ent- record tro toi alias", not bad_ent, bad_ent[:5])
    add("CHECK4b khong con Ename- record tro toi alias", not bad_ename, bad_ename[:5])
    add("CHECK5 khong con rel- record co src_id/tgt_id la alias", not bad_rel, bad_rel[:5])

    dangling_rel = [d["__id__"] for d in rel
                    if d.get("src_id") not in after_graph or d.get("tgt_id") not in after_graph]
    add("CHECK14 khong con rel- record tro toi node khong ton tai trong graph", not dangling_rel, dangling_rel[:5])

    # CHECK 6/7/8: hieu chinh theo thuc te index goc (1556 node nhung chi 1425 co ent-/Ename-
    # record -- 131 node "mo côi" duoc tao boi _merge_edges_then_upsert nhu diem cuoi canh, chua
    # bao gio duoc extract_entities upsert VDB rieng). Vi vay KHONG doi hoi moi node deu co
    # record; chi doi hoi KHONG THOAI LUI cho 18 node keep ma ta thuc su dong vao.
    have_ent_after = {d["entity_name"] for d in ent}
    have_ename_after = {d["entity_name"] for d in ename}
    keep_missing_ent = [r.keep for r in merges if r.keep not in have_ent_after]
    keep_missing_ename = [r.keep for r in merges if r.keep not in have_ename_after]
    add("CHECK6 moi keep van co Ename- record", not keep_missing_ename, keep_missing_ename)
    add("CHECK7 moi keep van co ent- record", not keep_missing_ent, keep_missing_ent)

    # touched_pairs la NHAT KY theo thoi diem xu ly: mot cap (keep, neighbor) sinh ra o nhom i
    # co the bi viet lai o nhom j > i neu neighbor chinh la alias cua nhom j. Nhung cap "cu" do
    # khong con la canh trong graph cuoi -- chung khong duoc va khong can co rel- record.
    have_rel_pairs = {frozenset((d.get("src_id"), d.get("tgt_id"))) for d in rel}
    live_touched = [p for p in touched_pairs if after_graph.has_edge(*tuple(p))]
    missing_rel = [tuple(sorted(p)) for p in live_touched if p not in have_rel_pairs]
    add("CHECK8 moi canh bi doi (con ton tai) deu co rel- record", not missing_rel, missing_rel[:5])

    # Bat bien manh hon: trong index goc moi canh co dung 1 rel- record (1509 = 1509). Giu dung
    # bat bien do sau merge.
    graph_pairs = {frozenset((u, v)) for u, v in after_graph.edges()}
    edges_without_record = [tuple(sorted(p)) for p in graph_pairs if p not in have_rel_pairs]
    records_without_edge = [tuple(sorted(p)) for p in have_rel_pairs if p not in graph_pairs]
    add("CHECK8b moi canh trong graph cuoi deu co rel- record", not edges_without_record,
        f"{len(edges_without_record)} canh thieu: {edges_without_record[:5]}")
    add("CHECK8c khong co rel- record mo coi (khong ung voi canh nao)", not records_without_edge,
        f"{len(records_without_edge)} record thua: {records_without_edge[:5]}")
    add("CHECK8d so rel- record == so canh", len(rel) == after_graph.number_of_edges(),
        f"{len(rel)} record vs {after_graph.number_of_edges()} canh")

    return checks


# --------------------------------------------------------------------------- Phase F / main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--merge-review", default=DEFAULT_MERGE_REVIEW)
    ap.add_argument("--dry-run", action="store_true", help="chi kiem mapping, khong copy/khong ghi")
    ap.add_argument("--force", action="store_true", help="cho phep xoa --dest neu da ton tai (KHONG dung source)")
    args = ap.parse_args()

    merges, rejects, alias_to_keep = load_merge_review(args.merge_review)
    print(f"doc {len(merges)} nhom MERGE, {len(rejects)} nhom REJECT tu {args.merge_review}")

    src_graph = read_graph(args.source)
    dry_rows = validate_against_graph(src_graph, merges, rejects)
    print_dry_run_table(dry_rows)

    if args.dry_run:
        print("\nDRY RUN: mapping hop le. Dung o day -- khong copy, khong ghi gi.")
        return

    print(f"\nsao chep {args.source} -> {args.dest} ...")
    source_hash_before = hash_dir(args.source)
    copy_index(args.source, args.dest, args.force)

    before = snapshot(args.dest, source_dir=args.source)
    os.makedirs(LOG_DIR, exist_ok=True)
    write_graph_stats_txt(before, os.path.join(LOG_DIR, "graph_stats_before.txt"))
    print(f"baseline (ban copy, truoc merge): {before['nodes']} node, {before['edges']} canh, "
          f"{before['chunk_count']} chunk, {len(before['types_lower'])} entity_type")

    graph = read_graph(args.dest)
    merge_stats = merge_graph(graph, merges)
    NetworkXStorage.write_nx_graph(graph, os.path.join(args.dest, GRAPHML_NAME))
    print(f"merge_graph: self_loops_removed={merge_stats['self_loops_removed']} "
          f"collapsed_edges={merge_stats['collapsed_edges']} touched_pairs={len(merge_stats['touched_pairs'])} "
          f"type_ties={len(merge_stats['type_ties'])}")

    print("dung embedding cuc bo (all-MiniLM-L6-v2) de nhung lai cac ban ghi bi anh huong ...")
    embedding_func = build_local_embedding_func()
    vdb_stats = asyncio.run(rebuild_vdb(args.dest, merges, alias_to_keep, merge_stats["touched_pairs"], graph, embedding_func))
    print(f"VDB deletes={vdb_stats['deletes']} upserts={vdb_stats['upserts']}")

    after_graph = read_graph(args.dest)  # doc lai tu dia de xac nhan nhung gi thuc su duoc ghi
    after_snapshot = snapshot(args.dest)
    write_graph_stats_txt(after_snapshot, os.path.join(LOG_DIR, "graph_stats_after.txt"))
    source_hash_after = hash_dir(args.source)

    checks = integrity_checks(before, after_graph, args.dest, merges, rejects,
                               source_hash_before, source_hash_after, merge_stats["touched_pairs"])
    all_pass = all(c["passed"] for c in checks)

    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {
        "source_index": args.source,
        "destination_index": args.dest,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": git_commit,
        "merge_groups_requested": [r.__dict__ for r in merges],
        "merge_groups_completed": merge_stats["groups"],
        "rejected_groups_untouched": [r.__dict__ for r in rejects],
        "nodes_before": before["nodes"], "nodes_after": after_snapshot["nodes"],
        "edges_before": before["edges"], "edges_after": after_snapshot["edges"],
        "self_loops_removed": merge_stats["self_loops_removed"],
        "collapsed_edges": merge_stats["collapsed_edges"],
        "type_ties": merge_stats["type_ties"],
        "vdb_deletes": vdb_stats["deletes"],
        "vdb_upserts": vdb_stats["upserts"],
        "orientation_provenance": vdb_stats.get("orientation_provenance"),
        "orientation_fallbacks": vdb_stats.get("orientation_fallbacks"),
        "orientation_not_sorted": vdb_stats.get("orientation_not_sorted"),
        "chunk_count_before": before["chunk_count"],
        "chunk_count_after": after_snapshot["chunk_count"],
        "chunk_ids_equal": before["chunk_ids_sorted"] == after_snapshot["chunk_ids_sorted"],
        "type_pool_equal": before["types_lower"] == after_snapshot["types_lower"],
        "checks": checks,
        "status": "PASS" if all_pass else "FAIL",
    }
    # Canh bao di kem: ket qua cong parity embedding (chay rieng truoc khi gop).
    parity_path = os.path.join(LOG_DIR, "embedding_parity.json")
    if os.path.exists(parity_path):
        p = json.load(open(parity_path, encoding="utf-8"))
        report["embedding_parity"] = {"status": p.get("status"), "message": p.get("message"),
                                       "function_parity": p.get("function_parity"),
                                       "asis_parity_ok": p.get("asis_parity_ok")}
    else:
        report["embedding_parity"] = {"status": "NOT_RUN"}
    with open(os.path.join(LOG_DIR, "merge_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(LOG_DIR, "integrity_report.txt"), "w", encoding="utf-8") as f:
        for c in checks:
            f.write(f"{'PASS' if c['passed'] else 'FAIL'}  {c['name']}  {c['detail']}\n")
        f.write(f"\nFINAL: {'PASS' if all_pass else 'FAIL'}\n")

    print(f"\nSTATUS: {'PASS' if all_pass else 'FAIL'}")
    for c in checks:
        print(("PASS" if c["passed"] else "FAIL"), c["name"], c["detail"])


if __name__ == "__main__":
    main()
