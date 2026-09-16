"""Đ3 — dựng phiếu rà tay 65 nhãn Null: mỗi câu kèm chunk ứng viên, không kèm câu trả lời hay phán quyết nào.

Đăng ký trước: reproduce/null_audit/preregistration/D3_ra_nhan_65_null.md

    .venv/bin/python reproduce/null_audit/make_label_audit_sheet.py

Ứng viên lấy theo bốn đường, ghép lại và bỏ trùng (bản cải tiến 16/09/2026 — bản đầu chỉ có BM25 và Sources):
  1. MỐC THỜI GIAN — ngày tháng nhắc trong câu hỏi, khớp với dấu thời gian của chunk
  2. NGƯỜI         — mọi người được nhắc trong câu hỏi cùng xuất hiện trong chunk
  3. BM25          — top 10 trên nguyên văn câu hỏi (cùng cấu hình với B1/B2)
  4. ĐÃ VÀO CONTEXT — chunk từng được đưa vào Sources của bất kỳ nhánh nào

Ra: logs/null_audit/d3_label_audit/{sheet_A.csv, sheet_B.csv}
"""
import collections
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
SHEET_COLS = ["id", "cau_hoi", "bang_chung", "nhan", "doi_mot_chi_tiet", "chunk_id", "trich_dan", "ghi_chu"]
CAPS = {"MỐC THỜI GIAN": 6, "NGƯỜI": 6, "BM25": 10, "ĐÃ VÀO CONTEXT": 6}
YEAR = "2026"                      # toàn bộ corpus LiHua-World nằm trong năm 2026
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
STOPWORDS = {"the", "and", "for", "what", "who", "when", "where", "did", "does", "was", "were", "with", "that", "this",
             "his", "her", "their", "they", "she", "have", "has", "had", "about", "during", "after", "before", "from"}


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in STOPWORDS}


def null_questions():
    rows = list(csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8")))
    return list(dict.fromkeys(r["Question"] for r in rows if r["Type"] == "Null"))


def speakers_of(text):
    return set(re.findall(r"^([A-Za-z][A-Za-z\-]+):", text, re.M))


def name_variants(speaker):
    """'YurikoYamamoto' -> {'yurikoyamamoto', 'yuriko yamamoto', 'yuriko'}; 'ChaeSong-hwa' -> {..., 'chae'}."""
    parts = re.findall(r"[A-Z][a-z\-]*", speaker) or [speaker]
    out = {speaker.lower(), " ".join(p.lower() for p in parts)}
    if len(parts[0]) >= 3:
        out.add(parts[0].lower())
    return out


def dates_in(question):
    """Dấu thời gian YYYYMMDD suy từ ngày tháng nhắc trong câu hỏi; ngày trần ('the 9th') trả về hậu tố MMDD rỗng."""
    q = question.lower()
    full, day_only = set(), set()
    for m in re.finditer(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?", q):
        full.add(f"{m.group(3) or YEAR}{MONTHS.index(m.group(1)) + 1:02d}{int(m.group(2)):02d}")
    for m in re.finditer(r"(\d{1,2})(?:st|nd|rd|th)\s+of\s+(" + "|".join(MONTHS) + r")", q):
        full.add(f"{YEAR}{MONTHS.index(m.group(2)) + 1:02d}{int(m.group(1)):02d}")
    for m in re.finditer(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", q):
        day_only.add(f"{int(m.group(1)):02d}")
    return full, day_only


def in_sources():
    """Chunk đã từng vào Sources của bất kỳ nhánh nào — đọc log context nếu có trên máy."""
    seen = collections.defaultdict(set)
    for p in glob.glob("logs/stage_d/*_ctx.jsonl") + glob.glob("logs/screening/*/answers.jsonl"):
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            q, ids = r.get("query") or r.get("question"), r.get("chunk_ids") or []
            if q and isinstance(ids, list):
                seen[q].update(ids)
    return seen


def best_lines(text, words, n=3):
    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("Time:")]
    scored = sorted(lines, key=lambda l: -len(words & content_words(l)))
    return [l for l in scored[:n] if words & content_words(l)] or lines[:1]


def main():
    questions = null_questions()
    raw = json.load(open(CHUNKS, encoding="utf-8"))
    idx = BM25Index({cid: v["content"] for cid, v in raw.items()})
    sources = in_sources()
    stamp, speakers, words_of = {}, {}, {}
    for cid, v in raw.items():
        t = v["content"]
        m = re.search(r"Time:\s*(\S+)", t)
        stamp[cid] = m.group(1) if m else cid[:12]
        speakers[cid] = speakers_of(t)
        words_of[cid] = content_words(t)
    variants = {sp: name_variants(sp) for sp in set().union(*speakers.values())}

    rows, stats = [], collections.Counter()
    for i, q in enumerate(questions, 1):
        qw = content_words(q)
        ql = q.lower()
        groups = collections.OrderedDict()

        named = {sp for sp, vs in variants.items() if any(re.search(rf"\b{re.escape(v)}\b", ql) for v in vs)}
        full, day_only = dates_in(q)
        by_time = [c for c in raw if any(stamp[c].startswith(d) for d in full)]
        if not by_time and day_only:
            # "ngày 9" không kèm tháng khớp 12 ngày trong năm -> siết thêm bằng người được nhắc trong câu hỏi
            by_time = [c for c in raw if any(stamp[c][6:8] == d for d in day_only) and (not named or named <= speakers[c])]
        groups["MỐC THỜI GIAN"] = sorted(by_time, key=lambda c: -len(qw & words_of[c]))

        by_name = [c for c in raw if named and named <= speakers[c]]
        groups["NGƯỜI"] = sorted(by_name, key=lambda c: -len(qw & words_of[c]))

        groups["BM25"] = list(idx.rank(q, CAPS["BM25"]))
        groups["ĐÃ VÀO CONTEXT"] = sorted((c for c in sources.get(q, ()) if c in raw),
                                          key=lambda c: -len(qw & words_of[c]))

        block, seen = [], set()
        for label, cands in groups.items():
            picked = [c for c in cands if c not in seen][:CAPS[label]]
            seen.update(picked)
            if picked:
                stats[label] += 1
                block.append(f"--- {label} ---")
                for c in picked:
                    lines = " / ".join(f"«{l[:220]}»" for l in best_lines(raw[c]["content"], qw))
                    block.append(f"[{stamp[c]} · {', '.join(sorted(speakers[c])) or '?'} · {c}] {lines}")
        rows.append([f"L{i:03d}", q, "\n".join(block), "", "", "", "", ""])
        stats["tổng chunk"] += len(seen)

    os.makedirs(OUT, exist_ok=True)
    for name in ("A", "B"):
        with open(f"{OUT}/sheet_{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(SHEET_COLS)
            w.writerows(rows)
    print(f"Đ3 — đã ghi {len(rows)} câu Null vào {OUT}/sheet_A.csv và sheet_B.csv")
    for label in CAPS:
        print(f"   {label:16s}: có ứng viên ở {stats[label]:2d}/{len(rows)} câu")
    print(f"   trung bình {stats['tổng chunk'] / len(rows):.1f} chunk mỗi câu")
    print("   nhan = KHONG_CO / CO_DU / CO_MOT_PHAN · doi_mot_chi_tiet = CO / KHONG")
    print("   Chấm xong chạy: .venv/bin/python reproduce/null_audit/score_label_audit.py")


if __name__ == "__main__":
    main()
