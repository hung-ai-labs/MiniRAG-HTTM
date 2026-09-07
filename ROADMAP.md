# MiniRAG Research Project — Roadmap 3 Phase

> Reproduce → Analyze → Improve → Prove
> 3 thành viên: **Hùng** (Retrieval & Proposed Method) · **Tài** (Baseline & Failure Analysis) · **HuyDog** (Experiment & Evaluation)

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
| 3 | `T2*` Chạy baseline gốc và **đóng băng `baseline.yaml`** | Tài | → 2 | ✅ |
| 4 | `T3*` End-to-end architecture map (raw docs → graph → answer) | Tài | → 2 · `‖ A` | ⬜ |
| 5 | `H1` **Retrieval Code Map** (Query Mapping / Path Discovery / Chunk Extraction) | **Hùng** | → 2 · `‖ A` | ✅ |
| 5b | `H1b` **Retrieval Flow** + **Query Trace** 3 query thật | **Hùng** | → 5 | ✅ |
| 6 | `HD1` Automated Experiment Runner (config → retrieve → generate → evaluate → results.json) | HuyDog | → 3 · `‖ B` | ⬜ |
| 7 | `HD-Schema` Chuẩn hoá schema log kết quả từng query | HuyDog | → 6 · `‖ B` | ⬜ |
| 8 | `T4` Thu tập **failed-query dataset** (≥20–50 câu, kèm retrieved chunks) | Tài | → 3 | 🔄 |
| 9 | `T5` **6-Stage Failure Taxonomy** — phân loại từng câu lỗi | Tài | → 8 | ⬜ |
| 10 | `T6` Failure Distribution Statistics (tỷ lệ % mỗi nhóm lỗi + ví dụ thật) | Tài | → 9 | ⬜ |
| 11 | `T7*` Research Problem Statement — chốt bài toán cần giải | Tài | → 10 | ⬜ |

**Song song:** nhóm `A` (task 4, 5) chạy cùng lúc — đọc code không cần chờ baseline chạy xong. Nhóm `B` (task 6, 7) chạy cùng lúc với 8–10 — HuyDog xây runner trong khi Tài phân tích lỗi.

**Cổng ra Phase 1:** có `baseline.yaml` đóng băng + bảng phân phối 6 nhóm lỗi. **Không có bảng này thì Phase 2 chỉ là đoán mò.**

---

## PHASE 2 — Thăm dò & Xây dựng cải tiến

*Tương ứng Week 04–06: Research Exploration → Method Selection → Implementation*
**Mục tiêu:** từ bằng chứng lỗi ra được một Proposed Method chạy được trên pipeline chung.

| # | Task | Người | Phụ thuộc / Song song | ✓ |
|---|---|---|---|---|
| 12 | `H2` Trace retrieval của các query lỗi (entity sót? path cụt? chunk xếp hạng thấp?) | **Hùng** | → 5, 10 | ⬜ |
| 13 | `H3*` Retrieval baseline analysis — báo cáo nhận xét retrieval gốc | **Hùng** | → 12 | ⬜ |
| 14 | `HD2*` Top-K sensitivity study (K = 1, 3, 5, 7, 10) theo từng loại query | HuyDog | → 6 · `‖ C` | ⬜ |
| 15 | `HD3*` Context efficiency — tỷ lệ chunk rác, chunk trùng lặp | HuyDog | → 6 · `‖ C` | ⬜ |
| 16 | `H4` **Lexical prototype (BM25)** — cứu thực thể hiếm | **Hùng** | → 13 | ⬜ |
| 17 | `H5` **Fixed hybrid fusion** (dense + lexical) | **Hùng** | → 16 | ⬜ |
| 18 | `H6` **Adaptive / router** — phân loại query rồi chọn chiến lược | **Hùng** | → 17 | ⬜ |
| 19 | `H7` Chốt phương án và **hiện thực Proposed Method** thành module interface sạch | **Hùng** | → 18 | ⬜ |
| 20 | `H8` Tài liệu thuật toán & tham số | **Hùng** | → 19 · `‖ D` | ⬜ |
| 21 | `T8*` Integration branch — merge Proposed Method, không làm gãy pipeline | Tài | → 19 · `‖ D` | ⬜ |

**Song song:** nhóm `C` (14, 15) là việc của HuyDog, chạy độc lập trong khi Hùng làm 12–13. Nhóm `D` (20, 21) chạy cùng lúc sau khi có code.

**Ràng buộc:** task 16 → 17 → 18 **phải tuần tự** — mỗi bước là một giả thuyết đơn biến, gộp lại thì không biết cái nào tạo ra hiệu quả.

**Cổng ra Phase 2 (DoD của Hùng):** một modification chỉ tính là xong khi *chạy được trên pipeline chung*, *có baseline comparison*, và *giải thích được nó sửa nhóm lỗi nào trong 6 nhóm*.

---

## PHASE 3 — Chứng minh & Báo cáo

*Tương ứng Week 07–08: Full Experiment → Report*
**Mục tiêu:** chứng minh cải tiến là thật, hoặc ghi nhận trung thực rằng nó không hiệu quả.

| # | Task | Người | Phụ thuộc / Song song | ✓ |
|---|---|---|---|---|
| 22 | `HD-Final` Full benchmark **Baseline vs Proposed** trên cùng 100% điều kiện | HuyDog | → 19, 21 | ⬜ |
| 23 | `HD-Ablation` Ablation study — tách riêng Lexical / Graph / Adaptive | HuyDog | → 22 | ⬜ |
| 24 | `H9` Hỗ trợ HuyDog chạy ablation (bật/tắt từng thành phần) | **Hùng** | → 23 (đồng thời) | ⬜ |
| 25 | Bảng đối chiếu 4 chỉ số: **Accuracy · Recall@K · Latency · Tokens** | HuyDog | → 23 | ⬜ |
| 26 | **Họp Keep / Reject** — quyết định dựa trên số liệu | **Cả nhóm** | → 25 | ⬜ |
| 27 | `T10*` Error Analysis section | Tài | → 26 · `‖ E` | ⬜ |
| 28 | `H10` Proposed Method section | **Hùng** | → 26 · `‖ E` | ⬜ |
| 29 | `HD-Report*` Experiment & Result section | HuyDog | → 26 · `‖ E` | ⬜ |
| 30 | Ghép báo cáo khoa học cuối | **Cả nhóm** | → 27, 28, 29 | ⬜ |

**Song song:** nhóm `E` (27, 28, 29) — ba người viết ba mục cùng lúc sau khi đã chốt Keep/Reject.

**Lưu ý:** nếu họp Keep/Reject ra kết luận **Reject**, vẫn phải viết đủ 3 mục và ghi nhận **negative findings**. Đó là kết quả khoa học hợp lệ, không phải thất bại.

---

## Trạng thái thật tính đến 07/09/2026

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
| Environment guide (`T1*`) | 🔄 | Chưa có hướng dẫn cài đặt chạy được trên máy cả 3 người |
| Failed-query dataset, Failure Taxonomy | ⬜ | Chưa bắt đầu — **đây là nút thắt chặn Phase 2** |

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

### Ba việc cần làm ngay

0. **Kiểm chứng bug bước ④** *(mới, ưu tiên cao nhất)* — Query Trace cho thấy
   `get_node_from_types` không bao giờ khớp do lệch hoa/thường, khiến cơ chế
   answer-type-aware của MiniRAG **không chạy**. Sửa một dòng, **không cần index
   lại**. Cần đo trước/sau trên dev set 200 để biết ảnh hưởng thật.
1. **Failure taxonomy (T4–T6)** — đường găng của cả dự án. Hùng không sang được `H2`
   nếu chưa có tập query lỗi đã gán nhãn. Baseline 442 đã chỉ sẵn hai hướng đào:
   Multi-hop và Null.
2. **Environment guide (`T1*`)** — `baseline.yaml` đã có, nhưng chưa ai ngoài máy này
   dựng lại được môi trường. Không có nó thì `baseline.yaml` chỉ là giấy.
3. **Sàn nhiễu mới là 1,53, không phải 0,29** — cả nhóm phải dùng ngưỡng **3 điểm**.
   Ai còn dùng ngưỡng 0,6 cũ sẽ kết luận nhầm rằng nhiễu là cải tiến.

### Sai lệch đã biết so với bài báo

Ghi lại để đưa vào phần Limitations, không phải lỗi cần sửa gấp:

- **Model**: Gemini Flash-Lite, bài báo dùng gpt-4o-mini → lần chạy cuối cần OpenAI (~$10 cho 2 lượt full)
- **Cache LLM rỗng**: `kv_store_llm_response_cache.json` 0 entry dù `enable_llm_cache=True` — nghi bug upstream thứ hai, chưa điều tra
- **Judge**: Gemini Flash-Lite 3 lượt, bài báo dùng GPT-4o 3 lượt
- **Đồ thị thưa hơn upstream** do bản vá O(N²) (upstream trích xuất lặp nên gom thêm entity)
- **Dataset có 2 dòng trùng**: 637 dòng nhưng chỉ **635 câu duy nhất**
- **68 câu có `Evidence` trỏ tới file không tồn tại** trong dataset — không hệ thống nào trả lời đúng được
