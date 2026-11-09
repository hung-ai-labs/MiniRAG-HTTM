"""B4: so các nhánh P-* (REGISTRATION.md) với C0 đóng băng trên dev 180. Offline. Bản sao đã sửa của compare_phase2.py."""
import json
import statistics
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "reproduce" / "screening"))
from screen_variant import dev_rows, gold_map  # noqa: E402

FROZEN = ROOT / "logs" / "c_ablation" / "graph"
PP = ROOT / "logs" / "graph_repair" / "p_pack"


def records(path):
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r.get("query") or r.get("question"): r for r in rows}


def mcnemar(b, c):
    n, k = b + c, min(b, c)
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


gold = gold_map()
questions = [r["Question"] for r in dev_rows() if r["Question"] in gold]
types = {r["Question"]: r.get("Type", "Single") for r in dev_rows()}


def full(recs):
    return {q: all(g in recs[q].get("chunk_ids", []) for g in gold[q]) for q in questions}


def micro(recs):
    hit = sum(len(set(gold[q]) & set(recs[q].get("chunk_ids", []))) for q in questions)
    return 100 * hit / sum(len(gold[q]) for q in questions)


c0 = records(FROZEN / "C0" / "C0_records.jsonl")
c0_full = full(c0)
out = {}

path = PP / "c0_reg" / "C0_records.jsonl"
if path.exists():
    b = records(path)
    same = sum(c0[q]["chunk_ids"] == b[q]["chunk_ids"] for q in questions)
    print(f"hồi quy c0_reg (công tắc tắt) vs C0 đóng băng: {same}/{len(questions)} chunk_ids giống hệt")
    out["regression_c0_reg"] = same

ARMS = [("C0 (frozen)", FROZEN / "C0" / "C0_records.jsonl"),
        ("P-FF  (đối chứng)", PP / "p_ff" / "C0_records.jsonl"),
        ("P-D1", PP / "p_d1" / "C0_records.jsonl"),
        ("P-D05", PP / "p_d05" / "C0_records.jsonl"),
        ("P-D05F", PP / "p_d05f" / "C0_records.jsonl")]
print(f"\n{'nhánh':18} {'đủ':>8} {'Single':>7} {'Multi':>6} {'micro':>6} {'lên/xuống vs C0':>16} {'p':>7} {'tok tv':>7} {'chunk tv':>8}")
for arm, p in ARMS:
    if not p.exists():
        continue
    recs = records(p)
    f = full(recs)
    up = sum(f[q] and not c0_full[q] for q in questions)
    down = sum(c0_full[q] and not f[q] for q in questions)
    single = sum(f[q] for q in questions if types[q] == "Single")
    multi = sum(f[q] for q in questions if types[q] == "Multi")
    tok = statistics.median(recs[q].get("sources_tok", 0) for q in questions)
    nch = statistics.median(len(recs[q].get("chunk_ids", [])) for q in questions)
    pv = mcnemar(up, down)
    changed = sum(set(recs[q]["chunk_ids"]) != set(c0[q]["chunk_ids"]) for q in questions)
    print(f"{arm:18} {sum(f.values()):>4}/{len(questions)} {single:>7} {multi:>6} {micro(recs):>6.1f} "
          f"{up:>7}/{down:<8} {pv:>7.3g} {tok:>7} {nch:>8}   (tập chunk đổi ở {changed} câu)")
    out[arm] = {"full": sum(f.values()), "single": single, "multi": multi, "micro": round(micro(recs), 2),
                "up": up, "down": down, "p": pv, "median_sources_tok": tok, "median_chunks": nch,
                "questions_with_changed_set": changed,
                "gold_chunks_kept": sum(len(set(gold[q]) & set(recs[q]["chunk_ids"])) for q in questions)}

# so thêm với đối chứng P-FF: phần "xếp lại" tách khỏi phần "lấp ngân sách"
ff = PP / "p_ff" / "C0_records.jsonl"
if ff.exists():
    ff_full = full(records(ff))
    print("\nso với P-FF (tách xếp lại khỏi lấp ngân sách):")
    for arm, p in ARMS[2:]:
        if p.exists():
            f = full(records(p))
            up = sum(f[q] and not ff_full[q] for q in questions)
            down = sum(ff_full[q] and not f[q] for q in questions)
            print(f"  {arm:10} so P-FF: {up} lên / {down} xuống, p = {mcnemar(up, down):.3g}")
            out[arm + " vs P-FF"] = {"up": up, "down": down, "p": mcnemar(up, down)}
(PP / "dev_summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
