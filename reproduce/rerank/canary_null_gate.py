"""Cổng 5 của CE2 — ba chunk gây nhầm Null đã biết, đo trên chính lượt canary.

    .venv/bin/python reproduce/rerank/canary_null_gate.py | tee logs/rerank/canary_null_gate.txt

Luật tiến cứu (CE2 mục 1, chốt trước khi chạy canary):
    chunk gây nhầm chỉ tính THOÁI LUI nếu reranker ĐẨY NÓ LÊN so với B2 đông lạnh.
    Đã ở hạng 1 trong B2 và vẫn hạng 1  ->  TRUNG TÍNH.
Cổng: ≤ 1 ca THOÁI LUI trong 3 ca.

Không gọi LLM. Chỉ đọc log context của lượt canary và của B2 đông lạnh.
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "retrieval_audit"))
import diagnose as d  # noqa: E402

MISLEAD = {"L002": "20260112_10:00", "L055": "20261113_13:00", "L052": "20260214_16:00"}
CE1 = os.path.join(ROOT, "logs", "retrieval_audit", "ce1_on_dev_ctx.jsonl")
B2 = os.path.join(ROOT, "logs", "retrieval_audit", "vector_bm25_dev_ctx.jsonl")


def main():
    ce = {r["question"]: r for r in (json.loads(l) for l in open(CE1, encoding="utf-8")) if not r.get("none")}
    b2 = {r["question"]: r for r in (json.loads(l) for l in open(B2, encoding="utf-8")) if not r.get("none")}
    sheet = {r["cau_hoi"]: r["id"] for r in csv.DictReader(
        open(os.path.join(ROOT, "logs", "null_audit", "d3_label_audit", "sheet_A.csv"), encoding="utf-8"))}

    print("Cổng 5 (CE2 mục 1) — ba chunk gây nhầm Null đã biết")
    print("   luật: THOÁI LUI chỉ khi bị ĐẨY LÊN so với B2; hạng 1 → hạng 1 là TRUNG TÍNH\n")
    verdicts = {}
    for q, r in ce.items():
        lid = sheet.get(q)
        if lid not in MISLEAD:
            continue
        rk_b = {c: i + 1 for i, c in enumerate(b2[q]["ranked_ids"])}
        rk_a = {c: i + 1 for i, c in enumerate(r["post_rerank_ids"])}
        tgt = next((c for c in b2[q]["ranked_ids"] if (d.ctime(c) or "") == MISLEAD[lid]), None)
        if tgt is None:
            print(f"   {lid}: không có chunk {MISLEAD[lid]} trong ứng viên — bỏ qua")
            continue
        rb, ra = rk_b[tgt], rk_a[tgt]
        v = "THOÁI LUI" if ra < rb else "CẢI THIỆN" if ra > rb else "TRUNG TÍNH"
        verdicts[lid] = v
        print(f"   {lid} ({MISLEAD[lid]}): hạng {rb} → {ra} · Sources "
              f"{'có' if tgt in b2[q]['chunk_ids'] else '—'} → {'có' if tgt in r['chunk_ids'] else '—'} · {v}")
    n = sum(v == "THOÁI LUI" for v in verdicts.values())
    print(f"\n   THOÁI LUI {n}/3 · cổng ≤ 1 → {'ĐẠT' if n <= 1 else 'TRƯỢT'}")
    return 0 if n <= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
