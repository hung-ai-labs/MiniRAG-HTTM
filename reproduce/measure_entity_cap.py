"""Đo xem trần 5 thực thể thật sự cắt mất bao nhiêu.

Đếm từ log chỉ cho biết câu nào *chạm* trần (45,5% nhóm Multi), không cho biết
LLM định trả về mấy thực thể trước khi `operate.py:1431` cắt `[:5]`. Một câu
hiện lên "5 thực thể" có thể vốn có đúng 5 (không mất gì) hoặc có 9 (mất 4) —
nhìn từ log hai trường hợp giống hệt nhau.

Script này chạy lại **đúng bước trích xuất từ khoá** của `minirag_query`, cùng
prompt, cùng TYPE_POOL lấy từ chính đồ thị, nhưng **không cắt** — rồi ghi lại độ
dài thật. Không đụng vào code production, không chạy truy hồi, không cần judge.

    python reproduce/measure_entity_cap.py --workingdir ./LiHua-World-gemini \
        --questions ./dataset/LiHua-World/qa/query_set.csv

Chi phí: 1 lời gọi/câu (637 lời gọi). Resume được — hết quota thì chạy lại đúng
lệnh cũ, nó bỏ qua phần đã đo.
"""
import asyncio
import csv
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

import json_repair  # noqa: E402
from gemini_common import build_rag, get_args  # noqa: E402
from minirag.prompt import PROMPTS  # noqa: E402

CAP = 5   # hằng số ở operate.py:1431 và :1445

args = get_args("Đo trần thực thể (không cắt)")
args_extra = None
rag = build_rag(args)

qpath = args.questions or args.querypath
rows = list(csv.DictReader(open(qpath, encoding="utf-8")))
if args.limit:
    rows = rows[: args.limit]

out = os.environ.get("ENTITY_CAP_OUT", "./logs/entity_cap.csv")


async def main():
    # TYPE_POOL phải lấy đúng từ đồ thị đang dùng: prompt nhúng danh sách này
    # vào, nên đồ thị khác sẽ cho prompt khác và số đo không so được.
    type_pool, _ = await rag.chunk_entity_relation_graph.get_types()
    tmpl = PROMPTS["minirag_query2kwd"]
    llm = rag.llm_model_func

    done = set()
    if os.path.exists(out) and os.path.getsize(out) > 0:
        with open(out, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                done.add(r["question"])
        print(f"resuming: {len(done)} câu đã đo")

    write_header = not done
    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if write_header:
            w.writerow(["question", "type", "n_full", "n_kept", "n_dropped",
                        "kept", "dropped"])

        todo = [r for r in rows if r["Question"] not in done]
        for i, r in enumerate(todo, 1):
            q = r["Question"]
            try:
                raw = await llm(tmpl.format(query=q, TYPE_POOL=type_pool))
                data = json_repair.loads(raw)
                full = data.get("entities_from_query", [])
                if not isinstance(full, list):
                    full = []
            except Exception as e:
                # Không ghi hàng hỏng: resume ở trên bỏ qua câu đã có trong file,
                # nên ghi vào là lần sau vĩnh viễn không đo lại. Cùng cái bẫy đã
                # làm hỏng lượt chấm 637 câu hôm 11/09.
                print(f"  lỗi ở câu {i}: {e}")
                continue
            kept, dropped = full[:CAP], full[CAP:]
            w.writerow([q, r.get("Type", "?"), len(full), len(kept), len(dropped),
                        json.dumps(kept, ensure_ascii=False),
                        json.dumps(dropped, ensure_ascii=False)])
            fh.flush()
            if i % 20 == 0:
                print(f"  {i}/{len(todo)}")

    report()


def report():
    rows_out = list(csv.DictReader(open(out, encoding="utf-8")))
    if not rows_out:
        print("chưa có dữ liệu")
        return
    import collections
    by_type = collections.defaultdict(list)
    for r in rows_out:
        by_type[r["type"]].append(int(r["n_full"]))

    print(f"\n{'loại':<8}{'n':>5}{'chạm trần':>11}{'BỊ CẮT':>9}{'tb mất':>9}{'max':>6}")
    for t in sorted(by_type):
        v = by_type[t]
        hit = sum(1 for x in v if x >= CAP)
        cut = [x - CAP for x in v if x > CAP]
        print(f"{t:<8}{len(v):>5}{hit / len(v) * 100:>10.1f}%"
              f"{len(cut) / len(v) * 100:>8.1f}%"
              f"{(sum(cut) / len(cut) if cut else 0):>9.2f}{max(v):>6}")
    allv = [x for v in by_type.values() for x in v]
    cut = [x - CAP for x in allv if x > CAP]
    print(f"{'TỔNG':<8}{len(allv):>5}"
          f"{sum(1 for x in allv if x >= CAP) / len(allv) * 100:>10.1f}%"
          f"{len(cut) / len(allv) * 100:>8.1f}%"
          f"{(sum(cut) / len(cut) if cut else 0):>9.2f}{max(allv):>6}")
    print("\n'chạm trần' = đúng 5 hoặc hơn (đây là con số log đọc được).")
    print("'BỊ CẮT'    = thật sự có hơn 5 nên mất thực thể. Đây mới là con số cần.")
    print(f"\nchi tiết: {out}")


if os.environ.get("ENTITY_CAP_REPORT_ONLY"):
    report()
else:
    asyncio.run(main())
