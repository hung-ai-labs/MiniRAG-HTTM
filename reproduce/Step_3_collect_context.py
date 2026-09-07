"""Step 3 - capture the context MiniRAG retrieves for each question.

Step 1 saves only the final answer, so faithfulness and the context metrics
cannot be computed from it afterwards. This re-runs retrieval with
`only_need_context=True` (no answer generation) and stores the retrieved chunks
alongside the answers Step 1 already produced.

    python reproduce/Step_3_collect_context.py --workingdir ./LiHua-World-gemini
"""

import csv
import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

from tqdm import trange  # noqa: E402
from minirag import QueryParam  # noqa: E402
from gemini_common import build_rag, get_args  # noqa: E402

csv.field_size_limit(10**9)


def parse_sources(context: str, limit: int):
    """Pull the `-----Sources-----` csv block out of MiniRAG's context string.

    Chunks arrive ranked, so the first `limit` are the top-ranked ones. The cap
    matters: RAGAS spends one LLM call per context per sample for context
    precision, and a single query here returns ~90KB of chunks.
    """
    if not context:
        return []
    m = re.search(r"-----Sources-----\s*```csv\s*(.*?)```", context, re.S)
    if not m:
        return []
    rows = list(csv.DictReader(io.StringIO(m.group(1).strip())))
    out = []
    for r in rows:
        c = (r.get("content") or "").strip()
        if c:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def main():
    args = get_args("MiniRAG context capture (Gemini)")
    maxctx = int(os.environ.get("RAGAS_MAX_CONTEXTS", "8"))
    rag = build_rag(args)

    answers = {}
    ans_path = args.outputpath
    if os.path.exists(ans_path):
        with open(ans_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                answers[r["Question"]] = r["minirag"]
    else:
        raise SystemExit(f"Chưa có file câu trả lời: {ans_path} (chạy Step_1 trước)")

    with open(args.querypath, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    out_path = os.path.splitext(ans_path)[0] + "_context.jsonl"

    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["question"])
                except (ValueError, KeyError):
                    pass
        print(f"resuming: {len(done)} câu đã có ngữ cảnh")

    todo = [r for r in rows if r["Question"] not in done]
    print(f"cần thu: {len(todo)} / {len(rows)} câu (tối đa {maxctx} chunk mỗi câu)")

    with open(out_path, "a", encoding="utf-8") as f:
        for i in trange(len(todo)):
            row = todo[i]
            q = row["Question"]
            try:
                ctx = rag.query(
                    q, param=QueryParam(mode="mini", only_need_context=True)
                )
                contexts = parse_sources(ctx, maxctx)
            except Exception as e:
                print("lỗi khi thu ngữ cảnh:", e)
                contexts = []
            f.write(
                json.dumps(
                    {
                        "question": q,
                        "answer": answers.get(q, ""),
                        "ground_truth": row["Gold Answer"],
                        "contexts": contexts,
                        "type": row.get("Type", ""),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.flush()

    print("đã ghi:", out_path)


main()
