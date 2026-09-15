"""Đo lại cổng thời gian truy hồi của tầng B theo sửa đổi đăng ký trước ngày 15/09/2026 (ROADMAP, commit 30d3485).

    SCREEN_SCRIPT=reproduce/screening/remeasure_latency.py reproduce/screening/run_screen.sh --smoke 3
    SCREEN_SCRIPT=reproduce/screening/remeasure_latency.py reproduce/screening/run_screen.sh

--smoke N: thử đường ống trên N câu dev NGOÀI canary với cache parser tạm (gọi SLM cho N câu). Chỉ in kiểm tra cấu trúc,
không in thời gian, không ghi kết quả. Không có --smoke: lượt đo duy nhất trên 100 câu canary, parser chỉ lấy từ cache.

Mỗi câu dựng context liền nhau cho V3 (rrf), B1 (rrf_bm25), B2 (vector_bm25); câu thứ i dùng [V3, B1, B2] dịch trái i mod 3.
Mỗi chế độ khởi động một lần bằng câu đầu (không tính). T1: trung vị hiệu ghép cặp retrieval_ms (biến thể − V3) ≤ 50 ms;
T2: trung vị bm25_ms ≤ 50 ms. Luật áp đối xứng cho B1 và B2: đạt (và các cổng canary khác đã đạt) → PROMOTE, trượt → STOP.
"""
import argparse, asyncio, json, os, shutil, statistics as st, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import screen_variant as sv  # noqa: E402

MODES = ["v3", "b1", "b2"]
LIMIT_MS = 50.0
PREREG = "30d3485"
OUT_BASE = os.path.join(sv.OUT, "latency_remeasure")


def order_for(i):
    k = i % 3
    return MODES[k:] + MODES[:k]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


async def build(rag, q, mode, cache_only):
    _, rec, ms = await sv.run_query(rag, q, mode, True, cache_only)
    if rec is None:
        return None
    return {"retrieval_ms": rec["retrieval_ms"], "bm25_ms": rec.get("bm25_ms"), "aquery_ms": round(ms, 1),
            "context_sha256": rec["context_sha256"]}


def expected_sha(frozen, answers, variant, q):
    if variant == "v3":
        return frozen[q]["context_sha256"]
    return (answers[variant].get(q) or frozen[q])["context_sha256"]   # câu không đổi context: bằng V3 đông lạnh


def summarize(rows, frozen, answers):
    out = {"v3_sha_match": sum(1 for r in rows if r["v3"] and r["v3"]["context_sha256"] == frozen[r["question"]]["context_sha256"]),
           "v3_built": sum(1 for r in rows if r["v3"])}
    for v in ("b1", "b2"):
        pairs = [r for r in rows if r["v3"] and r[v]]
        diffs = [r[v]["retrieval_ms"] - r["v3"]["retrieval_ms"] for r in pairs]
        bm = [r[v]["bm25_ms"] for r in pairs if r[v]["bm25_ms"] is not None]
        t1, t2 = st.median(diffs), st.median(bm)
        out[v] = {"n": len(pairs), "median_diff_ms": round(t1, 2), "mean_diff_ms": round(st.mean(diffs), 2),
                  "p10_diff_ms": round(pct(diffs, 0.1), 1), "p90_diff_ms": round(pct(diffs, 0.9), 1),
                  "median_bm25_ms": round(t2, 3), "T1": t1 <= LIMIT_MS, "T2": t2 <= LIMIT_MS,
                  "median_retrieval_ms": {m: round(st.median(r[m]["retrieval_ms"] for r in pairs), 1) for m in ("v3", v)},
                  "sha_match": sum(r[v]["context_sha256"] == expected_sha(frozen, answers, v, r["question"]) for r in pairs)}
    return out


def decide(v, s):
    rep = json.load(open(os.path.join(sv.OUT, v, "canary_report.json"), encoding="utf-8"))
    others = {k: ok for k, ok in rep["safety"].items() if "truy hồi" not in k}
    other_ok = (rep["processed"] == 100 and rep["summary"]["net"] >= 1 and rep["summary"]["excluded"] <= 1
                and all(others.values()))
    decision = "PROMOTE" if s["T1"] and s["T2"] and other_ok else "STOP"
    return {"variant": v, "original_decision": rep["decision"], "decision": decision,
            "decision_changed": decision != rep["decision"], "declared_deviation": True,
            "gate": "cổng thời gian truy hồi đo lại (sửa đổi đăng ký trước 15/09/2026)", "prereg_commit": PREREG,
            "T1_median_paired_diff_ms": s["median_diff_ms"], "T1": s["T1"],
            "T2_median_bm25_ms": s["median_bm25_ms"], "T2": s["T2"],
            "other_canary_gates_ok": other_ok, "measured_at": time.strftime("%Y-%m-%d %H:%M")}


async def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--smoke", type=int, default=0)
    own, rest = ap.parse_known_args()
    sys.argv = [sys.argv[0]] + rest
    from gemini_common import build_rag, get_args

    tmp = None
    if own.smoke:
        canary = {r["Question"] for r in sv.question_set("canary")}
        qs = [r["Question"] for r in sv.dev_rows() if r["Question"] not in canary][:own.smoke]
        tmp = tempfile.mkdtemp(prefix="latency_smoke_")
        sv.KW_CACHE = os.path.join(tmp, "kw_cache.jsonl")      # không chạm cache sàng lọc
        cache_only = False
    else:
        if os.path.exists(OUT_BASE + ".json") and os.environ.get("SCREEN_FORCE") != "1":
            sys.exit(f"đã đo ({OUT_BASE}.json) — đăng ký trước chỉ cho đo một lần")
        if subprocess.run(["pgrep", "-f", "Step_1_QA.py|Step_2_evaluate.py"], capture_output=True).returncode == 0:
            sys.exit("đang có tiến trình sinh hoặc chấm chạy — đăng ký trước yêu cầu đo khi không có tải song song")
        qs = [r["Question"] for r in sorted(sv.question_set("canary"), key=lambda r: int(r["order"]))]
        cache_only = True

    caff = subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])
    rag = build_rag(get_args("remeasure_latency"))
    for m in MODES:                                   # khởi động mỗi chế độ, không tính
        await build(rag, qs[0], m, cache_only)
    rows = []
    for i, q in enumerate(qs):
        r = {"i": i, "question": q, "order": order_for(i)}
        for m in r["order"]:
            r[m] = await build(rag, q, m, cache_only)
        rows.append(r)
        if (i + 1) % 10 == 0:
            print(time.strftime("%H:%M"), f"đã đo {i + 1}/{len(qs)} câu", flush=True)

    if own.smoke:
        ok = (all(r[m] is not None and isinstance(r[m]["retrieval_ms"], (int, float)) for r in rows for m in MODES)
              and all(r["v3"]["bm25_ms"] is None and r["b1"]["bm25_ms"] is not None and r["b2"]["bm25_ms"] is not None
                      for r in rows))
        print(f"SMOKE: {len(rows)} câu dev ngoài canary × 3 chế độ · thứ tự {[r['order'] for r in rows]} · "
              f"retrieval_ms / bm25_ms đủ và đúng chế độ: {'ĐẠT' if ok else 'TRƯỢT'} (không in thời gian)", flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
        caff.terminate()
        sys.exit(0 if ok else 1)

    frozen = sv.load_jsonl(sv.FROZEN)
    answers = {v: sv.load_jsonl(os.path.join(sv.OUT, v, "answers.jsonl")) for v in ("b1", "b2")}
    s = summarize(rows, frozen, answers)
    decisions = {v: decide(v, s[v]) for v in ("b1", "b2")}
    json.dump({"prereg_commit": PREREG, "questions": len(qs), "summary": s, "decisions": decisions, "rows": rows},
              open(OUT_BASE + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for v, d in decisions.items():
        json.dump(d, open(os.path.join(sv.OUT, v, "canary_amendment.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    f = sv.fmt
    lines = [f"Đo lại cổng thời gian truy hồi — tầng B (sửa đổi đăng ký trước, commit {PREREG}; lệch đăng ký đã khai báo)",
             f"Đo lúc {time.strftime('%d/%m/%Y %H:%M')} · {len(qs)} câu canary × 3 chế độ liền nhau, thứ tự xoay vòng · "
             "parser chỉ từ cache · caffeinate bật",
             f"Kiểm toàn vẹn: V3 dựng được {s['v3_built']}/{len(qs)}, khớp hash đông lạnh {s['v3_sha_match']}"]
    for v in ("b1", "b2"):
        x, d = s[v], decisions[v]
        lines += [f"{v.upper()} (n = {x['n']}; context khớp báo cáo canary {x['sha_match']}/{x['n']}):",
                  f"- T1 trung vị hiệu ghép cặp retrieval_ms: {x['median_diff_ms']:+.2f} ms "
                  f"(trung bình {x['mean_diff_ms']:+.2f}, p10 {x['p10_diff_ms']:+.1f}, p90 {x['p90_diff_ms']:+.1f}) → "
                  f"{'ĐẠT' if x['T1'] else 'TRƯỢT'} (≤ {f(LIMIT_MS, 0)} ms)",
                  f"- T2 trung vị bm25_ms: {x['median_bm25_ms']:.3f} ms → {'ĐẠT' if x['T2'] else 'TRƯỢT'}",
                  f"- trung vị retrieval_ms: V3 {f(x['median_retrieval_ms']['v3'], 1)} · {v.upper()} "
                  f"{f(x['median_retrieval_ms'][v], 1)} ms",
                  f"- quyết định canary: gốc {d['original_decision']} → sau sửa đổi {d['decision']}"
                  + (" (đổi quyết định — lệch đăng ký)" if d["decision_changed"] else "")]
    open(OUT_BASE + ".txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    caff.terminate()


if __name__ == "__main__":
    asyncio.run(main())
