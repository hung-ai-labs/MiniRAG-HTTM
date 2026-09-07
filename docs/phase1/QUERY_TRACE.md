# Query Trace — ba câu hỏi thật đi qua MiniRAG

> Sinh tự động bởi `reproduce/Step_5_trace.py`. Mỗi bước được bọc tại chỗ quanh hàm thật, không viết lại logic.

> Xem [`RETRIEVAL_CODE_MAP.md`](RETRIEVAL_CODE_MAP.md) để biết mỗi bước nằm ở file/hàm nào.

## Query: Did Adam Smith send Li Hua a reminder about the upcoming rent due date before Li Hua sent a message about having already transferred the rent on 20260301?

- **Gold answer:** Yes
- **Verdict baseline:** `error`

### ② Entity Matching

**`Adam Smith`** → 60 node (top_k=60)

| node khớp | cosine |
|---|---|
| "ADAM SMITH" | 0.9240000247955322 |
| "ADAMSMITH" | 0.6079999804496765 |
| "MR. SMITH" | 0.5649999976158142 |
| "ALEX" | 0.4580000042915344 |
| "JOHN DENVER" | 0.43299999833106995 |
| "JAKEWATSON" | 0.41999998688697815 |
| "PHIL FODEN" | 0.41200000047683716 |
| "NEIL PEART" | 0.36399999260902405 |

**`Li Hua`** → 60 node (top_k=60)

| node khớp | cosine |
|---|---|
| "LI HUA" | 0.9240000247955322 |
| "LIHUA" | 0.652999997138977 |
| "LALIGA" | 0.41499999165534973 |
| "EL CLÁSICO" | 0.3869999945163727 |
| "EL CLASICO" | 0.3529999852180481 |
| "DECLAN RICE" | 0.3490000069141388 |
| "PHOENIX" | 0.3479999899864197 |
| "CINQUE TERRE" | 0.3440000116825104 |

**`rent due date`** → 5 node (top_k=60)

| node khớp | cosine |
|---|---|
| "APARTMENT" | 0.3140000104904175 |
| "THE APARTMENT" | 0.2919999957084656 |
| "SATURDAY AT 3 PM" | 0.24400000274181366 |
| "GARDEN RENOVATIONS" | 0.21400000154972076 |
| "3:00 PM" | 0.20900000631809235 |

**`rent transfer`** → 2 node (top_k=60)

| node khớp | cosine |
|---|---|
| "APARTMENT" | 0.2939999997615814 |
| "THE APARTMENT" | 0.28700000047683716 |

**`20260301`** → 29 node (top_k=60)

| node khớp | cosine |
|---|---|
| "20260107_15:00" | 0.6790000200271606 |
| "20260523_08:30" | 0.6779999732971191 |
| "20260503_08:29" | 0.6620000004768372 |
| "20260711_11:00" | 0.6499999761581421 |
| "20261103_13:00" | 0.6420000195503235 |
| "20260529_08:30" | 0.640999972820282 |
| "20260509_08:28" | 0.6330000162124634 |
| "20260419_08:13" | 0.6299999952316284 |

### ③ Starting Entities

146 node mở rộng 2-hop · **9 node cụt** (không đường đi nào) · 137 node có đường

| node | số đường 2-hop |
|---|---|
| "ADAM SMITH" | 34 |
| "ADAMSMITH" | 760 |
| "MR. SMITH" | 299 |
| "ALEX" | 39 |
| "JOHN DENVER" | 50 |
| "JAKEWATSON" | 506 |
| "PHIL FODEN" | 13 |
| "NEIL PEART" | 108 |
| "SIR ALEX FERGUSON" | 23 |
| "JOHN KRASINSKI" | 1 |
| "JARED HARRIS" | 1 |
| "AMOS" | 312 |

### ④ Candidate Answer Entities

- Loại đáp án LLM đoán: `['"event"', '"person"']`
- Ứng viên tìm được: **0** node
- Ví dụ: 

### ⑤ Reasoning Path

- Chấm điểm: 138 thực thể · **22879 đường đi**
- Bỏ phiếu cạnh: 23 cạnh liên quan → **971 đường được cộng phiếu**

### ⑥ Topology-Enhanced Retrieval

`max_chunks=3` mỗi thực thể

| thực thể | chunk lấy ra |
|---|---|
| "ADAM SMITH" | chunk-9797572cb3, chunk-d368374bf6, chunk-5db7772f06 |
| "ADAMSMITH" | chunk-3859cde608, chunk-97ca5f171e, chunk-f2e9e4e568 |
| "MR. SMITH" | chunk-7697feea03 |
| "ALEX" | chunk-fade220263, chunk-295e2ee406, chunk-0a0e37c955 |
| "JOHN DENVER" | chunk-b356ab5775 |

### ⑦ Chunk Retrieval

- Lấy cuối cùng: **30** chunk (chunk_nums=30)
- ID: chunk-5db7772f06, chunk-9797572cb3, chunk-d368374bf6, chunk-d3c725aafc, chunk-3859cde608, chunk-97ca5f171e, chunk-f2e9e4e568, chunk-5b8c1f45d4, chunk-c58293201e, chunk-41a71a4d9c

### Câu trả lời sinh ra

> Based on the provided communication records, Adam Smith did not send Li Hua a rent reminder on that specific timeline, nor is there any record of a message on March 1, 2026. The sources show that Adam Smith sent a message reminding Li Hua about the rent later in the year, specifically on April 29, 2026, and another rent-related check-in on June 1, 2026.   Additionally, Li Hua's interactions with Adam Smith throughout the provided logs cover various topics—such as neighborhood potluck preparations, maintenance requests for door hinges and water tabs, apartment updates, and basement air-conditioning installations—but do not include a rent transfer message or reminder matching the specific dat…


---

## Query: What type of feedback did Li Hua provide to Chae regarding the community medical knowledge lecture, and what is Wolfgang's role in the band rehearsal?

- **Gold answer:** Insufficient information
- **Verdict baseline:** `error`

### ② Entity Matching

**`Li Hua`** → 60 node (top_k=60)

| node khớp | cosine |
|---|---|
| "LI HUA" | 0.9240000247955322 |
| "LIHUA" | 0.652999997138977 |
| "LALIGA" | 0.41499999165534973 |
| "EL CLÁSICO" | 0.3869999945163727 |
| "EL CLASICO" | 0.3529999852180481 |
| "DECLAN RICE" | 0.3490000069141388 |
| "PHOENIX" | 0.3479999899864197 |
| "CINQUE TERRE" | 0.3440000116825104 |

**`Chae`** → 60 node (top_k=60)

| node khớp | cosine |
|---|---|
| "CHAE" | 0.7990000247955322 |
| "CHAE SONG-HWA" | 0.5509999990463257 |
| "CHAESONG-HWA" | 0.46799999475479126 |
| "CHAESONG-HWA'S TEAM" | 0.41600000858306885 |
| "BRIAR" | 0.367000013589859 |
| "GETAFE" | 0.3499999940395355 |
| "KEVIN DE BRUYNE" | 0.3310000002384186 |
| "PEP GUARDIOLA" | 0.32199999690055847 |

**`community medical knowledge lecture`** → 40 node (top_k=60)

| node khớp | cosine |
|---|---|
| "COMMUNITY MEDICAL KNOWLEDGE LECTURE" | 0.9340000152587891 |
| "MEDICAL LECTURE" | 0.6480000019073486 |
| "WEB DESIGN SEMINAR" | 0.3720000088214874 |
| "FITNESS DISCUSSION GROUP" | 0.33399999141693115 |
| "SPEECH THERAPY STUDIO" | 0.32899999618530273 |
| "TRAINING SESSION" | 0.3089999854564667 |
| "BRAINSTORMING SESSION" | 0.2939999997615814 |
| "SPECIAL WEEKEND GYM CLASS" | 0.27900001406669617 |

**`Wolfgang`** → 60 node (top_k=60)

| node khớp | cosine |
|---|---|
| "WOLFGANG" | 0.8180000185966492 |
| "WOLFGANGSCHULZ" | 0.7250000238418579 |
| "WOLFGANGSCHULZ": | 0.7149999737739563 |
| "WOLFGANGSCHULZ'S PROMOTION CELEBRATION" | 0.49900001287460327 |
| "BRUNO FERNANDES" | 0.4650000035762787 |
| "BORIS SHCHERBINA" | 0.4390000104904175 |
| "IVOR" | 0.42100000381469727 |
| "KIERAN" | 0.4059999883174896 |

**`band rehearsal`** → 60 node (top_k=60)

| node khớp | cosine |
|---|---|
| "BAND GATHERING" | 0.5929999947547913 |
| "CONCERT" | 0.5740000009536743 |
| "THE BAND" | 0.5479999780654907 |
| "MUSIC FESTIVAL" | 0.4909999966621399 |
| "BAND" | 0.4830000102519989 |
| "SUNDAY EVENING JAM SESSION" | 0.48100000619888306 |
| "LOCAL MUSIC FESTIVAL" | 0.47699999809265137 |
| "MUSIC GROUP" | 0.4440000057220459 |

### ③ Starting Entities

220 node mở rộng 2-hop · **16 node cụt** (không đường đi nào) · 204 node có đường

| node | số đường 2-hop |
|---|---|
| "LI HUA" | 367 |
| "LIHUA" | 2001 |
| "LALIGA" | 10 |
| "EL CLÁSICO" | 0 |
| "EL CLASICO" | 4 |
| "DECLAN RICE" | 13 |
| "PHOENIX" | 465 |
| "CINQUE TERRE" | 107 |
| "HONG KONG" | 406 |
| "PREMIER LEAGUE" | 13 |
| "MACHU PICCHU" | 0 |
| "TALI" | 27 |

### ④ Candidate Answer Entities

- Loại đáp án LLM đoán: `['concept', 'person', 'event']`
- Ứng viên tìm được: **0** node
- Ví dụ: 

### ⑤ Reasoning Path

- Chấm điểm: 207 thực thể · **56159 đường đi**
- Bỏ phiếu cạnh: 188 cạnh liên quan → **11164 đường được cộng phiếu**

### ⑥ Topology-Enhanced Retrieval

`max_chunks=3` mỗi thực thể

| thực thể | chunk lấy ra |
|---|---|
| "LI HUA" | chunk-a361f8bd75, chunk-5db7772f06, chunk-a89ea36ebe |
| "LIHUA" | chunk-312e618ed3, chunk-6ed7071e50, chunk-bd4fb9fc92 |
| "LALIGA" | chunk-d7974f7459 |
| "EL CLASICO" | chunk-ec5dfa1e07 |
| "DECLAN RICE" | chunk-54f91257a1 |

### ⑦ Chunk Retrieval

- Lấy cuối cùng: **30** chunk (chunk_nums=30)
- ID: chunk-f349d26bb0, chunk-8be0a55ff4, chunk-e494b420c9, chunk-26fe61ec68, chunk-6ed7071e50, chunk-17565139d2, chunk-5c8daddc3c, chunk-8f190cae08, chunk-f47d4d9064, chunk-753746ca57

### Câu trả lời sinh ra

> Li Hua provided very positive and insightful feedback to Chae regarding her community medical knowledge lecture. After attending the event, Li Hua expressed appreciation for how insightful the presentation was, specifically noting that she learned a lot about the latest advancements in neurosurgery. Furthermore, Li Hua complimented Chae's presentation style, mentioning that it made complex medical topics easy to understand and encouraging her to keep up the great work.  Within the context of their band, "The Jolly Band," Wolfgang Schulz plays a vital role as the drummer. Known for bringing a steady beat and high energy to their practice sessions, Wolfgang values keeping their jam sessions f…


---

## Query: What does Bronwyn think about the idea of stealth missions?

- **Gold answer:** it will be all about timing and communication
- **Verdict baseline:** `accurate`

### ② Entity Matching

**`Bronwyn`** → 60 node (top_k=60)

| node khớp | cosine |
|---|---|
| "BRONWYN" | 0.7639999985694885 |
| "BRIENNE" | 0.4309999942779541 |
| "JAIME LANNISTER" | 0.4009999930858612 |
| "TYRION LANNISTER" | 0.3970000147819519 |
| "WESTEROS" | 0.37400001287460327 |
| "TYWIN" | 0.37299999594688416 |
| "CHAESONG-HWA'S TEAM" | 0.36000001430511475 |
| "KEVIN DE BRUYNE" | 0.3569999933242798 |

**`stealth missions`** → 51 node (top_k=60)

| node khớp | cosine |
|---|---|
| "BOUNTY HUNTERS" | 0.3230000138282776 |
| "ROBOT UPRISING" | 0.30399999022483826 |
| "STRANGER THINGS" | 0.30300000309944153 |
| "CALL OF DUTY 4: MODERN WARFARE" | 0.2980000078678131 |
| "ASSASSIN'S CREED VALHALLA" | 0.289000004529953 |
| "PEACEKEEPERS" | 0.2879999876022339 |
| "A SECURITY GUARD" | 0.2879999876022339 |
| "PHOTOGRAPHY WALK" | 0.2840000092983246 |

### ③ Starting Entities

111 node mở rộng 2-hop · **4 node cụt** (không đường đi nào) · 107 node có đường

| node | số đường 2-hop |
|---|---|
| "BRONWYN" | 652 |
| "BRIENNE" | 68 |
| "JAIME LANNISTER" | 144 |
| "TYRION LANNISTER" | 112 |
| "WESTEROS" | 68 |
| "TYWIN" | 17 |
| "CHAESONG-HWA'S TEAM" | 87 |
| "KEVIN DE BRUYNE" | 40 |
| "BRIAR" | 108 |
| "ALFYN" | 56 |
| "TYRION" | 51 |
| "BROOKLYN NINE-NINE" | 299 |

### ④ Candidate Answer Entities

- Loại đáp án LLM đoán: `['concept', 'unknown']`
- Ứng viên tìm được: **0** node
- Ví dụ: 

### ⑤ Reasoning Path

- Chấm điểm: 108 thực thể · **20291 đường đi**
- Bỏ phiếu cạnh: 50 cạnh liên quan → **1331 đường được cộng phiếu**

### ⑥ Topology-Enhanced Retrieval

`max_chunks=3` mỗi thực thể

| thực thể | chunk lấy ra |
|---|---|
| "BRONWYN" | chunk-5b6c70f1f1, chunk-1c0657a846, chunk-7a3558efd3 |
| "BRIENNE" | chunk-216bc148e6, chunk-9040642fe4, chunk-d3940135ac |
| "JAIME LANNISTER" | chunk-432b50669e, chunk-fa5fee30de, chunk-6005549693 |
| "TYRION LANNISTER" | chunk-fa5fee30de, chunk-dca3a8b582, chunk-432b50669e |
| "WESTEROS" | chunk-9040642fe4, chunk-0a2d4a40a7, chunk-fa5fee30de |

### ⑦ Chunk Retrieval

- Lấy cuối cùng: **30** chunk (chunk_nums=30)
- ID: chunk-dca3a8b582, chunk-0a2d4a40a7, chunk-9040642fe4, chunk-1c5f787179, chunk-92f77f0e13, chunk-5b6c70f1f1, chunk-fa5fee30de, chunk-7a3558efd3, chunk-98a8574995, chunk-c4da48420f

### Câu trả lời sinh ra

> When discussing the exciting possibilities of upcoming co-op gameplay, resource management, and stealth mechanics in video games, **Bronwyn** expresses a thoughtful and enthusiastic perspective on how stealth missions could enhance the overall experience.   Specifically, Bronwyn points out that if stealth is integrated into the game, players will need to plan their approaches much more carefully than they would in a standard, action-heavy run-and-gun scenario. According to Bronwyn, successful stealth missions would rely heavily on proper timing and clear communication among teammates. Rather than shying away from the added difficulty, Bronwyn embraces the challenge, noting that getting the …


---

<!-- ==== PHẦN DƯỚI VIẾT TAY. Chạy lại Step_5_trace.py sẽ ghi đè, nhớ dán lại. ==== -->

# Nhận xét từ ba trace

## 🔴 Phát hiện lớn: bước ④ **luôn trả về 0 ứng viên**

Cả ba query đều cho `Ứng viên tìm được: 0`. Đây không phải trùng hợp — đó là **bug
so khớp chữ hoa/thường trong code gốc**.

| Nơi | Giá trị |
|---|---|
| `entity_type` lưu trong đồ thị | `'"EVENT"'`, `'"PERSON"'`, `'"ORGANIZATION"'`… (**HOA**, có dấu nháy) |
| `get_types()` trả `TYPE_POOL` | `['event', 'person', …]` (**thường**, `.lower()` ở `networkx_impl.py:155`) |
| Prompt đưa cho LLM | `TYPE_POOL` — bản **thường** |
| LLM trả về | `['concept', 'person', 'event']` — **thường** |
| `get_node_from_types` so sánh | `data['entity_type'].strip('"')` → `EVENT` (**HOA**) `in` `['event',…]` → ❌ |

`get_types()` có trả về **hai** danh sách: `TYPE_POOL` (thường) và `TYPE_POOL_w_CASE`
(giữ nguyên hoa/thường). Nhưng `operate.py:1423-1424` chỉ dùng bản thường:

```python
TYPE_POOL, TYPE_POOL_w_CASE = await knowledge_graph_inst.get_types()
kw_prompt = kw_prompt_temp.format(query=query, TYPE_POOL=TYPE_POOL)
```

`TYPE_POOL_w_CASE` được tính ra rồi **không dùng ở đâu cả** — grep toàn file chỉ
thấy đúng hai dòng trên.

### Hệ quả

`maybe_answer_list` rỗng → `cal_path_score_list` đếm được **0 node đích trên mọi
đường đi** → toàn bộ `scorelist[0]` bằng 0. Nghĩa là:

> **Cơ chế "answer-type-aware" — điểm bán hàng chính của MiniRAG trong bài báo —
> đang không chạy.** Việc chấm điểm đường đi hiện chỉ còn dựa vào phiếu cạnh
> (`edge_vote_path`), tức chỉ còn một nửa thuật toán.

Đây là ứng viên **rất mạnh** cho Proposed Method: sửa một dòng, không cần index lại,
và có thể giải thích được vì sao Multi-hop chỉ đạt 42,86%.

⚠️ **Chưa sửa.** Cần xác nhận thêm: (a) upstream có cố ý không, (b) sửa xong điểm có
tăng thật không, hay đồ thị thưa của nhóm làm hỏng theo cách khác. Đây là việc của
`H2`, không phải sửa ngay bây giờ.

---

## Ba quan sát khác

### 1. `top_k=60` kéo về rất nhiều node vô quan

Trace query 1, thực thể `Li Hua` khớp 60 node, nhưng từ node thứ ba trở đi đã là:

| node | cosine |
|---|---|
| "LI HUA" | 0.924 |
| "LIHUA" | 0.653 |
| "LALIGA" | **0.415** |
| "CINQUE TERRE" | **0.344** |

`LALIGA` và `CINQUE TERRE` không liên quan gì tới Li Hua. Ngưỡng
`cosine_better_than_threshold = 0.2` quá lỏng, nên gần như mọi node đều lọt.

→ Khớp trực tiếp với **`context_precision = 0,316`** đo bằng RAGAS: 2/3 chunk lấy về
là rác.

### 2. Bùng nổ đường đi

Query 1: **138 thực thể → 22.879 đường đi 2-hop**, trong đó chỉ **971 đường** nhận
được phiếu cạnh. Nghĩa là **96% đường đi được sinh ra rồi chấm điểm vô ích**.

Node `"ADAMSMITH"` một mình sinh 760 đường; `"LIHUA"` sinh 2.001 đường.

### 3. Đồ thị bị chẻ đôi vì tên thực thể trùng lặp

| Cùng một người | Các node riêng biệt trong đồ thị |
|---|---|
| Adam Smith | `"ADAM SMITH"` (34 đường) · `"ADAMSMITH"` (760 đường) · `"MR. SMITH"` (299 đường) |
| Li Hua | `"LI HUA"` (367) · `"LIHUA"` (2.001) |
| Wolfgang Schulz | `"WOLFGANG"` · `"WOLFGANGSCHULZ"` · `"WOLFGANGSCHULZ":` ← *node có dấu hai chấm* |

Thông tin về một người bị chia cho 2–3 node, mỗi node giữ một phần chunk. Đây là lỗi
**lúc index** (trích xuất thực thể không chuẩn hoá), nên **muốn sửa phải index lại**.

Node `"WOLFGANGSCHULZ":` còn dính cả dấu hai chấm của định dạng chat — dấu hiệu prompt
trích xuất không làm sạch đầu vào.

---

## Vì sao ba câu này trả lời sai

**Query 1 (Multi, `error`).** Retrieval lấy đúng người (`ADAM SMITH`) nhưng sai thời
điểm — chunk lấy về là các lời nhắc tiền nhà **tháng 4 và tháng 6**, không phải mốc
`20260301` trong câu hỏi. Node ngày tháng khớp gần như ngẫu nhiên: `20260301` khớp
mạnh nhất với `"20260107_15:00"` (0,679). **Embedding không hiểu thứ tự thời gian**,
mà câu hỏi lại là câu so sánh trước/sau. Hệ thống kết luận "không có bản ghi" trong
khi đáp án đúng là "Yes".

**Query 2 (Null, `error`).** Câu hỏi ghép hai chủ đề không liên quan (bài giảng y tế
+ buổi tập ban nhạc), đáp án đúng là *Insufficient information*. Nhưng bước ② vẫn
khớp mượt cả hai vế (`COMMUNITY MEDICAL KNOWLEDGE LECTURE` 0,934 · `BAND GATHERING`
0,593), rồi retrieval lấy về đủ chunk cho cả hai. **Không có bước nào kiểm tra hai
cụm chunk đó có nói về cùng một sự kiện không**, nên LLM nhận được context trông rất
đầy đủ và tự tin ghép lại thành câu trả lời bịa.

Đây chính là cơ chế sinh ra **err 31,67% ở nhóm Null**: hệ thống không có đường nào
để nói "không biết".

**Query 3 (Single, `accurate`).** Câu một thực thể, một chunk. Trace ngắn, không có
gì bất thường — đúng vùng MiniRAG hoạt động tốt (Single acc 60,17%).

---

## Nối sang Phase 2

| Phát hiện | Giả thuyết liên quan | Cần index lại? |
|---|---|---|
| ④ luôn rỗng (bug hoa/thường) | Ứng viên mới, mạnh nhất | ❌ Không |
| `top_k`/ngưỡng cosine quá lỏng | `HD2` Top-K sensitivity | ❌ Không |
| Bùng nổ đường đi | `H3` phân tích retrieval | ❌ Không |
| Embedding không hiểu thời gian | `H4` BM25 / lexical | ❌ Không |
| Tên thực thể trùng lặp | Chuẩn hoá lúc index | ✅ Có |
