"""CE1 — đo độ trễ mỗi câu (p50/p95) cho phần xếp lại, CPU và MPS. Không đổi model, không đổi kích thước lô.

    .venv/bin/python reproduce/rerank/ce_latency.py | tee logs/rerank/ce_latency.txt

Độ trễ B2 lấy từ log đã đóng băng (không chạy lại truy hồi). Không gọi sinh, không gọi giám khảo.
"""
import json, os, statistics as st, sys, time

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from ce_score import BATCH, CHUNKS, CTX, MAXLEN, MODEL, REVISION, load_model, windows  # noqa: E402

WARMUP = 5


def pct(v, p):
    return sorted(v)[min(len(v) - 1, int(p * len(v)))]


def run(device, recs, chunks, tok, model):
    model = model.to(device)
    cache, per_q, per_w = {}, [], []
    for n, r in enumerate(recs):
        q_ids = tok(r["question"], add_special_tokens=False)["input_ids"]
        items = windows(r["ranked_ids"], len(q_ids), tok, chunks, cache)
        t = time.perf_counter()
        for i in range(0, len(items), BATCH):
            batch = items[i:i + BATCH]
            enc = tok.pad({"input_ids": [[tok.cls_token_id] + q_ids + [tok.sep_token_id] + p + [tok.sep_token_id]
                                         for _, _, p in batch],
                           "token_type_ids": [[0] * (len(q_ids) + 2) + [1] * (len(p) + 1) for _, _, p in batch]},
                          return_tensors="pt")
            with torch.no_grad():
                model(**{k: v.to(device) for k, v in enc.items()}).logits.squeeze(-1).float().cpu()
        if device == "mps":
            torch.mps.synchronize()
        dt = 1000 * (time.perf_counter() - t)
        if n >= WARMUP:                      # bỏ vài câu đầu: nạp cache tokenizer + khởi động kernel
            per_q.append(dt)
            per_w.append(dt / len(items))
    return per_q, per_w


def main():
    tok, model, _ = load_model()
    chunks = json.load(open(CHUNKS, encoding="utf-8"))
    recs = [json.loads(l) for l in open(CTX, encoding="utf-8") if not json.loads(l).get("none")]
    print(f"{MODEL} @ {REVISION[:12]} · lô {BATCH} · MaxP · {len(recs)} câu dev (bỏ {WARMUP} câu khởi động)\n")

    out = {}
    for device in ("cpu", "mps"):
        if device == "mps" and not torch.backends.mps.is_available():
            print("mps: không có")
            continue
        per_q, per_w = run(device, recs, chunks, tok, model)
        out[device] = per_q
        print(f"=== {device.upper()} — chỉ phần xếp lại, mỗi câu")
        print(f"   p50 {pct(per_q, .5):.0f} ms · p95 {pct(per_q, .95):.0f} ms · trung bình {st.mean(per_q):.0f} ms · "
              f"max {max(per_q):.0f} ms")
        print(f"   mỗi cửa sổ: p50 {pct(per_w, .5):.1f} ms · thông lượng {1000 / st.mean(per_w):.0f} cửa sổ/s\n")

    # B2 đông lạnh: lấy từ log, không chạy lại
    b2 = sorted(json.loads(l)["retrieval_ms"] for l in open(os.path.join(ROOT, "logs", "screening", "b2",
                                                                         "answers.jsonl"), encoding="utf-8"))
    print(f"=== Truy hồi B2 đông lạnh (logs/screening/b2/answers.jsonl, n={len(b2)})")
    print(f"   p50 {pct(b2, .5):.0f} ms · p95 {pct(b2, .95):.0f} ms · trung bình {st.mean(b2):.0f} ms")
    print("   (phần lớn là dựng đường đi đồ thị; BM25 p50 1 ms, p95 3 ms)\n")

    print("=== Tổng truy hồi B2 + cross-encoder (cộng p50 với p50, p95 với p95 — cận trên, hai phần tuần tự)")
    for device, per_q in out.items():
        print(f"   {device}: p50 {pct(b2, .5) + pct(per_q, .5):.0f} ms ({100 * pct(per_q, .5) / pct(b2, .5):+.0f}% so B2) · "
              f"p95 {pct(b2, .95) + pct(per_q, .95):.0f} ms ({100 * pct(per_q, .95) / pct(b2, .95):+.0f}%)")

    if "mps" in out:
        print("\n=== Kiểm MPS có cho cùng thứ hạng như CPU không (quyết định thiết bị runtime)")
        r = recs[0]
        q_ids = tok(r["question"], add_special_tokens=False)["input_ids"]
        items = windows(r["ranked_ids"], len(q_ids), tok, chunks, {})
        sc = {}
        for device in ("cpu", "mps"):
            m = model.to(device)
            best = {}
            for i in range(0, len(items), BATCH):
                batch = items[i:i + BATCH]
                enc = tok.pad({"input_ids": [[tok.cls_token_id] + q_ids + [tok.sep_token_id] + p + [tok.sep_token_id]
                                             for _, _, p in batch],
                               "token_type_ids": [[0] * (len(q_ids) + 2) + [1] * (len(p) + 1) for _, _, p in batch]},
                              return_tensors="pt")
                with torch.no_grad():
                    lg = m(**{k: v.to(device) for k, v in enc.items()}).logits.squeeze(-1).float().cpu()
                for (cid, _, _), s in zip(batch, lg.tolist()):
                    best[cid] = max(best.get(cid, -1e9), s)
            sc[device] = best
        d = max(abs(sc["cpu"][c] - sc["mps"][c]) for c in sc["cpu"])
        o = [sorted(sc[x], key=lambda c: (-sc[x][c], r["ranked_ids"].index(c))) for x in ("cpu", "mps")]
        print(f"   chênh điểm lớn nhất {d:.2e} · thứ hạng {'TRÙNG' if o[0] == o[1] else 'KHÁC'} trên câu mẫu "
              f"({len(items)} cửa sổ)")


if __name__ == "__main__":
    main()
