# Retrieval Flow — MiniRAG đi từ Query tới Chunk như thế nào

> Bản đồ khái niệm. Chi tiết File/Function/Input/Output xem
> [`RETRIEVAL_CODE_MAP.md`](RETRIEVAL_CODE_MAP.md).

Toàn bộ luồng nằm trong `mode="mini"`. Hai chế độ `light` và `naive` đi đường khác,
không bàn ở đây.

---

## Sơ đồ tổng

```
Query
  │
  ├─ ① Query Semantic Mapping ──── 1 lời gọi LLM
  │     └─> answer_type_keywords (loại đáp án cần tìm)
  │         entities_from_query  (thực thể trong câu hỏi, TRẦN 5)
  │
  ├─ ② Entity Matching ─────────── vector search trên tên thực thể
  │     └─> mỗi thực thể → top_k node giống nhất + điểm cosine
  │
  ├─ ③ Starting Entities ───────── lọc node cụt
  │     └─> giữ node có ≥1 đường 2-hop; node cụt chỉ giữ 20% điểm cao nhất
  │
  ├─ ④ Candidate Answer Entities ─ quét đồ thị theo entity_type
  │     └─> mọi node có type khớp answer_type_keywords
  │
  ├─ ⑤ Reasoning Path ─────────── chấm điểm đường đi
  │     ├─ cal_path_score_list: đếm node đích nằm trên đường
  │     └─ edge_vote_path:      đếm cạnh (từ vector search) khớp đường
  │
  ├─ ⑥ Topology-Enhanced Retrieval ─ đường đi → chunk
  │     └─> path2chunk: gom chunk của node/cạnh trên đường,
  │         nhân trọng số = điểm đường, giữ top 3 chunk mỗi node
  │
  └─ ⑦ Chunk Retrieval ────────── trộn 2 nguồn rồi chọn cuối
        ├─ nguồn A: chunk từ đồ thị (bước ⑥)
        ├─ nguồn B: vector search thẳng trên chunk, top_k/2
        └─ kwd2chunk: cộng điểm, ×2 cho thực thể khớp nhất,
                      ×10 nếu chunk xuất hiện ở CẢ hai nguồn
                      → lấy top_k/2 chunk cuối cùng
  │
  ▼
Context (Entities CSV + Sources CSV) → 1 lời gọi LLM → Câu trả lời
```

**Tổng cộng 2 lời gọi LLM cho mỗi câu hỏi**: một để phân tích câu hỏi, một để sinh
câu trả lời. Toàn bộ phần giữa là thuật toán thuần, không dùng LLM.

---

## Giải thích từng bước

### ① Query Semantic Mapping

LLM nhận câu hỏi **và danh sách toàn bộ `entity_type` đang có trong đồ thị**, rồi trả
về JSON hai trường:

- `answer_type_keywords` — đáp án nên thuộc loại gì (PERSON, EVENT, DATE...)
- `entities_from_query` — thực thể nào xuất hiện trong câu hỏi

Đây là bước duy nhất "hiểu" câu hỏi. Mọi bước sau chỉ thao tác trên hai danh sách này.

### ② Entity Matching

Mỗi thực thể ở ① được đem đi tìm kiếm vector trên `entity_name_vdb` — kho vector chỉ
chứa **tên** thực thể, không chứa mô tả. Kết quả là các node giống nhất kèm điểm
cosine, dùng làm điểm khởi đầu.

### ③ Starting Entities

Với mỗi node tìm được, lấy toàn bộ hàng xóm trong **2 hop**. Node nào không có đường
đi nào (`Path` rỗng) bị coi là cụt — chỉ **20% node cụt điểm cao nhất** được giữ lại,
phần còn lại loại bỏ.

### ④ Candidate Answer Entities

Quét **toàn bộ đồ thị**, lấy mọi node có `entity_type` nằm trong
`answer_type_keywords`. Đây là tập "đáp án có thể", dùng để chấm điểm đường đi ở ⑤.

Bước này quét tuyến tính toàn đồ thị, không dùng index.

### ⑤ Reasoning Path

Hai vòng chấm điểm cộng dồn:

1. **`cal_path_score_list`** — với mỗi đường đi, **đếm** xem có bao nhiêu node thuộc
   tập ứng viên đáp án (④) nằm trên đó.
2. **`edge_vote_path`** — tìm kiếm vector quan hệ bằng câu hỏi gốc, lấy
   `len(entities) × top_k` cạnh; đường đi nào chứa cạnh đó thì được cộng thêm phiếu.

Điểm cuối của một đường là `score[0] + score[1] + 1`.

### ⑥ Topology-Enhanced Retrieval

`path2chunk` đi ngược từ đường đi về văn bản: mỗi node và mỗi cạnh trên đường đều có
`source_id` trỏ tới chunk gốc. Các chunk đó được gom lại, **nhân trọng số bằng điểm
của đường**, rồi giữ **top 3 chunk** cho mỗi node.

Khi một node có hơn 5 mô tả, `calculate_similarity` (Levenshtein) chọn ra khoảng một
nửa mô tả gần câu hỏi nhất — đây là chỗ duy nhất trong toàn bộ luồng có gì đó **hơi
giống lexical matching**.

### ⑦ Chunk Retrieval

Trộn hai nguồn trong `kwd2chunk`:

| Nguồn | Cách lấy |
|---|---|
| A — đồ thị | chunk từ bước ⑥ |
| B — vector | `chunks_vdb.query(query, top_k/2)` |

Quy tắc cộng điểm **đóng cứng trong code**:

- thực thể khớp đầu tiên được nhân **×2**
- chunk đứng đầu đường đi **và** cũng có trong nguồn B được nhân **×10**

Lấy `top_k/2` chunk điểm cao nhất, đọc nội dung, xuất thành bảng CSV `Sources`.

---

## Điểm nghi ngờ — và một bug đã xác nhận

> ⚠️ **#0 đã được Query Trace xác nhận là bug thật**, xem
> [`QUERY_TRACE.md`](QUERY_TRACE.md). Các điểm còn lại vẫn là nghi ngờ từ đọc code.

**0. Bước ④ luôn trả về 0 ứng viên.** `entity_type` lưu trong đồ thị là chữ HOA
(`"EVENT"`), còn `TYPE_POOL` đưa cho LLM đã bị `.lower()`, nên LLM trả về chữ
thường và `get_node_from_types` so sánh phân biệt hoa/thường → **không bao giờ
khớp**. `get_types()` có trả `TYPE_POOL_w_CASE` nhưng `operate.py` **không dùng**.
Hệ quả: `cal_path_score_list` luôn đếm 0 → cơ chế answer-type-aware của MiniRAG
đang không chạy.

Các điểm còn lại ghi từ lần đọc code `H1`:

1. **Không có lexical matching ở bất kỳ đâu.** Toàn bộ luồng là dense vector +
   topo. Thực thể hiếm, tên riêng lạ, mã số — dense embedding rất dễ trượt.
   → Đây là cơ sở cho giả thuyết `H4` (BM25).
2. **Trần 5 thực thể mỗi câu hỏi** (`entities_from_query[:5]`, đóng cứng). Câu
   multi-hop nhiều thực thể sẽ bị cắt cụt ngay từ bước ①.
3. **Chấm điểm đường đi là phép đếm, không phải đo tương đồng.** Một đường đi qua 3
   node đúng loại nhưng lạc đề vẫn thắng đường đi qua 1 node đúng chính xác.
4. **Hệ số ×2 và ×10 đóng cứng**, không có cơ sở lý thuyết nào trong bài báo.
5. **Bảng `Sources` không bị cắt theo token** như bảng `Entities`. Context có thể
   phình to bất thường → liên quan trực tiếp tới `context_precision 0,316`.
6. **Tập ứng viên đáp án phụ thuộc chất lượng `entity_type` khi index.** Type gán sai
   lúc trích xuất thì bước ④ trả về tập rác, hỏng dây chuyền từ đó trở đi.

### Nối với số liệu baseline


Baseline 442 cho thấy **Multi-hop sai 42,86%** và **Null bịa 31,67%**. Hai con số này
khớp với điểm nghi ngờ **#2** (trần 5 thực thể cắt cụt câu multi-hop) và **#3**
(chấm điểm bằng đếm nên luôn tìm ra "đường tốt nhất" kể cả khi đáp án không tồn tại —
hệ thống không có cơ chế nói "không biết").

Đây là hai giả thuyết nên kiểm chứng đầu tiên bằng Query Trace.
