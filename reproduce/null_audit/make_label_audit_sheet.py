"""Đ3 — dựng phiếu rà tay 65 nhãn Null: mỗi câu kèm chunk ứng viên, không kèm câu trả lời hay phán quyết nào.

Đăng ký trước: reproduce/null_audit/preregistration/D3_ra_nhan_65_null.md

    .venv/bin/python reproduce/null_audit/make_label_audit_sheet.py

Ra: logs/null_audit/d3_label_audit/{sheet_A.csv, sheet_B.csv}
"""
import csv
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from minirag.bm25 import BM25Index  # noqa: E402

CHUNKS = "LiHua-World-qwen-modal/kv_store_text_chunks.json"
OUT = "logs/null_audit/d3_label_audit"
TOP_BM25 = 10
SHEET_COLS = ["id", "cau_hoi", "bang_chung", "nhan", "doi_mot_chi_tiet", "chunk_id", "trich_dan", "ghi_chu"]


def null_questions():
    rows = list(csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8")))
    return list(dict.fromkeys(r["Question"] for r in rows if r["Type"] == "Null"))


def in_sources():
    """Chunk đã từng vào Sources của bất kỳ nhánh nào — đọc log context nếu có trên máy."""
    seen = {}
    paths = glob.glob("logs/stage_d/*_ctx.jsonl") + glob.glob("logs/screening/*/answers.jsonl")
    for p in paths:
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            q = r.get("query") or r.get("question")
            ids = r.get("chunk_ids") or []
            if q and isinstance(ids, list):
                seen.setdefault(q, set()).update(ids)
    return seen


def best_lines(text, question, n=2):
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) >= 3}
    lines = [l.strip() for l in re.split(r"\n", text) if l.strip() and not l.strip().startswith("Time:")]
    lines.sort(key=lambda l: -sum(w in l.lower() for w in words))
    return lines[:n]


def main():
    questions = null_questions()
    raw = json.load(open(CHUNKS, encoding="utf-8"))
    idx = BM25Index({cid: v["content"] for cid, v in raw.items()})
    sources = in_sources()
    stamp = {cid: (m.group(1) if (m := re.search(r"Time:\s*(\S+)", v["content"])) else cid[:12]) for cid, v in raw.items()}

    rows = []
    for i, q in enumerate(questions, 1):
        cands = list(idx.rank(q, TOP_BM25))
        for cid in sorted(sources.get(q, set())):
            if cid not in cands and cid in raw:
                cands.append(cid)
        block = []
        for cid in cands:
            tag = "BM25" if cands.index(cid) < TOP_BM25 else "đã vào Sources"
            lines = " / ".join(f"«{l[:200]}»" for l in best_lines(raw[cid]["content"], q))
            block.append(f"[{stamp[cid]} · {tag} · {cid}] {lines}")
        rows.append([f"L{i:03d}", q, "\n".join(block), "", "", "", "", ""])

    os.makedirs(OUT, exist_ok=True)
    for name in ("A", "B"):
        with open(f"{OUT}/sheet_{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(SHEET_COLS)
            w.writerows(rows)
    have_src = sum(1 for q in questions if sources.get(q))
    print(f"Đ3 — đã ghi {len(rows)} câu Null vào {OUT}/sheet_A.csv và sheet_B.csv")
    print(f"   mỗi câu: {TOP_BM25} chunk theo BM25" + (f" + chunk đã vào Sources ({have_src}/{len(rows)} câu có log context)" if have_src else ""))
    print("   nhan = KHONG_CO / CO_DU / CO_MOT_PHAN · doi_mot_chi_tiet = CO / KHONG")
    print("   Chấm xong chạy: .venv/bin/python reproduce/null_audit/score_label_audit.py")


if __name__ == "__main__":
    main()
