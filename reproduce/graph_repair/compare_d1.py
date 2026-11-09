"""Compare frozen D1 runs to C0 by ordered chunk IDs for all 180 questions."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "logs" / "graph_repair" / "phase1"


def load(name):
    path = PHASE / name / "C0_records.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    result = {row["question"]: row["chunk_ids"] for row in rows}
    if len(rows) != 180 or len(result) != 180:
        raise ValueError(f"Expected 180 unique rows in {path}")
    return result


def main():
    baseline = load("t0_on")
    result = {}
    for name in ("d1_zero", "d1_shuffle"):
        other = load(name)
        if set(other) != set(baseline):
            raise ValueError(f"Question set differs: {name}")
        result[name] = {"different": sum(baseline[q] != other[q] for q in baseline),
                        "total": len(baseline)}
    (PHASE / "d1_comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
