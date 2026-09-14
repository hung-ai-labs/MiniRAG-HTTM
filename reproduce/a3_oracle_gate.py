"""Cổng từ chối A3 tốt nhất có thể: chọn ngưỡng BẰNG NHÃN (gian lận có chủ đích) trên V3.
Nếu ngay cả ngưỡng này không tăng điểm thì A3 dạng ngưỡng tín hiệu truy hồi là vô vọng."""
import asyncio, collections, csv, statistics as st, sys
sys.path.insert(0, "reproduce"); sys.path.insert(0, ".")
from gemini_common import build_rag, get_args

async def main(args):
    rag = build_rag(args)
    votes, types = collections.defaultdict(list), {}
    for r in csv.DictReader(open("logs/qwen637_v3_judged.csv")):
        votes[r["question"]].append(r["verdict"]); types[r["question"]] = r["type"]
    maj = {q: collections.Counter(v).most_common(1)[0][0] for q, v in votes.items()}
    ans = {r["Question"]: r["minirag"] for r in csv.DictReader(open("logs/qwen637_v3.csv"))}
    gold = {r["Question"]: r["Gold Answer"] for r in csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv"))}

    print("=== Giả định: câu Null mà hệ từ chối thì được chấm 'accurate'? ===")
    null_acc = [q for q in maj if types[q] == "Null" and maj[q] == "accurate"]
    print("gold của câu Null (mẫu):", sorted({gold[q] for q in maj if types[q] == 'Null'})[:4])
    for q in null_acc[:3]:
        print("  accurate ·", ans[q][:130].replace("\n", " "))
    print("  phán quyết đa số nhóm Null V3:", dict(collections.Counter(maj[q] for q in maj if types[q] == "Null")))

    gap = {}
    for q in maj:
        res = await rag.chunks_vdb.query(q, top_k=30)
        s = [float(x["distance"]) for x in res]
        gap[q] = (s[0] - s[1]) if len(s) > 1 else 0.0

    n = len(maj)
    base_acc = sum(v == "accurate" for v in maj.values())
    # Từ chối -> câu Null thành 'accurate', câu có đáp án thành 'neither'.
    def after(t):
        acc = 0
        for q, v in maj.items():
            refused = gap[q] < t
            if refused:
                acc += types[q] == "Null"
            else:
                acc += v == "accurate"
        return acc
    ths = sorted(set(gap.values()))
    best = max(ths + [ths[-1] + 1], key=after)
    print(f"\n=== Cổng 'từ chối nếu top1-top2 < ngưỡng', trên phán quyết đa số V3 ({n} câu) ===")
    print(f"không cổng: acc {100*base_acc/n:.2f}%")
    for q_ in (0.05, 0.10, 0.20, 0.30):
        t = sorted(gap.values())[int(q_ * (n - 1))]
        refused = [q for q in maj if gap[q] < t]
        rn = sum(types[q] == "Null" for q in refused)
        print(f"  từ chối {100*q_:4.0f}% câu (ngưỡng {t:.4f}): {rn} câu Null / {len(refused)-rn} câu có đáp án · acc {100*after(t)/n:.2f}%")
    refused = [q for q in maj if gap[q] < best]
    rn = sum(types[q] == "Null" for q in refused)
    print(f"\nNGƯỠNG TỐT NHẤT (chọn bằng nhãn): {best:.4f} · từ chối {rn} Null / {len(refused)-rn} có đáp án "
          f"· acc {100*after(best)/n:.2f}% (so với {100*base_acc/n:.2f}% không cổng, chênh {after(best)-base_acc:+d} câu)")

asyncio.run(main(get_args("A3 oracle gate")))
