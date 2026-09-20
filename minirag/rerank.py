"""Chế độ thí nghiệm: xếp lại ứng viên bằng cross-encoder tiền huấn luyện (CE1).

TẮT MẶC ĐỊNH. Bật bằng MINIRAG_RERANK=ce1. Khi tắt, không một dòng nào ở đây chạy và đường đi B2 không đổi.

Đăng ký trước: reproduce/rerank/preregistration/CE1_cross_encoder_pretrained.md
Kết quả offline:  logs/rerank/CE1_KET_QUA.md

Bất biến:
- chỉ ĐỔI THỨ TỰ đúng tập ứng viên đã nhận; không thêm, không bớt, không đổi BM25 / vector / RRF / A1@4000;
- không nhãn vàng, không Evidence, không Type, không lời gọi LLM nào;
- hỏng thì NÉM LỖI. Không được âm thầm quay về B2 trong một lượt thí nghiệm — làm vậy là nhiễm bẩn số liệu.
  Quay về B2 nghĩa là TẮT CỜ, không phải giấu lỗi bên trong lượt chạy.
"""
import os
import time

MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
MAXLEN = 512
MODES = ("ce1",)

_STATE = {}


def _load():
    """Nạp state dict vào RAM thay vì mmap: from_pretrained làm tiến trình chết SIGBUS với
    torch 2.14.0 + transformers 5.16.1 trên macOS arm64 (ghi trong đăng ký trước)."""
    if "model" in _STATE:
        return _STATE
    import torch
    from huggingface_hub import snapshot_download
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoTokenizer, BertForSequenceClassification

    path = snapshot_download(MODEL, revision=REVISION)
    tok = AutoTokenizer.from_pretrained(path)
    sd = {k: v.clone() for k, v in load_file(os.path.join(path, "model.safetensors")).items()}
    model = BertForSequenceClassification(AutoConfig.from_pretrained(path)).eval()
    missing, _ = model.load_state_dict(sd, strict=False)
    if missing:
        raise RuntimeError(f"CE1: thiếu trọng số {missing}")
    device = os.environ.get("MINIRAG_RERANK_DEVICE", "cpu").strip() or "cpu"
    _STATE.update(torch=torch, tok=tok, model=model.to(device), device=device,
                  batch=int(os.environ.get("MINIRAG_RERANK_BATCH", "32")))
    return _STATE


def _windows(ids, texts, qlen, tok, cache):
    """MaxP như đăng ký trước: cửa sổ = 512 - len(q) - 3 wordpiece, bước = cửa sổ // 2, lấy điểm lớn nhất."""
    w = MAXLEN - qlen - 3
    if w < 32:
        raise RuntimeError(f"CE1: câu hỏi dài {qlen} wordpiece, không còn chỗ cho chunk")
    step = max(1, w // 2)
    out = []
    for cid in ids:
        if cid not in cache:
            cache[cid] = tok(texts[cid], add_special_tokens=False)["input_ids"]
        t = cache[cid]
        if len(t) <= w:
            out.append((cid, t))
        else:
            out += [(cid, t[s:s + w]) for s in range(0, len(t) - w + step, step) if t[s:s + w]]
    return out


def score(query, ids, texts):
    """Điểm cross-encoder cho từng chunk. Chỉ đọc câu hỏi và nội dung chunk."""
    s = _load()
    torch, tok, model = s["torch"], s["tok"], s["model"]
    q_ids = tok(query, add_special_tokens=False)["input_ids"]
    items = _windows(ids, texts, len(q_ids), tok, {})
    best = {}
    for i in range(0, len(items), s["batch"]):
        batch = items[i:i + s["batch"]]
        enc = tok.pad({"input_ids": [[tok.cls_token_id] + q_ids + [tok.sep_token_id] + p + [tok.sep_token_id]
                                     for _, p in batch],
                       "token_type_ids": [[0] * (len(q_ids) + 2) + [1] * (len(p) + 1) for _, p in batch]},
                      return_tensors="pt")
        with torch.no_grad():
            logits = model(**{k: v.to(s["device"]) for k, v in enc.items()}).logits.squeeze(-1).float().cpu()
        for (cid, _), v in zip(batch, logits.tolist()):
            best[cid] = v if cid not in best else max(best[cid], v)
    if set(best) != set(ids):
        raise RuntimeError(f"CE1: chấm thiếu chunk — {len(best)}/{len(ids)}")
    return best


def rerank(mode, query, ids, texts):
    """Trả (thứ tự mới, mili giây). Hoà điểm giữ nguyên thứ tự RRF đi vào → tất định.

    Mọi lỗi được NÉM RA, không nuốt: một lượt thí nghiệm hỏng phải hỏng to."""
    if mode not in MODES:
        raise ValueError(f"MINIRAG_RERANK không hợp lệ: {mode!r} (hợp lệ: {MODES})")
    t0 = time.perf_counter()
    ids = list(ids)
    s = score(query, ids, texts)
    pos = {c: i for i, c in enumerate(ids)}
    out = sorted(ids, key=lambda c: (-s[c], pos[c]))
    if sorted(out) != sorted(ids):
        raise RuntimeError("CE1: tập ứng viên đã đổi sau khi xếp lại")
    return out, 1000 * (time.perf_counter() - t0)
