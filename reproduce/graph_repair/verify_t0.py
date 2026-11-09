"""Compare both fresh C0 runs with the frozen 180-question baseline."""
import argparse
import json
from pathlib import Path


def read(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
    by_question = {row["question"]: row["chunk_ids"] for row in rows}
    if len(rows) != 180 or len(by_question) != 180:
        raise ValueError(f"{path}: expected 180 unique questions, got {len(rows)}/{len(by_question)}")
    return by_question


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", required=True)
    ap.add_argument("--off", required=True)
    ap.add_argument("--on", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    frozen = read(args.frozen)
    result = {}
    for label, path in (("off", args.off), ("on", args.on)):
        current = read(path)
        diffs = [q for q, ids in frozen.items() if current.get(q) != ids]
        result[label] = {"matching": 180 - len(diffs), "total": 180, "different_questions": diffs}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if any(item["matching"] != 180 for item in result.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
