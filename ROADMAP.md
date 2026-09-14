# MiniRAG Research Project — Roadmap 3 Phase

> Reproduce → Analyze → Improve → Prove
> 3 thành viên: **Hùng** (Retrieval & Proposed Method) · **Tài** (Baseline & Failure Analysis) · **Huy Đức** (Experiment & Evaluation)

Tài liệu này gộp 8 week-milestone trên trang kế hoạch thành **3 phase**, xếp theo thứ tự bắt buộc phải làm trước — làm sau.

## Ký hiệu

| Ký hiệu | Nghĩa |
|---|---|
| `‖ A` | Làm song song được với nhóm A (không phụ thuộc nhau) |
| `→ X` | Phải xong X mới làm được |
| ✅ | Đã xong |
| 🔄 | Đang làm |
| ⬜ | Chưa bắt đầu |

Mã task lấy từ trang kế hoạch. Những mã ghi `*` là tôi suy ra từ mô tả stage vì trang chỉ đặt tên rõ cho T4–T6, H1–H2, HD1/HD-Schema/HD-Final.

---

## PHASE 1 — Nền tảng & Phát hiện lỗi

*Tương ứng Week 01–03: Learning → Baseline Reproduction → Failure Discovery*
**Mục tiêu:** cả nhóm đứng trên cùng một baseline bất biến, và biết MiniRAG hỏng ở đâu bằng bằng chứng chứ không phải cảm giác.

| # | Task | Người | Phụ thuộc / Song song | ✓ |
|---|---|---|---|---|
| 1 | Đọc paper MiniRAG, thống nhất thuật ngữ, hiểu heterogeneous graph retrieval | **Cả nhóm** | — | ⬜ |
| 2 | `T1*` Dựng môi trường chuẩn, hướng dẫn cài đặt chạy lại được trên máy 3 người | Tài | → 1 | 🔄 |
| 2b | Đóng băng version + commit dev set + chia sẻ index | **Hùng** | → 2 | 🔄 |
| 3 | `T2*` Chạy baseline gốc và **đóng băng `baseline.yaml`** | Tài | → 2 | ✅ |
| 4 | `T3*` End-to-end architecture map (raw docs → graph → answer) | Tài | → 2 · `‖ A` | ⬜ |
| 5 | `H1` **Retrieval Code Map** (Query Mapping / Path Discovery / Chunk Extraction) | **Hùng** | → 2 · `‖ A` | ✅ |
| 5b | `H1b` **Retrieval Flow** + **Query Trace** 3 query thật | **Hùng** | → 5 | ✅ |
| 6 | `HD1` Automated Experiment Runner (config → retrieve → generate → evaluate → results.json) | Huy Đức | → 3 · `‖ B` | ✅ |
| 7 | `HD-Schema` Chuẩn hoá schema log kết quả từng query | Huy Đức | → 6 · `‖ B` | ✅ |
| 8 | `T4` Thu tập **failed-query dataset** (≥20–50 câu, kèm retrieved chunks) | Tài | → 3 | 🔄 |
| 9 | `T5` **6-Stage Failure Taxonomy** — phân loại từng câu lỗi | Tài | → 8 | ⬜ |
| 10 | `T6` Failure Distribution Statistics (tỷ lệ % mỗi nhóm lỗi + ví dụ thật) | Tài | → 9 | ⬜ |
| 11 | `T7*` Research Problem Statement — chốt bài toán cần giải | Tài | → 10 | ⬜ |
| 11b | 🔧 `G1` **Sửa bug answer-type** rồi đo lại → `baseline_v2.yaml` | **Hùng** | → 5b | ⬜ |

**Song song:** nhóm `A` (task 4, 5) chạy cùng lúc — đọc code không cần chờ baseline chạy xong. Nhóm `B` (task 6, 7) chạy cùng lúc với 8–10 — Huy Đức xây runner trong khi Tài phân tích lỗi.

**Cổng ra Phase 1:** có `baseline.yaml` đóng băng + bảng phân phối 6 nhóm lỗi. **Không có bảng này thì Phase 2 chỉ là đoán mò.**

---

## PHASE 2 — Thăm dò & Xây dựng cải tiến

*Tương ứng Week 04–06: Research Exploration → Method Selection → Implementation*
**Mục tiêu:** từ bằng chứng lỗi ra được một Proposed Method chạy được trên pipeline chung.

| # | Task | Người | Phụ thuộc / Song song | ✓ |
|---|---|---|---|---|
| 12 | `H2` Trace retrieval của các query lỗi (entity sót? path cụt? chunk xếp hạng thấp?) | **Hùng** | → 5, 10 | ⬜ |
| 13 | `H3*` Retrieval baseline analysis — báo cáo nhận xét retrieval gốc | **Hùng** | → 12 | ⬜ |
| 14 | `HD2*` Top-K sensitivity study (K = 1, 3, 5, 7, 10) theo từng loại query | Huy Đức | → 6 · `‖ C` | ⬜ |
| 15 | `HD3*` Context efficiency — tỷ lệ chunk rác, chunk trùng lặp | Huy Đức | → 6 · `‖ C` | ⬜ |
| 15b | 📊 `G3` Sensitivity study top_k + giới hạn token bảng Sources | Huy Đức | → 6 · `‖ C` | ⬜ |
| 15c | ✅ `G2` **Entity resolution** lúc merge *(+`G6` dọn node rác, chung 1 lần index)* | **Hùng** | → 13 | ⬜ |
| 15d | ✅ **Path re-weighting / pruning** — 96% đường đi hiện vô ích | **Hùng** | → 13 | ⬜ |
| 16 | `H4` **Lexical prototype (BM25)** — cứu thực thể hiếm | **Hùng** | → 13 | ⬜ |
| 17 | `H5` **Fixed hybrid fusion** (dense + lexical) | **Hùng** | → 16 | ⬜ |
| 18 | `H6` **Adaptive / router** — phân loại query rồi chọn chiến lược | **Hùng** | → 17 | ⬜ |
| 19 | `H7` Chốt phương án và **hiện thực Proposed Method** thành module interface sạch | **Hùng** | → 18 | ⬜ |
| 20 | `H8` Tài liệu thuật toán & tham số | **Hùng** | → 19 · `‖ D` | ⬜ |
| 21 | `T8*` Integration branch — merge Proposed Method, không làm gãy pipeline | Tài | → 19 · `‖ D` | ⬜ |

**Song song:** nhóm `C` (14, 15) là việc của Huy Đức, chạy độc lập trong khi Hùng làm 12–13. Nhóm `D` (20, 21) chạy cùng lúc sau khi có code.

**Ràng buộc:** task 16 → 17 → 18 **phải tuần tự** — mỗi bước là một giả thuyết đơn biến, gộp lại thì không biết cái nào tạo ra hiệu quả.

**Cổng ra Phase 2 (DoD của Hùng):** một modification chỉ tính là xong khi *chạy được trên pipeline chung*, *có baseline comparison*, và *giải thích được nó sửa nhóm lỗi nào trong 6 nhóm*.

---

## PHASE 3 — Chứng minh & Báo cáo

*Tương ứng Week 07–08: Full Experiment → Report*
**Mục tiêu:** chứng minh cải tiến là thật, hoặc ghi nhận trung thực rằng nó không hiệu quả.

| # | Task | Người | Phụ thuộc / Song song | ✓ |
|---|---|---|---|---|
| 22 | `HD-Final` Full benchmark **Baseline vs Proposed** trên cùng 100% điều kiện | Huy Đức | → 19, 21 | ⬜ |
| 23 | `HD-Ablation` Ablation study — tách riêng Lexical / Graph / Adaptive | Huy Đức | → 22 | ⬜ |
| 24 | `H9` Hỗ trợ Huy Đức chạy ablation (bật/tắt từng thành phần) | **Hùng** | → 23 (đồng thời) | ⬜ |
| 24b | **Chạy lại toàn bộ trên SLM** (index + QA) qua vLLM trên GPU thuê | Huy Đức | → 22 | ⬜ |
| 25 | Bảng đối chiếu 4 chỉ số: **Accuracy · Recall@K · Latency · Tokens** | Huy Đức | → 23, 24b | ⬜ |
| 26 | **Họp Keep / Reject** — quyết định dựa trên số liệu | **Cả nhóm** | → 25 | ⬜ |
| 27 | `T10*` Error Analysis section | Tài | → 26 · `‖ E` | ⬜ |
| 28 | `H10` Proposed Method section | **Hùng** | → 26 · `‖ E` | ⬜ |
| 29 | `HD-Report*` Experiment & Result section | HuyDog | → 26 · `‖ E` | ⬜ |
| 30 | Ghép báo cáo khoa học cuối | **Cả nhóm** | → 27, 28, 29 | ⬜ |

**Song song:** nhóm `E` (27, 28, 29) — ba người viết ba mục cùng lúc sau khi đã chốt Keep/Reject.

**Lưu ý:** nếu họp Keep/Reject ra kết luận **Reject**, vẫn phải viết đủ 3 mục và ghi nhận **negative findings**. Đó là kết quả khoa học hợp lệ, không phải thất bại.

---

## ⛔ Quy tắc đóng góp khoa học — đọc trước khi đề xuất cải tiến

Chốt 09/09/2026. Chi tiết đầy đủ ở [`CLAUDE.md`](CLAUDE.md) §1b.

Một đóng góp hợp lệ phải đủ 5 bước: **Observed Problem → Hypothesis → Designed
Mechanism → Controlled Experiment → Measurable Effect**.

**Sáu hành vi KHÔNG được gọi là Proposed Method:** đổi Top-K đơn thuần · đổi LLM
temperature · đổi sang API/LLM to hơn · đổi embedding model · sửa system prompt ·
bọc thêm framework hay tool UI.

**Hệ quả:** hai việc đang xếp ưu tiên cao **không phải** Proposed Method —

| Việc | Vai trò đúng |
|---|---|
| `G1` sửa bug hoa/thường answer-type | 🔧 **Sửa baseline**, báo cáo như một *finding* |
| `G3` chỉnh `top_k` / giới hạn Sources | 📊 **Sensitivity study** làm bằng chứng cho Observed Problem |

Ứng viên Proposed Method thật sự: `G2` entity resolution · **path re-weighting** ·
`H4→H5→H6` BM25 → hybrid fusion → adaptive router.

> ⚠️ **Lưu ý mã hiệu:** `H1`–`H10` là **mã task của Hùng** theo trang kế hoạch.
> `G1`–`G6` là **mã giả thuyết cải tiến** trong
> [`docs/phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md`](docs/phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md).
> Hai hệ mã khác nhau, đừng lẫn.

---

## Trạng thái thật tính đến 09/09/2026

Chỉ liệt kê những gì **có sản phẩm kiểm chứng được**, không tính việc đang dở.

| Việc | Trạng thái | Bằng chứng |
|---|---|---|
| `H1` Retrieval Code Map | ✅ | Bản đồ hàm 4 giai đoạn + bảng tham số đóng cứng + 6 điểm nghi vấn |
| Backend Gemini + pipeline đo | ✅ | `minirag/llm/gemini.py`, `reproduce/Step_0..4` |
| Sửa bug O(N²) trong `ainsert` | ✅ | ~68.000 → **653** lời gọi LLM |
| **Index corpus đầy đủ 442 tài liệu** | ✅ | 442/442 processed · 503 chunks · đồ thị 770 nodes / 1.779 edges |
| **Baseline chính thức (corpus 442)** | ✅ | dev 200 câu: **acc 57,33 ± 1,53 · err 21,00 ± 2,00** |
| **`baseline.yaml` đóng băng** | ✅ | [`baseline.yaml`](baseline.yaml) — commit `dbfa0d1`, chốt 07/09/2026 |
| Giao thức judge 3 lượt + sàn nhiễu | ✅ | sd acc **1,53** → chênh lệch **< 3 điểm** không kết luận được |
| RAGAS chẩn đoán (n=100) | ✅ | faithfulness 0,703 · **context_precision 0,316** · context_recall 0,560 |
| `H1` Retrieval Flow + Code Map | ✅ | [`docs/phase1/RETRIEVAL_FLOW.md`](docs/phase1/RETRIEVAL_FLOW.md) · [`docs/phase1/RETRIEVAL_CODE_MAP.md`](docs/phase1/RETRIEVAL_CODE_MAP.md) |
| **Query Trace 3 query thật** | ✅ | [`docs/phase1/QUERY_TRACE.md`](docs/phase1/QUERY_TRACE.md) — sinh tự động bởi `reproduce/Step_5_trace.py` |
| **🔴 Phát hiện bug: bước ④ luôn rỗng** | ✅ | So khớp hoa/thường `entity_type` → answer-type-aware **không chạy** |
| `G1` Sửa bug answer-type + đo lại | ✅ | 57,33 → 59,50 · **p = 0,267, chưa kết luận được** |
| Chạy SLM Qwen2.5-3B (Modal A10G) | ✅ | acc 59,50 · err 28,00 · `neither` 12,50 · ~$1, dưới 1 giờ |
| Công tắc local / Modal / Gemini | ✅ | `reproduce/slm_env.sh` + `reproduce/modal_slm.py` |
| Environment guide (`T1*`) | 🔄 | [`docs/phase1/ENVIRONMENT.md`](docs/phase1/ENVIRONMENT.md) — đã PASS trên **1/3 máy** (Windows, CPython 3.13.5) |
| Pin version + commit dev set | ✅ | `requirements.lock.txt` (119 gói) · `logs/devset.csv` + bằng chứng baseline đã track |
| Chia sẻ index 442 (15 MB) | ⬜ | **Chưa** — ai index lại sẽ ra graph khác, baseline mất tính so sánh |
| Failed-query dataset, Failure Taxonomy | ⬜ | Chưa bắt đầu — **đây là nút thắt chặn Phase 2** |

### Năm cấu hình đã đo (dev set 200 câu, 3 lượt judge)

| Cấu hình | acc | err | **neither** | Single | Multi | Null |
|---|---:|---:|---:|---:|---:|---:|
| Gemini baseline | 57,33 ± 1,53 | 21,00 ± 2,00 | 21,67 | 60,17 | 42,86 | 50,00 |
| Gemini + sửa answer-type | 59,50 ± 0,50 | 21,50 ± 0,87 | 19,00 | 62,89 | 36,51 | 56,67 |
| Qwen2.5-3B bf16 — code **chưa vá** | 56,00 ± 1,00 | 30,33 ± 0,29 | 13,67 | 57,86 | 42,86 | 55,00 |
| **Qwen2.5-3B bf16** — đã vá answer-type | 59,50 ± 0,50 | 28,00 ± 0,87 | **12,50** | 60,38 | 47,62 | 65,00 |
| *Bài báo — Qwen2.5-3B* | *48,75* | *26,02* | *25,23* | — | — | — |

### ⭐ Baseline 637 câu, corpus 442 — mốc chính thức mới (12/09/2026)

| Cấu hình | acc | err | neither | Single (506) | Multi (66) | Null (65) |
|---|---:|---:|---:|---:|---:|---:|
| **Chưa vá** *(nối dài baseline 57,33)* | **61,70 ± 0,31** | 19,57 ± 0,24 | 18,73 | 63,64 | 43,43 | 65,13 |
| Đã vá answer-type | 61,38 ± 0,27 | 19,78 ± 0,47 | 18,84 | 62,78 | **46,97** | 65,13 |

**Sàn nhiễu sụp từ 1,53 xuống 0,31.** Ngưỡng "dưới 3 điểm không kết luận được" trong
`CLAUDE.md` hoá ra là thuộc tính của **dev set 200 câu**, không phải của judge. Ở n=637
ngưỡng còn khoảng **0,6 điểm**.

**Dev set 200 câu bi quan 4,37 điểm** (57,33 so với 61,70) và **thổi phồng lỗi nhóm
Null 8,59 điểm** (err 31,67 trên 20 câu, thực tế 23,08 trên 65 câu). Phát hiện "hệ
thống bịa khi thiếu bằng chứng" phải hạ mức độ nghiêm trọng tương ứng.

**Multi-hop là phát hiện duy nhất đứng vững:** 43,43 / 42,42 trên n=66, gần trùng khít
dev set (42,86 / 42,86). Tỷ lệ sai xấp xỉ tỷ lệ đúng.

### ⛔ Bản vá answer-type KHÔNG cải thiện độ chính xác

Đây là kết quả quan trọng nhất của lượt 637 câu, và nó **ngược** với dev set.

| Tập | Δacc | McNemar | p |
|---|---:|---|---:|
| Dev 200, Gemini | +2,17 | 9 lên / 4 xuống | 0,267 |
| Dev 200, Qwen | +3,50 | 22 lên / 17 xuống | 0,522 |
| **637 câu, Gemini** | **−0,32** | **24 lên / 29 xuống** | **0,583** |

Tách theo loại (n=635, hai câu trùng bị gộp):

| Nhóm | n | sai→đúng | đúng→sai | net | p |
|---|---:|---:|---:|---:|---:|
| Single | 506 | 11 | 19 | −8 | 0,201 |
| Multi | 64 | 6 | 3 | **+3** | 0,508 |
| Null | 65 | 7 | 7 | 0 | 1,000 |

Bản vá **đổi kết quả 53 câu** — cơ chế có chạy thật, không phải không có tác dụng gì.
Nhưng số câu hỏng đi nhiều hơn số câu tốt lên. Hai tín hiệu dương trên dev set là nhiễu.

**Vì sao vá xong acc lại giảm — đo được, không phải suy đoán.** Đồ thị Gemini chỉ có
**7 kiểu thực thể**, và ba kiểu đầu phủ **86,6%** số node:

| Kiểu | Node | % đồ thị |
|---|---:|---:|
| event | 256 | 33,2% |
| person | 245 | 31,8% |
| organization | 166 | 21,6% |
| location | 80 | 10,4% |
| *3 kiểu còn lại + unknown* | 23 | 3,0% |

Khi LLM trả lời *"kiểu đáp án là PERSON"*, `maybe_answer_list` nhận **245/770 node —
gần một phần ba đồ thị**. `cal_path_score_list` (`utils.py:404`) đếm số node đó trên
mỗi đường đi, nên **gần như đường nào cũng ghi điểm**, và đường qua nhiều node ghi
nhiều hơn — tức thiên vị đường đi qua hub. Mà hub là nguồn nhiễu chính: `LIHUA` bậc 300.

Bản vá không hỏng. Nó bật một tín hiệu **quá thô để phân biệt**. Điều đó khớp đúng
hướng của số liệu: Single **−8** (cần đường ngắn chính xác, bị đường hub lấn), Multi
**+3** (vốn cần đường dài).

**Giả thuyết kiểm được:** giá trị của cơ chế answer-type tỷ lệ với **độ mịn của hệ
thống kiểu**. Đồ thị Gemini 7 kiểu → −0,32. Đồ thị Qwen **47 kiểu / 1.556 node** →
+3,50 trên dev set. Cùng một cơ chế giải thích được cả hai kết quả. Đáng theo.

> ⚠️ **Cập nhật 13/09 — phép sàng lọc trên Qwen 637 không ủng hộ giả thuyết này.** Qwen,
> 637 câu: 44 lên / 40 xuống, net **+4, p = 0,744** (Gemini: net −5, p = 0,583). Cả hai là
> số không; +3,50 trên dev 200 là nhiễu. Giả thuyết **chưa bị bác bỏ** — phép sàng lọc quá
> yếu vì hai đồ thị khác nhau nhiều thứ — nhưng **không còn bằng chứng ủng hộ**. Muốn kết
> luận phải gộp 47 kiểu của Qwen xuống 7 nhóm và chạy lại trên **cùng** đồ thị.

**Cách trình bày đúng:** cơ chế answer-type-aware — một trong những đóng góp trung tâm
của bài báo — **đã chết trên mọi truy vấn** do lỗi so khớp hoa/thường (`"ITEM"` so với
`"item"`, khớp 0 node thay vì 49). Hồi sinh nó xong, điểm **không tăng**. Đây là một
**kết quả phủ định có giá trị**: cơ chế chạy đúng như thiết kế nhưng thiết kế không giúp
gì trên bộ dữ liệu này.

Nhóm Multi là chỗ duy nhất có dấu hiệu dương (+3,54 điểm, đúng nhóm mà answer-type lẽ
ra hữu ích nhất), nhưng p = 0,508 trên n = 64 — chưa nói được gì.

**Giữ bản vá làm mặc định** vì nó sửa một lỗi có thật, nhưng phải ghi rõ nó không đổi
điểm. Không được trình bày như đóng góp.

**Cột `neither` giải thích gần như toàn bộ khác biệt.** Nó là tỷ lệ hệ thống nói
không biết / từ chối / lạc đề. Tỷ lệ **dám trả lời** (acc + err): Qwen **87,5%**,
Gemini đã vá 81,0%, bài báo 74,8%.

Qwen không sai nhiều hơn vì kém hơn — nó sai nhiều hơn vì **ít chịu im lặng hơn**.
So với bài báo, cấu hình của nhóm đổi **11 điểm accuracy lấy 2 điểm error**. Đây là
một đánh đổi, không phải cải thiện thuần.

Đáng chú ý: +6,5 điểm err của Qwen so với Gemini đến gần như toàn bộ từ **Single-hop**
(err +8,18, `neither` 18,87 → 13,21) — nhóm câu dễ nhất. Ở Null thì Qwen lại sai
**ít hơn** 3,33 điểm.

*Giả thuyết đã loại trừ:* độ dài câu trả lời gần như bằng nhau ở cả ba cấu hình
(trung vị 706 / 732 / 714 ký tự), nên không phải nguyên nhân.

> ⚠️ **Không được trình bày 59,50 như "nhóm tái tạo được dòng Qwen2.5-3B của bài báo".**
> Bốn khác biệt cùng lúc: code đã vá lỗi answer-type (bài báo chạy bản hỏng), chấm
> bằng Gemini thay vì GPT-4o, 200 câu thay vì 637, và bản vá O(N²) làm đồ thị khác
> upstream. Ranh giới `error` / `neither` phụ thuộc judge nên riêng việc đổi judge
> đã đủ dịch chuyển hai cột đó.

### 🔍 Chẩn đoán truy hồi bằng Evidence — dev 200, index Qwen (13/09/2026)

Cột `Evidence` ghi đúng thời điểm tin nhắn chứa đáp án; mỗi chunk bắt đầu bằng
`Time: YYYYMMDD_HH:MM`. Nên với mỗi câu ta biết **chính xác chunk nào chứa đáp án** — đo
được truy hồi mà không cần sinh hay chấm. 180 câu, 207 chunk đáp án (20 câu Null có
evidence `N/A` bị loại). Script: `reproduce/diagnose_path2chunk.py` · báo cáo:
`logs/diag_path2chunk_report.txt`. Evidence **chỉ** dùng để chẩn đoán, không bao giờ
dùng lúc chạy (rò nhãn).

**Chunk đáp án rơi rụng ở đâu:**

| Giai đoạn | Chunk đáp án còn lại |
|---|---:|
| Top-30 vector thuần trên câu hỏi (`chunks_vdb`) | **87,0%** |
| Xếp hạng đồ thị, 30 chunk (`kwd2chunk`) | 61,8% |
| Sau A1@4000 — thứ thật sự vào prompt | **47,3%** |

**Phát hiện 1 — lỗi `path2chunk` có thật nhưng vô hại.** `operate.py:1207` chọn chunk theo
điểm của **đường đi cuối cùng** thay vì điểm cộng dồn mọi đường (bản đúng nằm trong
comment từ commit đầu tiên của upstream). Sửa xong: 47,3% → 45,4%, McNemar 13 lên / 17
xuống, p = 0,585. → Sửa lỗi baseline, **không phải đóng góp**.

**Phát hiện 2 — cắt theo vách điểm làm mất đáp án.** Quy tắc không tham số (cắt tại chỗ
`s[i]/s[i+1]` lớn nhất): giữ trung vị 4 chunk, 2.424 token, nhưng chỉ còn **37,2%** chunk
đáp án. Dự báo hại độ chính xác.

**Phát hiện 3 — Observed Problem mạnh nhất: khâu đồ thị bỏ rơi 25 điểm recall mà vector đã
tìm được.** `kwd2chunk` chỉ xếp hạng chunk **nằm trên đường đi**; `chunks_ids` từ vector
chỉ được thưởng ×10 nếu tình cờ đứng đầu một đường. Chunk vector tìm được mà không đường
nào chạm tới thì **không bao giờ vào context**.

Mô phỏng offline trên chính xếp hạng đã lưu (`reproduce/simulate_fusion.py`; vector tính
lại khớp bản ghi 180/180), cùng A1@4000:

| Cách xếp hạng | Chunk đáp án | Câu đủ đáp án | Token tv | Multi: chunk / câu đủ |
|---|---:|---:|---:|---:|
| Đồ thị (hiện tại) | 47,3% | 43,3% | 3.678 | 54,2% / 28,6% |
| **RRF(đồ thị, vector)**, k=60 | **66,7%** | **62,8%** | 3.704 | **81,2% / 66,7%** |
| Vector thuần | 71,5% | 67,8% | 3.726 | 79,2% / 57,1% |

RRF so với hiện tại: **40 câu lên / 7 xuống, p < 0,0001**; riêng Multi 8 / 0, p = 0,008.

> ⚠️ **Điều phải nói thẳng khi viết bài.** Ở Single, vector thuần (69,2%) **hơn** RRF
> (62,3%) — tức trên câu một bước, xếp hạng đồ thị đang **kéo recall xuống**. Đồ thị chỉ
> thắng ở Multi. Nếu QA xác nhận điều này, đóng góp đúng là *"trộn giữ được lợi thế
> multi-hop của đồ thị mà không mất recall của vector"*, không phải *"đồ thị tốt hơn"*.
> Recall chunk cũng chưa phải độ chính xác — phải chờ judge.

**Đang chạy trên Qwen 637** (`reproduce/run_fusion637_{qa,judge}.sh`), mỗi biến thể so với
baseline `qwen637_fix`, đổi đúng một biến:

| Biến thể | Công tắc | Chẩn đoán dự báo |
|---|---|---|
| V2 | `PATH2CHUNK_FIX=1` + `CHUNK_CUT=knee` | giữ 37,2% đáp án → hại · **đo 14/09: hại thật** ↓ |
| V3 | `CHUNK_FUSION=rrf` | giữ 66,7% đáp án → có lợi · **đo 14/09: +10,92 acc, p = 1,4·10⁻⁷** ↓ |
| V1 | `PATH2CHUNK_FIX=1` | 45,4% → ≈ không đổi · **đo 14/09: net −2, p = 0,936** ✓ |

Dev 200 là tập con của 637 và quy tắc được nhìn trên dev → **phép thử sạch là 437 câu
ngoài dev**; `compare_variants.py` báo tách riêng.

**⛔ V2 — cắt theo vách: kết quả phủ định, có ý nghĩa thống kê (14/09, `logs/compare_v2.txt`)**

| Nhóm | n | baseline acc / err / neither | V2 acc / err / neither | McNemar |
|---|---:|---|---|---|
| **Tổng** | 635 | 51,02 / 27,66 / 21,31 | **45,41** / 23,52 / **31,08** | 64 lên / 100 xuống, **p = 0,006** |
| Single | 506 | 51,19 / 25,03 / 23,78 | 43,94 / 22,00 / 34,06 | 51 / 87, p = 0,003 |
| Multi | 64 | 30,21 / 58,85 / 10,94 | 23,96 / 47,92 / 28,12 | 6 / 9, p = 0,607 |
| Null | 65 | 70,26 / 17,44 / 12,31 | 77,95 / 11,28 / 10,77 | 7 / 4, p = 0,549 |
| Ngoài dev | 435 | 49,43 / 28,43 / 22,15 | 45,82 / 23,83 / 30,34 | 46 / 63, p = 0,125 |

Context trung vị **2.438 token** (giảm ~40%), nhưng mất 5,6 điểm acc. Cơ chế hỏng đúng như
chẩn đoán dự báo: bớt chunk thì bớt bằng chứng, và Qwen **chuyển sang từ chối** (`neither`
+9,77) chứ không bịa thêm (`err` −4,14; acc/(acc+err) còn nhích 64,84 → 65,88). Hệ an toàn
hơn nhưng trả lời được ít hơn hẳn. **Loại cắt vách.** Giá trị phụ: chẩn đoán bằng Evidence
đã dự báo đúng chiều trước khi tốn một lượt chấm nào.

**✅ V3 — trộn RRF xếp hạng đồ thị + vector: cải thiện lớn, có ý nghĩa thống kê (14/09, `logs/compare_v3.txt`)**

| Nhóm | n | baseline acc / err / neither | V3 acc / err / neither | McNemar chính xác |
|---|---:|---|---|---|
| **Tổng** | 635 | 51,02 / 27,66 / 21,31 | **61,94 ± 0,45** / 23,78 / 14,28 | **117 lên / 49 xuống, p = 1,4·10⁻⁷** |
| Single | 506 | 51,19 / 25,03 / 23,78 | 64,36 / 20,88 / 14,76 | 99 / 33, p = 7,5·10⁻⁹ |
| Multi | 64 | 30,21 / 58,85 / 10,94 | 43,75 / 42,71 / 13,54 | 15 / 6, p = 0,078 |
| Null | 65 | 70,26 / 17,44 / 12,31 | 61,03 / 27,69 / 11,28 | 3 / 10, p = 0,092 ⚠️ |
| **Ngoài dev (phép thử sạch)** | 435 | 49,43 / 28,43 / 22,15 | **62,99** / 22,38 / 14,64 | **85 / 28, p = 7,3·10⁻⁸** |
| Dev 200 | 200 | 54,50 / 26,00 / 19,50 | 59,67 / 26,83 / 13,50 | 32 / 21, p = 0,169 |

acc/(acc+err) 64,84 → **72,26**. Context trung vị 3.870 token, 9 chunk — **cùng trần A1@4000**
với baseline, nên điểm tăng không đến từ việc nhét thêm token.

**Kiểm độ sạch trước khi tin:**
- Độ dài câu trả lời không đổi (trung vị 524 → 526 ký tự); riêng 117 câu lên còn **ngắn đi**
  (541 → 491) → không phải giám khảo ưu ái câu dài.
- 46/117 câu lên là `neither` → `accurate`: có bằng chứng trong context thì Qwen thôi từ chối
  — đúng cơ chế giả thuyết.
- Hiệu ứng **lớn hơn** ở 435 câu ngoài dev (+13,56) so với dev (+5,17) → không có dấu hiệu
  quá khớp theo tập đã nhìn khi thiết kế.
- 0 dòng `Error`, 0 `judge_failed`, sd giữa 3 lượt chấm 0,45.

**⚠️ Nhóm Null đi ngược (−9,23 acc, p = 0,092, chưa ý nghĩa).** Chuyển dịch: 6 `accurate` →
`neither`, 4 `neither` → `error`, 4 `accurate` → `error`. Thêm chunk vector nghĩa là luôn có
văn bản "trông liên quan", nên với câu không có đáp án Qwen dễ trả lời thay vì nói không biết.
Phải ghi vào Limitations; là ứng viên kết hợp với A3 (cơ chế từ chối).

**Đủ 5 bước §1b:** Observed Problem (chẩn đoán Evidence: 87,0% → 47,3%) · Hypothesis
(`kwd2chunk` loại chunk không nằm trên đường đi) · Mechanism (RRF, k=60 không tinh chỉnh) ·
Controlled Experiment (một công tắc; cùng index, model, judge, 637 câu) · Measurable Effect
(Quality +10,92 acc; Efficiency cùng ngân sách; ablation V4 @2000 và V1 đang chạy).

*So với bài báo (chỉ tham chiếu — khác giám khảo):* acc 61,94 so với 48,75, err 23,78 so với
26,02 — lần đầu **vừa cao acc hơn vừa thấp err hơn**.

**V1 — chỉ sửa lỗi `path2chunk`: không đổi điểm (14/09, `logs/compare_v1.txt`)**

| Nhóm | n | baseline acc / err / neither | V1 acc / err / neither | McNemar |
|---|---:|---|---|---|
| **Tổng** | 635 | 51,02 / 27,66 / 21,31 | 50,81 ± 0,64 / 26,35 / 22,83 | 76 lên / 78 xuống, **p = 0,936** |
| Single | 506 | 51,19 / 25,03 / 23,78 | 51,19 / 23,06 / 25,76 | 64 / 64, p = 1,000 |
| Multi | 64 | 30,21 / 58,85 / 10,94 | 31,77 / 55,73 / 12,50 | 9 / 8, p = 1,000 |
| Null | 65 | 70,26 / 17,44 / 12,31 | 66,67 / 23,08 / 10,26 | 3 / 6, p = 0,508 |
| Ngoài dev | 435 | 49,43 / 28,43 / 22,15 | 51,34 / 23,98 / 24,67 | 54 / 47, p = 0,551 |

Lỗi có thật trong code nhưng không đổi điểm — đúng dự báo chẩn đoán (47,3% → 45,4% chunk đáp
án, p = 0,585). Trình bày như **sửa lỗi baseline**, không phải đóng góp.

**Tách biến cho V2.** V2 so với V1 — khác nhau đúng một thứ là cắt vách: **39 lên / 73 xuống,
net −34, p = 0,002** (ngoài dev 27 / 51, p = 0,009). → Toàn bộ phần hại của V2 là do cắt vách.

**Chẩn đoán bằng Evidence dự báo đúng chiều cả ba biến thể trước khi tốn lượt chấm nào:**
V1 ≈ 0 ✓ · V2 hại ✓ · V3 lợi ✓. Đây là lập luận phương pháp đáng đưa vào bài: nhãn Evidence
có sẵn cho phép sàng lọc cơ chế truy hồi gần như miễn phí.

**⛔ A3 dạng "ngưỡng tín hiệu truy hồi" không khả thi (14/09 — offline, 0 API)**

Đặc tả A3 trong kế hoạch: *từ chối nếu chunk tốt nhất dưới ngưỡng cosine*. Đo khả năng tách
65 câu Null khỏi 570 câu có đáp án (`reproduce/a3_feasibility.py`; `Type` chỉ dùng để đo):

| Tín hiệu | Null tv | Có đáp án tv | AUC |
|---|---:|---:|---:|
| Cosine chunk tốt nhất | 0,473 | 0,488 | 0,538 |
| Cosine trung bình top-5 | 0,437 | 0,427 | 0,475 |
| Khoảng cách top-1 − top-2 | 0,016 | 0,032 | 0,648 |
| Trùng đồ thị ∩ vector top-30 (dev) | 11 | 11 | 0,546 |

Mô phỏng cổng tốt nhất trên phán quyết V3 (`reproduce/a3_oracle_gate.py`), **ngưỡng chọn
bằng chính nhãn** và giả định câu Null bị từ chối luôn được chấm đúng — cả hai đều thiên vị
có lợi cho A3: **mọi ngưỡng đều làm giảm acc**. Từ chối 5% câu → chặn 5 Null nhưng chặn nhầm
26 câu có đáp án, acc 62,05 → 60,47. Ngưỡng tốt nhất là không từ chối gì.

Lý do: câu Null của LiHua-World là câu *gần đúng* về người và sự kiện có thật, nên truy hồi
ra chunk giống hệt câu có đáp án. **Tín hiệu thiếu bằng chứng phải nằm ở nội dung, không ở
độ tương đồng.** Đừng làm A3 theo đặc tả cũ.

Tín hiệu nội dung rẻ nhất cũng đã thử và loại: kiểm "ngày trong câu hỏi không có trong
corpus". Chỉ **1/65** câu Null nhắc ngày `YYYYMMDD` (câu có đáp án: 55/570), và **không câu
nào** nhắc ngày vắng mặt khỏi 313 ngày có tin nhắn. Câu Null ở đây không sai về thời gian.

**Trần lợi ích của A3 trên bộ này rất thấp:** V3 chỉ có 18 câu Null bị chấm `error`. Kể cả
một cổng hoàn hảo cũng chỉ thêm tối đa 18/635 = 2,8 điểm, còn mỗi câu có đáp án bị từ chối
nhầm mất trung bình ~0,62 điểm đúng. Ưu tiên thấp.

**⛔ V5a / V5b / V5c — verifier không sinh (không gọi model) cũng không tách được Null (14/09 — offline, 0 API)**

Câu hỏi: sau khi V3 sinh câu trả lời, có kiểm được "câu trả lời có được hỗ trợ không" mà
không thêm model nào? Đo trên **câu trả lời thật của V3** (`logs/qwen637_v3.csv`), nhãn chỉ
dùng để chấm tín hiệu. Lớp dương = 18 câu Null bị chấm `error`; lớp âm = 354 câu có đáp án
V3 trả lời đúng (chặn nhầm chúng là mất điểm). "Net oracle" = số Null được cứu − số câu
đúng bị chặn, **ngưỡng chọn bằng chính nhãn** (cận trên lạc quan).
`reproduce/v5_signal_feasibility.py` → `logs/v5_signal_feasibility.txt`.

| Tín hiệu (cao = đáng ngờ) | Họ | AUC [95% CI] | Net oracle |
|---|---|---:|---:|
| Tỷ lệ thực thể/số/trích dẫn trong câu trả lời vắng khỏi corpus | V5a | 0,53 [0,41–0,65] | +0 |
| … vắng khỏi Sources xấp xỉ (nửa vector, ngân sách 4000) | V5a | 0,58 [0,45–0,71] | +0 |
| Từ nội dung vắng khỏi từ vựng corpus | V5a | 0,45 | +0 |
| Câu trả lời tự nói "không được nhắc tới" / suy đoán ("likely") | V5a | 0,54 / 0,53 | +0 |
| Không có cạnh trực tiếp thực-thể-câu-hỏi → thực-thể-câu-trả-lời | V5b | 0,34 *(ngược chiều)* | +0 |
| Không có chunk chung giữa hai nhóm thực thể | V5b | 0,42 | +0 |
| MiniLM: câu trả lời ↔ chunk gần nhất (corpus / Sources xấp xỉ) | V5c | 0,52 / 0,52 | +0 |
| MiniLM: câu hỏi ↔ chunk gần nhất; câu trả lời ↔ câu hỏi | V5c | 0,51 / 0,57 | +0 |

**Không tín hiệu nào có net dương ở bất kỳ ngưỡng nào**, kể cả khi ngưỡng được chọn bằng
nhãn. Các tín hiệu tương quan với nhau (ρ 0,36–0,96) nên gộp điểm không thêm thông tin độc
lập — không lập điểm tổng hợp (V5c dừng ở đây).

Vì sao, nhìn từ 18 câu sai:
- **Câu trả lời sai được dựng từ nội dung có thật.** 18/18 câu có thực thể; phần "vắng khỏi
  corpus" chỉ là rác regex (`Lastly`, `Furthermore`). Lỗi nằm ở **tiền đề của câu hỏi**
  ("yêu thích", "tại sự kiện kỷ niệm", "đêm Giao thừa 2026", "đã dùng sau buổi tập 19/09")
  mà câu trả lời lặp lại rồi gắn với sự thật lân cận. Kiểm dấu vết (provenance) không bắt được
  vì dấu vết có thật.
- **Luật hẹp nhất còn lại — ngày câu trả lời trích phải là ngày của một chunk chứa nội dung
  câu trả lời** (`reproduce/v5a_date_provenance.py`): bắt **0/18** câu Null sai, chặn nhầm
  **23/354 = 6,5%** câu đúng. Loại.
- **Một phần trần là nhiễu nhãn.** Câu "Li Hua đo cửa sổ bao nhiêu trước khi lắp rèm" gán Null,
  nhưng chunk `20260928_10:00` ghi đúng "150 cm wide and 120 cm high" như V3 trả lời. Trần 18
  câu (2,8 điểm) còn thấp hơn thật.

**V5b (xác minh quan hệ bằng đồ thị) không khả thi với biểu diễn hiện tại** — không phải do
ngưỡng mà do cấu trúc (`reproduce/v5b_graph_bound.py`):
- Đồ thị Qwen **vô hướng** (`edgedefault="undirected"`): mất chiều quan hệ.
- **717/1.556 node cô lập** (46%), 746 thành phần liên thông.
- Không có loại quan hệ: `keywords` có **1.536 nhãn khác nhau**, phổ biến nhất là số điểm độ
  mạnh (`8`, `7`) và cảm xúc (`encouragement`, `support`). Không có `attended`/`bought`.
- **Cận trên độ phủ:** trong 347 câu có đáp án V3 trả lời đúng (có Evidence), chỉ **114 (32,9%)**
  có cạnh trực tiếp thực-thể-câu-hỏi → thực-thể-câu-trả-lời mà `source_id` trỏ đúng chunk gold;
  cho phép 2 bước: 126 (36,3%). 29 câu Yes/No không có thực thể trả lời. Một cổng "phải có quan
  hệ được đồ thị hỗ trợ" vì vậy chặn nhầm **≥ 63%** câu đúng, trước cả khi kiểm loại quan hệ.
  Chỉ còn đồng xuất hiện (73,2% chạm cạnh gold) — đúng thứ không được coi là bằng chứng.

**Cảnh báo phương pháp.** Sources của V3 không được lưu (chỉ đếm token), nên V5a/V5c dùng
corpus và Sources xấp xỉ. Kết luận "dấu vết có thật" không phụ thuộc xấp xỉ: Sources ⊂ corpus,
và Qwen chỉ thấy Sources. Hướng còn lại (NLI nhỏ V5d, Qwen verifier V5e) cần Sources thật →
phải chạy lại V3 có ghi context trước.

**📌 Đăng ký trước — V5d Bước 0: kiểm sàn HHEM-2.1-Open offline (14/09, ghi TRƯỚC khi chạy)**

Duyệt 14/09. Chỉ offline, không đụng runtime MiniRAG hay V3. Không làm pilot 50 câu khi chưa duyệt.
Script: `reproduce/v5d_hhem_floor.py` → `logs/v5d_step0.txt`, `logs/v5d_step0_scores.jsonl`.

- **Model, ghim cố định:** `vectara/hallucination_evaluation_model` @ `8e4a2e6e96c708cc76c2344f7e4757df2515292c`,
  trọng số sha256 `634de18a…2e72`; tokenizer + config `google/flan-t5-base` @ `7bcac572ce56db69c1ea7c8af255c5d7c9672fc2`.
  CPU float32. **Không chạy remote code** (nó nạp flan-t5-base theo tên, không ghim): tái hiện
  đúng 10 dòng suy luận của nó và phải khớp điểm công bố trong model card (sai lệch ≤ 1e-3) mới được chấm.
- **Luật quyết định, cố định:** tách câu trả lời V3 thành câu (bỏ markdown, tách mục liệt kê dính, giữ
  câu ≥ 4 từ). Điểm câu = max theo chunk premise. Điểm câu trả lời = min theo câu. **Gắn cờ
  (sẽ từ chối) khi < 0,5.** Không tinh chỉnh ngưỡng, không đổi cách gộp.
- **Quần thể và premise:**
  - Câu có đáp án, V3 trả lời đúng (majority): premise = chunk gold theo Evidence (chỉ để chẩn
    đoán; câu không map được chunk bị loại khỏi mẫu số và báo riêng).
  - 18 câu Null V3 trả lời sai: premise = Sources xấp xỉ (MiniLM, lấp tới 4.000 token).
- **Tiêu chí dừng (áp nghiêm):** dừng V5d nếu **> 10%** câu đúng bị gắn cờ, **hoặc** bắt được
  **< 6/18** câu Null sai. Trượt một trong hai → ghi kết quả phủ định, không tinh chỉnh.

### Đồ thị: SLM dựng khác hẳn Gemini

| | Qwen2.5-3B | Gemini Flash-Lite |
|---|---:|---:|
| Node | **1.556** | 770 |
| Cạnh | 1.509 | **1.779** |
| Số loại `entity_type` | **47** | 7 |

`prompt.py:5` chỉ cho phép 4 loại. Qwen sinh ra 47, gồm `EMOJI`, `FLAVOR`,
`QUESTION`, `STRETCH`, `TECHNOLOGY/PRODUCT`. Model nhỏ tuân thủ ràng buộc prompt kém
hơn nhiều, và **không có bước kiểm tra nào chặn lại** — bằng chứng độc lập cho
nhược điểm 8. Đồ thị gấp đôi node nhưng ít cạnh hơn, tức vụn hơn; điều này lại giải
thích vì sao Multi-hop của Qwen (47,62) **cao hơn** Gemini đã vá (36,51).

### Baseline 442 nói gì

| Loại | acc % | err % | n |
|---|---|---|---|
| Single | 60,17 ± 1,31 | 16,77 ± 2,21 | 159 |
| Null | 50,00 ± 5,00 | 31,67 ± 2,89 | 20 |
| **Multi** | **42,86** | **42,86** | 21 |

So với baseline corpus 267 cũ (**65,67 ± 0,29**), điểm **tụt 8,34 điểm** khi thêm
175 tài liệu nhiễu vào. Con số cũ lạc quan giả tạo vì corpus chỉ chứa tài liệu có
đáp án — retrieval gần như không thể lấy nhầm.

Hai chỗ hỏng lộ ra, **đây chính là nguyên liệu cho failure taxonomy của Tài**:

1. **Multi-hop: tỷ lệ sai bằng tỷ lệ đúng.** Nghi ngờ path discovery đứt ở bước 2 hop.
2. **Null err 31,67%.** Câu không có đáp án trong dữ liệu thì hệ thống **bịa** thay
   vì nói không biết. Thêm distractor thì err tăng 4 điểm — nó sai một cách tự tin.

⚠️ n của Multi và Null chỉ ~20 câu, sai số lớn. Cần xác nhận trên tập đầy đủ 637 câu
trước khi đưa vào báo cáo.

### Bốn việc cần làm ngay

1. **Failure taxonomy (T4–T6)** — vẫn là đường găng của cả dự án, và giờ còn quan
   trọng hơn: quy tắc đóng góp yêu cầu **Observed Problem có dữ liệu thực nghiệm**
   làm bước 1. Không có bảng phân phối lỗi thì mọi Proposed Method đều thiếu chân đế.
   Baseline 442 đã chỉ sẵn hai hướng đào: Multi-hop (42,86%) và Null (err 31,67%).
2. **Chia sẻ index 442** — 15 MB, nén còn 7,2 MB. Git không giải quyết được, cần
   GitHub Release. Phải xong **trước khi** Tài bắt đầu T4, vì task đó chạy retrieval
   thật trên đúng index này. Ai index lại sẽ ra graph khác → baseline mất tính so sánh.
3. **Hai máy còn lại chạy `ENVIRONMENT.md`** — mới PASS 1/3 máy. Và cài
   `requirements.lock.txt`: `openai` đang lệch **hai major version** giữa các máy
   (1.109.1 vs 3.10.0), `tenacity` lệch một — cả hai là phụ thuộc trực tiếp của
   `minirag/llm/gemini.py`.
4. **Sàn nhiễu là 1,53, không phải 0,29** — cả nhóm dùng ngưỡng **3 điểm**. Ai còn
   dùng ngưỡng 0,6 cũ sẽ kết luận nhầm rằng nhiễu là cải tiến.

### Sai lệch đã biết so với bài báo

Ghi lại để đưa vào phần Limitations, không phải lỗi cần sửa gấp:

- **Model**: `gemini-flash-lite` làm **cả 4 việc** — trích xuất entity lúc index (`operate.py:271`), gleaning (`:275`), phân tích câu hỏi (`:1425`), sinh câu trả lời (`:1474`). MiniRAG chỉ có một `llm_model_func`, không tách được. **Đồ thị 770 node là do Gemini dựng, không phải SLM.**
- **Lần chạy cuối đã đổi sang SLM** (`Qwen2.5-3B` hoặc `Phi-3.5-mini`) qua vLLM trên GPU thuê, ~2 USD — vì luận điểm của bài báo là SLM. Phải **index lại bằng chính SLM đó**. Xem `CLAUDE.md` §1.
- **Baseline 57,33% cao hơn MỌI dòng trong bảng bài báo**, kể cả `gpt-4o-mini` (54,08%). Nguyên nhân: model mạnh hơn dựng đồ thị sạch hơn **và** viết câu trả lời tốt hơn từ context nhiễu.
- **Cache LLM rỗng**: đã điều tra xong — `gemini.py:270` và `openai.py:109` cùng `kwargs.pop("hashing_kv", None)` rồi bỏ qua. **Hành vi upstream**, không phải lỗi fork.
- **Judge**: Gemini Flash-Lite 3 lượt, bài báo dùng GPT-4o 3 lượt
- **Đồ thị thưa hơn upstream** do bản vá O(N²) (upstream trích xuất lặp nên gom thêm entity)
- **Dataset có 2 dòng trùng**: 637 dòng nhưng chỉ **635 câu duy nhất**
- **Không có câu nào thiếu file evidence** — kiểm lại 09/09/2026, cả 637 câu đều trỏ tới file có thật. Con số "68 câu" ghi trước đây là **sai**: nó đếm câu trỏ tới tài liệu *chưa index* hồi corpus 267, không phải file không tồn tại. **Không có trần điểm cứng do dữ liệu.**
