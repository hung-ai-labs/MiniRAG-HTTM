"""Dựng lại bảng benchmark chính từ file phán quyết — dùng khi trình bày, để không phải tin số chép tay.

    .venv/bin/python reproduce/demo/bang_benchmark.py

435 câu NGOÀI dev set (dev 200 bị loại để tránh tinh chỉnh trên chính tập đo).
Mỗi cấu hình lấy phán quyết đa số của các lượt chấm; các lượt SINH được báo riêng vì nhiễu sinh lớn hơn nhiễu chấm.
"""
import collections, csv, math, os, statistics as st, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ARMS = {
    "MiniRAG gốc": ["logs/qwen637_fix_judged.csv"],
    "V3 · RRF(đồ thị, vector)": ["logs/qwen637_v3_judged.csv", "logs/qwen637_v3_r2_judged.csv",
                                 "logs/qwen637_v3_r3_judged.csv"],
    "VEC · vector thuần": ["logs/qwen637_vec_judged.csv", "logs/stage_d/vec_s202_judged.csv",
                           "logs/stage_d/vec_s303_judged.csv"],
    "B1 · RRF(đồ thị, vector, BM25)": ["logs/stage_d/b1_s101_judged.csv", "logs/stage_d/b1_s202_judged.csv",
                                       "logs/stage_d/b1_s303_judged.csv"],
    "B2 · RRF(vector, BM25) ← đang dùng": ["logs/stage_d/b2_s101_judged.csv", "logs/stage_d/b2_s202_judged.csv",
                                           "logs/stage_d/b2_s303_judged.csv"],
}


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def main():
    dev = {r["Question"] for r in csv.DictReader(open(os.path.join(ROOT, "logs", "devset.csv"), encoding="utf-8"))}
    types = {r["Question"]: r["Type"] for r in csv.DictReader(
        open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"), encoding="utf-8"))}

    def load(path):
        """Phán quyết đa số giữa các lượt chấm, chỉ lấy câu NGOÀI dev."""
        runs = collections.defaultdict(list)
        for r in csv.DictReader(open(os.path.join(ROOT, path), encoding="utf-8")):
            if r["question"] not in dev:
                runs[r["question"]].append(r["verdict"])
        return {q: collections.Counter(v).most_common(1)[0][0] for q, v in runs.items()}

    data = {name: [load(p) for p in paths] for name, paths in ARMS.items()}
    n = len(next(iter(data["MiniRAG gốc"])))

    print(f"BENCHMARK — {n} câu ngoài dev set · phán quyết đa số các lượt chấm\n")
    print(f"{'Cấu hình':36s} | {'acc':>13s} | {'err':>6s} | {'neither':>7s} | {'Single':>6s} | {'Multi':>5s} | {'Null':>5s}")
    print("-" * 96)
    for name, runs in data.items():
        acc = [100 * sum(v == "accurate" for v in d.values()) / len(d) for d in runs]
        err = [100 * sum(v == "error" for v in d.values()) / len(d) for d in runs]
        nei = [100 * sum(v == "neither" for v in d.values()) / len(d) for d in runs]
        by = {}
        for t in ("Single", "Multi", "Null"):
            vals = []
            for d in runs:
                qs = [q for q in d if types.get(q) == t]
                if qs:
                    vals.append(100 * sum(d[q] == "accurate" for q in qs) / len(qs))
            by[t] = st.mean(vals) if vals else float("nan")
        sd = f" ± {st.stdev(acc):4.2f}" if len(acc) > 1 else "       "
        print(f"{name:36s} | {st.mean(acc):6.2f}{sd} | {st.mean(err):6.2f} | {st.mean(nei):7.2f} | "
              f"{by['Single']:6.2f} | {by['Multi']:5.2f} | {by['Null']:5.2f}")
    print("\n± là sd giữa các LƯỢT SINH (nhiễu sinh 2,09 điểm trên tập này, lớn hơn nhiễu giám khảo 0,30).")

    base = data["MiniRAG gốc"][0]
    print(f"\nMcNemar ghép cặp so với MiniRAG gốc — từng lượt sinh riêng, không gộp")
    for name, runs in data.items():
        if name == "MiniRAG gốc":
            continue
        print(f"\n   {name}")
        for i, d in enumerate(runs, 1):
            qs = [q for q in d if q in base]
            u = sum(d[q] == "accurate" and base[q] != "accurate" for q in qs)
            w = sum(base[q] == "accurate" and d[q] != "accurate" for q in qs)
            print(f"      lượt {i}: {u:3d} sai→đúng / {w:3d} đúng→sai · net {u - w:+4d} · p = {mcnemar(u, w):.3g}")

    print("\n⚠ Nhóm Null đi NGƯỢC ở mọi cấu hình cải tiến — xem docs/CAI_TIEN_VA_BENCHMARK.md mục 5.")


if __name__ == "__main__":
    main()
