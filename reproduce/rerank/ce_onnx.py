"""CE3 — chạy ĐÚNG model CE1 bằng ONNX Runtime trên CPU. Xuất model, chấm lại dev 200, đo độ trễ.

    .venv/bin/python reproduce/rerank/ce_onnx.py | tee logs/rerank/ce3_onnx.txt

Mọi tham số chốt trong reproduce/rerank/preregistration/CE3_cpu_backend.md TRƯỚC khi chạy file này.
Không đổi model, tokenizer, MaxP, kích thước lô. Chỉ CPUExecutionProvider — CoreML bị cấm theo đăng ký trước.
Không đọc Evidence/Type/đáp án vàng. Không gọi LLM.
"""
import json, os, resource, sys, time

import numpy as np
import onnxruntime as ort
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from ce_score import BATCH, CHUNKS, CTX, MODEL, REVISION, load_model, windows  # noqa: E402

ONNX_PATH = os.path.join(ROOT, "logs", "rerank", "ce1_minilm_l6.onnx")
OUT = os.path.join(ROOT, "logs", "rerank", "ce3_onnx_scores.json")
THREADS = 6            # bằng torch.get_num_threads() của lượt CE1 gốc
PROVIDER = "CPUExecutionProvider"
WARMUP = 5


def export(tok, model):
    if os.path.exists(ONNX_PATH):
        print(f"   (dùng lại {os.path.basename(ONNX_PATH)})")
        return
    enc = tok(["a"] * 2, ["b c"] * 2, padding=True, return_tensors="pt")
    torch.onnx.export(
        model, (enc["input_ids"], enc["attention_mask"], enc["token_type_ids"]), ONNX_PATH,
        input_names=["input_ids", "attention_mask", "token_type_ids"], output_names=["logits"],
        dynamic_axes={k: {0: "batch", 1: "seq"} for k in ("input_ids", "attention_mask", "token_type_ids")}
        | {"logits": {0: "batch"}},
        opset_version=17, do_constant_folding=True)
    print(f"   đã xuất {ONNX_PATH} ({os.path.getsize(ONNX_PATH) / 1e6:.1f} MB)")


def session():
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = THREADS
    so.inter_op_num_threads = 1
    return ort.InferenceSession(ONNX_PATH, so, providers=[PROVIDER])


def pct(v, p):
    return sorted(v)[min(len(v) - 1, int(p * len(v)))]


def main():
    print(f"CE3 · {MODEL} @ {REVISION[:12]} · ONNX Runtime {ort.__version__} · {PROVIDER} · "
          f"{THREADS} luồng · lô {BATCH} · MaxP (không đổi)")
    tok, model, _ = load_model()
    export(tok, model)
    del model

    t0 = time.perf_counter()
    sess = session()
    load_ms = 1000 * (time.perf_counter() - t0)
    assert sess.get_providers() == [PROVIDER], sess.get_providers()
    print(f"   nạp session: {load_ms:.0f} ms · provider {sess.get_providers()}")

    chunks = json.load(open(CHUNKS, encoding="utf-8"))
    recs = [json.loads(l) for l in open(CTX, encoding="utf-8")]
    cache, scores, per_q, n_win = {}, {}, [], 0
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    for n, r in enumerate(recs):
        q = r["question"]
        q_ids = tok(q, add_special_tokens=False)["input_ids"]
        items = windows(r["ranked_ids"], len(q_ids), tok, chunks, cache)
        n_win += len(items)
        best = {}
        t = time.perf_counter()
        for i in range(0, len(items), BATCH):
            batch = items[i:i + BATCH]
            enc = tok.pad({"input_ids": [[tok.cls_token_id] + q_ids + [tok.sep_token_id] + p + [tok.sep_token_id]
                                         for _, _, p in batch],
                           "token_type_ids": [[0] * (len(q_ids) + 2) + [1] * (len(p) + 1) for _, _, p in batch]},
                          return_tensors="np")
            out = sess.run(["logits"], {k: v.astype(np.int64) for k, v in enc.items()})[0]
            for (cid, _, _), s in zip(batch, out.reshape(-1).tolist()):
                best[cid] = s if cid not in best else max(best[cid], s)
        dt = 1000 * (time.perf_counter() - t)
        if n >= WARMUP:
            per_q.append(dt)
        scores[q] = best
        if (n + 1) % 50 == 0:
            print(f"   {n + 1}/{len(recs)} câu · {n_win} cửa sổ")

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mb = (rss - rss0) / (1024 ** 2 if sys.platform == "darwin" else 1024)
    print(f"\n=== Độ trễ phần xếp lại, ONNX Runtime CPU (bỏ {WARMUP} câu khởi động, n={len(per_q)})")
    print(f"   p50 {pct(per_q, .5):.0f} ms · p95 {pct(per_q, .95):.0f} ms · max {max(per_q):.0f} ms · "
          f"trung bình {sum(per_q) / len(per_q):.0f} ms")
    print(f"   số câu vượt 3000 ms: {sum(1 for x in per_q if x > 3000)}/{len(per_q)}")
    print(f"   nạp model {load_ms:.0f} ms (đo riêng) · RSS tăng thêm ~{mb:.0f} MB · file ONNX "
          f"{os.path.getsize(ONNX_PATH) / 1e6:.1f} MB")

    json.dump({"model": MODEL, "revision": REVISION, "backend": f"onnxruntime-{ort.__version__}",
               "provider": PROVIDER, "threads": THREADS, "batch": BATCH,
               "policy": "MaxP w=512-len(q)-3 stride=w//2", "n_windows": n_win,
               "load_ms": round(load_ms, 1), "per_q_ms": per_q, "scores": scores},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
