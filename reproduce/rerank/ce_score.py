"""CE1 — chấm điểm cross-encoder cho mọi cặp (câu hỏi dev, chunk ứng viên B2). Chỉ chấm, không đánh giá.

    .venv/bin/python reproduce/rerank/ce_score.py | tee logs/rerank/ce_score.txt

Tham số ghim trong reproduce/rerank/preregistration/CE1_cross_encoder_pretrained.md TRƯỚC khi chạy file này.
Không đọc Evidence, Type hay đáp án vàng. Không gọi LLM. Không chạm minirag/.
"""
import json, os, sys, time

import torch
from safetensors.torch import load_file
from transformers import AutoConfig, AutoTokenizer, BertForSequenceClassification

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
DEVICE = "cpu"
BATCH = 32
MAXLEN = 512
CTX = os.path.join(ROOT, "logs", "retrieval_audit", "vector_bm25_dev_ctx.jsonl")
CHUNKS = os.path.join(ROOT, "LiHua-World-qwen-modal", "kv_store_text_chunks.json")
OUT = os.path.join(ROOT, "logs", "rerank", "ce1_scores.json")


def load_model():
    """Nạp qua RAM thay vì mmap: from_pretrained làm tiến trình chết SIGBUS với torch 2.14 + transformers 5.16
    trên máy này (xem đăng ký trước). Điểm ra trùng khít bản nạp thường ở máy không lỗi."""
    from huggingface_hub import snapshot_download
    d = snapshot_download(MODEL, revision=REVISION)
    tok = AutoTokenizer.from_pretrained(d)
    sd = {k: v.clone() for k, v in load_file(os.path.join(d, "model.safetensors")).items()}
    model = BertForSequenceClassification(AutoConfig.from_pretrained(d)).eval()
    missing, _ = model.load_state_dict(sd, strict=False)
    assert not missing, missing
    return tok, model.to(DEVICE), d


def windows(chunk_ids, qlen, tok, chunks, cache):
    """MaxP: cửa sổ = 512 - len(q) - 3 wordpiece, bước nhảy = cửa sổ // 2, chồng 50%."""
    w = MAXLEN - qlen - 3
    step = max(1, w // 2)
    out = []
    for cid in chunk_ids:
        if cid not in cache:
            cache[cid] = tok(chunks[cid]["content"], add_special_tokens=False)["input_ids"]
        ids = cache[cid]
        if len(ids) <= w:
            out.append((cid, 0, ids))
            continue
        for k, start in enumerate(range(0, len(ids) - w + step, step)):
            piece = ids[start:start + w]
            if piece:
                out.append((cid, k, piece))
    return out


def main():
    t0 = time.perf_counter()
    tok, model, path = load_model()
    chunks = json.load(open(CHUNKS, encoding="utf-8"))
    recs = [json.loads(l) for l in open(CTX, encoding="utf-8")]
    print(f"{MODEL} @ {REVISION[:12]} · {DEVICE} · lô {BATCH} · MaxP · {len(recs)} câu dev")
    print(f"snapshot: {path}")

    cache, scores, n_win = {}, {}, 0
    t_infer = 0.0
    for n, r in enumerate(recs, 1):
        q = r["question"]
        q_ids = tok(q, add_special_tokens=False)["input_ids"]
        items = windows(r["ranked_ids"], len(q_ids), tok, chunks, cache)
        n_win += len(items)
        best, first = {}, {}
        t = time.perf_counter()
        for i in range(0, len(items), BATCH):
            batch = items[i:i + BATCH]
            enc = tok.pad({"input_ids": [[tok.cls_token_id] + q_ids + [tok.sep_token_id] + p + [tok.sep_token_id]
                                         for _, _, p in batch],
                           "token_type_ids": [[0] * (len(q_ids) + 2) + [1] * (len(p) + 1) for _, _, p in batch]},
                          return_tensors="pt")
            with torch.no_grad():
                logits = model(**{k: v.to(DEVICE) for k, v in enc.items()}).logits.squeeze(-1).float().cpu()
            for (cid, k, _), s in zip(batch, logits.tolist()):
                best[cid] = s if cid not in best else max(best[cid], s)
                if k == 0:
                    first[cid] = s
        t_infer += time.perf_counter() - t
        scores[q] = {"maxp": best, "firstp": first, "n_win": len(items)}
        if n % 25 == 0:
            print(f"   {n}/{len(recs)} câu · {n_win} cửa sổ · {t_infer:.0f}s suy luận")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"model": MODEL, "revision": REVISION, "device": DEVICE, "batch": BATCH,
               "maxlen": MAXLEN, "policy": "MaxP w=512-len(q)-3 stride=w//2",
               "n_windows": n_win, "infer_sec": round(t_infer, 1), "scores": scores},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n{n_win} cửa sổ · suy luận {t_infer:.1f}s = {n_win / t_infer:.0f} cửa sổ/s · "
          f"{t_infer / len(recs):.2f} s/câu ({1000 * t_infer / len(recs):.0f} mili giây) · tổng {time.perf_counter() - t0:.0f}s")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
