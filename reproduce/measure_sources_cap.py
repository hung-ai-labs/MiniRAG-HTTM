"""A1: đo bảng Sources phình bao nhiêu, và cắt token thu lại được gì.

Chỉ chạy phần truy hồi (`only_need_context=True`) — **không sinh câu trả lời,
không chấm**. Mỗi câu tốn đúng 1 lời gọi (bước trích xuất từ khoá), nên quét 4
mức ngân sách trên dev set 200 câu tốn ~800 lời gọi thay vì ~3.200 nếu đo đủ
acc/err.

Đây là phép đo Efficiency: bảng kết quả hiện chưa có dòng nào cho nó, mà công
thức đóng góp của nhóm đòi cả Quality lẫn Efficiency.

    python reproduce/measure_sources_cap.py --workingdir ./LiHua-World-gemini \
        --questions ./logs/devset.csv --budgets off,4000,2000,1000

`off` = MINIRAG_TRUNCATE_SOURCES=0, tức đúng hành vi upstream. Nó là mốc so sánh.
"""
import asyncio
import csv
import io
import json
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

from gemini_common import build_rag, get_args  # noqa: E402
from minirag import QueryParam  # noqa: E402
from minirag.utils import encode_string_by_tiktoken  # noqa: E402

args = get_args("Đo cắt token bảng Sources (A1)")
BUDGETS = os.environ.get("SOURCES_BUDGETS", "off,4000,2000,1000").split(",")
OUT = os.environ.get("SOURCES_OUT", "./logs/sources_cap.csv")

rows = list(csv.DictReader(open(args.questions or args.querypath, encoding="utf-8")))
if args.limit:
    rows = rows[: args.limit]


def ntok(s):
    return len(encode_string_by_tiktoken(s or ""))


def split_context(ctx):
    """Tách context thành các khối ```csv``` rồi nhận diện khối theo dòng tiêu đề.

    Không được lấy khối cuối làm Sources: nội dung chunk có xuống dòng và dấu
    phẩy bên trong, nên cắt theo ký tự sẽ ra số bậy. Đọc bằng csv.reader và tìm
    đúng khối có tiêu đề ["id", "content"] (operate.py, bảng Sources).
    """
    out = {}
    for b in ctx.split("```"):
        b = b.strip()
        if not b.startswith("csv"):
            continue
        body = b[3:].strip()
        try:
            rows_ = list(csv.reader(io.StringIO(body)))
        except Exception:
            continue
        if not rows_:
            continue
        head = [c.strip().lower() for c in rows_[0]]
        out["sources" if head == ["id", "content"] else ",".join(head)] = (body, rows_)
    return out


async def main():
    rag = build_rag(args)
    done = set()
    if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            done.add((r["budget"], r["question"]))
        print(f"resuming: {len(done)} phép đo đã có")

    with open(OUT, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not done:
            w.writerow(["budget", "question", "type", "tok_total",
                        "tok_sources", "n_chunks"])
        for b in BUDGETS:
            b = b.strip()
            if b.lower() == "off":
                os.environ["MINIRAG_TRUNCATE_SOURCES"] = "0"
                os.environ.pop("MINIRAG_MAX_TOKEN_TEXT_UNIT", None)
            else:
                os.environ["MINIRAG_TRUNCATE_SOURCES"] = "1"
                os.environ["MINIRAG_MAX_TOKEN_TEXT_UNIT"] = b
            todo = [r for r in rows if (b, r["Question"]) not in done]
            if not todo:
                continue
            print(f"\nngân sách {b}: {len(todo)} câu")
            for i, r in enumerate(todo, 1):
                try:
                    ctx = await rag.aquery(
                        r["Question"],
                        param=QueryParam(mode="mini", only_need_context=True),
                    )
                except Exception as e:
                    print(f"  lỗi câu {i}: {e}")
                    continue          # không ghi -> lượt sau resume sẽ đo lại
                if not isinstance(ctx, str):
                    continue
                blocks = split_context(ctx)
                src, src_rows = blocks.get("sources", ("", []))
                w.writerow([b, r["Question"], r.get("Type", "?"),
                            ntok(ctx), ntok(src), max(0, len(src_rows) - 1)])
                fh.flush()
                if i % 25 == 0:
                    print(f"  {i}/{len(todo)}")
    report()


def report():
    if not os.path.exists(OUT):
        print("chưa có dữ liệu")
        return
    import collections
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(OUT, encoding="utf-8")):
        by[r["budget"]].append((int(r["tok_total"]), int(r["tok_sources"]),
                                int(r["n_chunks"])))
    base = by.get("off")
    print(f"\n{'ngân sách':<11}{'n':>5}{'context tb':>12}{'p90':>8}{'max':>8}"
          f"{'Sources tb':>12}{'chunk tb':>10}{'giảm':>8}")
    for b in by:
        v = by[b]
        tot = statistics.median(x[0] for x in v)
        p90 = sorted(x[0] for x in v)[int(len(v) * 0.9) - 1]
        mx = max(x[0] for x in v)
        srcm = statistics.median(x[1] for x in v)
        chm = statistics.median(x[2] for x in v)
        cut = ""
        if base and b != "off":
            cut = f"{(1 - tot / statistics.median(x[0] for x in base)) * 100:.0f}%"
        print(f"{b:<11}{len(v):>5}{tot:>12.0f}{p90:>8}{mx:>8}{srcm:>12.0f}"
              f"{chm:>10.0f}{cut:>8}")
    print("\n'giảm' = context trung vị giảm bao nhiêu so với upstream (off).")
    print("Cửa sổ SLM Qwen2.5-3B là 32k, nhưng lượt trước đã vỡ ở 16.413 token.")
    print(f"\nchi tiết: {OUT}")


if os.environ.get("SOURCES_REPORT_ONLY"):
    report()
else:
    asyncio.run(main())
