"""Đọc chunk gốc cho 3 câu Null nghi nhãn sai (kiểm toán Null 15/09/2026)."""
import json, re
raw = json.load(open("LiHua-World-qwen-modal/kv_store_text_chunks.json", encoding="utf-8"))
CASES = [("Cửa sổ 150 × 120 cm", ["150", "120", "window"], ["150", "120", "window", "curtain"]),
         ("Tiệm bánh — sự kiện kỷ niệm + bánh tart", ["anniversary", "tart"], ["tart", "anniversary", "enjoy", "loved"]),
         ("Yuriko — phản hồi demo website (20260312)", ["time: 20260312", "yuriko"], ["demo", "website", "outreach", "morning"])]
for title, must, near in CASES:
    print(f"=== {title}")
    for cid, v in raw.items():
        t = v["content"]; low = t.lower()
        if all(m in low for m in must):
            tm = re.search(r"Time:\s*(\S+)", t)
            print(f"  chunk {tm.group(1) if tm else cid[:12]}:")
            for l in [l.strip() for l in t.split("\n") if l.strip() and any(k in l.lower() for k in near)][:6]:
                print(f"    «{l[:260]}»")
