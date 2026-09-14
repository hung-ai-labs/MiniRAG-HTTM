"""BM25 Okapi trên kho chunk cho MINIRAG_CHUNK_FUSION=rrf_bm25 (B1) và vector_bm25 (B2).

Đặc tả chốt trong ROADMAP ("BM25 — đăng ký trước hai lượt B1, B2", 14/09/2026) trước khi có code hay kết
quả, KHÔNG tinh chỉnh sau khi thấy kết quả:
- k1 = 1,2; b = 0,75; idf = ln(1 + (N - n + 0,5) / (n + 0,5)).
- Tách từ: chữ thường, `[a-z0-9]+`. Bỏ stopword ở phía câu hỏi theo STOP dưới đây (chép nguyên từ
  reproduce/probe_query_signals.py -- selftest kiểm hai danh sách trùng nhau).
- Truy vấn: nguyên câu hỏi gốc, không dùng parser, không trích ngày.
- Trả tối đa n chunk có điểm > 0; hoà điểm giữ thứ tự chunk trong kho.
"""
import collections
import math
import re

STOP = frozenset((
    "a an the of to in on at for from by with about and or is are was were be been being do does did has have had that this "
    "these those what which who whom whose when where why how whether his her their its he she they it i you we me him them my "
    "your our as into than then there here more most any some all can could would should will may might question"
).split())


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Index:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.ids = list(docs)
        self.tf = [collections.Counter(tokenize(docs[i])) for i in self.ids]
        self.lens = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.lens) / len(self.lens) if self.lens else 0.0
        df = collections.Counter(w for t in self.tf for w in t)
        n_docs = len(self.ids)
        self.idf = {w: math.log(1 + (n_docs - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        self.k1, self.b = k1, b

    def rank(self, query, n):
        terms = [w for w in tokenize(query) if w not in STOP]
        scored = []
        for cid, tf, length in zip(self.ids, self.tf, self.lens):
            s = sum(
                self.idf[w] * tf[w] * (self.k1 + 1)
                / (tf[w] + self.k1 * (1 - self.b + self.b * length / self.avg))
                for w in terms if tf.get(w)
            )
            if s > 0:
                scored.append((s, cid))
        return [c for _, c in sorted(scored, key=lambda x: -x[0])[:n]]
