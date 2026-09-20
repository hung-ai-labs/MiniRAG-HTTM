# CE1 — Đăng ký trước: xếp hạng lại bằng cross-encoder tiền huấn luyện

> 20/09/2026 · Viết **trước khi chấm bất kỳ cặp (câu hỏi, chunk) nào của dev**. Chỉ offline: không gọi sinh, không gọi
> giám khảo, không sửa `minirag/`. Evidence và đáp án vàng **chỉ** dùng để đánh giá, không bao giờ vào đầu vào model.

## Giả thuyết (chỉ là giả thuyết)

Một cross-encoder nhỏ đọc **đồng thời** `[câu hỏi, chunk]` có thể phân biệt **bằng chứng thật sự hỗ trợ** với chunk
*cùng chủ đề nhưng không hỗ trợ* tốt hơn BM25, cosine, độ phủ idf và các tín hiệu tất định khác đã bị loại ngày 19/09
(`logs/retrieval_audit/README.md`).

Các phân biệt quan tâm: *được khuyên ≠ đã dùng · dự định ≠ đã làm · người A ≠ người B · sự kiện A ≠ sự kiện B ·
ngày A ≠ ngày B · sự thật liên quan ≠ bằng chứng hỗ trợ*.

**Không giả định nó chạy được.** Phép thử offline phải chứng minh, nếu không thì ghi kết quả phủ định.

## B2 là bản dự phòng vĩnh viễn

B2 = vector top-30 + BM25 top-30 → RRF(k=60) → A1@4000 → Qwen2.5-3B không đổi. Thí nghiệm này **không** sửa B2.
Nếu CE1 trượt cổng thì bỏ chế độ mới, giữ B2 làm hệ thống chính thức. Không có code runtime nào được viết trước khi
báo cáo offline và được duyệt.

## Phase 0 — mốc B2 xác nhận lại (20/09/2026)

| | |
|---|---|
| Đường đi | `minirag/operate.py`, `_build_mini_query_context`: `chunks_vdb.query(originalquery, top_k=30)` → `_bm25_index(...).rank(originalquery, 30)` → `_rrf_fuse(chunks_ids, bm25_ids)` (dòng ~1481–1518) → `truncate_list_by_token_size(..., 4000)` (dòng ~1553) |
| Công tắc | `MINIRAG_CHUNK_FUSION=vector_bm25`, `top_k=60`, `max_token_for_text_unit=4000` |
| A1 | duyệt theo thứ tự trộn, **dừng ở chunk đầu tiên làm tràn 4.000 token** (`minirag/utils.py:189`), tiktoken gpt-4o |
| Ứng viên | trung vị **48** id/câu (min 30, max 60) |
| Kiểm hash | `logs/retrieval_audit/vector_bm25_dev_ctx.jsonl` so với `logs/screening/b2/answers.jsonl`: `context_sha256` trùng **198/198**; 2 câu còn lại không có context. Dựng lại A1 từ `ranked_ids` khớp `chunk_ids` **200/200** |
| Tập dev | 200 câu: Single 159 · Multi 21 · Null 20 |
| Hiện vật tái dùng | `vector_bm25_dev_ctx.jsonl` (ứng viên + thứ tự + context), `LiHua-World-qwen-modal/kv_store_text_chunks.json`, `logs/diag_path2chunk.jsonl` (gold), `logs/retrieval_audit/ranking_depth.json` (20 ca) |

## Phase 1 — model chốt trước khi thấy kết quả

| | |
|---|---|
| Model | `cross-encoder/ms-marco-MiniLM-L6-v2` |
| Revision ghim | `233902d25c440f23af6f7d6e94d2946bac0bee0a` |
| Kiến trúc | `BertForSequenceClassification`, 6 lớp, hidden 384, 12 đầu, `num_labels=1` (điểm thô, không sigmoid) |
| Tham số | 22,71 M |
| Tokenizer | `BertTokenizer`, vocab 30.522, `model_max_length=512` |
| Độ dài tối đa | 512 wordpiece kể cả `[CLS] q [SEP] p [SEP]` |
| Thiết bị | **CPU, float32** (chốt vì tái lập được; MPS chỉ dùng nếu cần tốc độ, phải kiểm trùng thứ hạng) |
| Kích thước lô | 32 |
| Cách chấm | điểm thô của `logits[:, 0]`; xếp giảm dần; **hoà điểm → giữ thứ tự RRF của B2** (ổn định, tất định) |
| Tập được xếp lại | đúng `ranked_ids` của B2 — **không** thêm ứng viên, **không** đổi vector/BM25/RRF/A1/prompt |

**Chính sách cắt (chốt trước, có lý do a priori — không phải nút vặn):** trung vị chunk ứng viên là 276 wordpiece nhưng
p90 là 1.223 và **34% chunk ứng viên vượt 480 wordpiece**. Cắt thẳng sẽ biến thí nghiệm thành "chấm 480 wordpiece đầu
của chunk" chứ không phải chấm chunk. Vì vậy dùng **MaxP** (Dai & Callan 2019): với mỗi cặp, cửa sổ = `512 − len(q) − 3`
wordpiece, bước nhảy = `cửa sổ // 2` (chồng 50%), điểm của chunk = **max** điểm các cửa sổ. Chi phí đo trước: 9.351 cặp →
**18.723 cửa sổ** (2,00 cửa sổ/cặp).

*FirstP (cắt thẳng) được ghi lại như số đối chiếu cố định, và **không được phép** đổi quyết định.*

**Lỗi môi trường đã gặp và cách ghim.** `from_pretrained` nạp safetensors qua mmap làm tiến trình chết SIGBUS (exit 138)
với torch 2.14.0 + transformers 5.16.1 trên máy này; `all-MiniLM-L6-v2` không bị. Cách nạp ghim: `safetensors.torch.load_file`
→ `.clone()` từng tensor vào RAM → `BertForSequenceClassification(config).load_state_dict(..., strict=False)`. Kiểm:
điểm theo lô **trùng khít** điểm từng cặp (`[8.4846, −4.3201, −11.2703]` cho ví dụ Berlin liên quan / cùng chủ đề / không
liên quan), nên chấm không phụ thuộc padding và tất định.

**Chi phí đo trước:** CPU ~59 cửa sổ/s → **~5,3 phút** cho cả dev 200; MPS bs=64 ~105 cửa sổ/s → ~3,0 phút.
Suy ra độ trễ runtime mỗi câu: 48 ứng viên × 2,00 cửa sổ ≈ 96 cửa sổ ≈ **1,6 s/câu trên CPU**, ~0,9 s trên MPS.

**Không làm:** không so nhiều reranker rồi chọn con thắng · không fine-tune · không dùng Qwen làm reranker · không gọi
LLM theo từng chunk · không đổi embedding · không index lại · không đổi BM25 / RRF / A1@4000 / prompt sinh.

## Phase 2–5 — đo cái gì

Với mỗi câu: ứng viên B2 → điểm cross-encoder → xếp lại **cùng tập ứng viên** → **cùng A1@4000** → đánh giá offline.

- **Phase 3 (mục tiêu chính, 20 ca độ sâu xếp hạng)** — hạng chunk đáp án trước/sau; có vào được A1 không; giữ đủ bằng
  chứng; giữ đáp án nguyên văn; mất→giữ; giữ→mất; tách Single/Multi. Mỗi ca xếp đúng một nhóm:
  **A** đủ để vào context · **B** hạng tốt lên nhưng chưa vào · **C** không đổi · **D** tệ đi.
- **Phase 4 (an toàn Null, bắt buộc)** — chunk nào mới vào A1, chunk nào rời đi; số sự kiện phân biệt (`Time:`) trong
  Sources; mức khớp thực thể của chunk mới vào; xung đột ngày/sự kiện đo được tất định; và **hạng của 3 chunk gây nhầm
  đã xác định**: `L002` → chunk `Time: 20260112_10:00`, `L055` → `20261113_13:00`, `L052` → `20260214_16:00`
  (lời khuyên whey tháng 2 bị gán sang 19/09). Không đặt luật tay mới từ các ca này.
- **Phase 5 (toàn dev nếu Phase 3 khả quan)** — recall ứng viên không đổi; giữ đủ bằng chứng trước/sau; giữ đáp án
  nguyên văn; hạng chunk đáp án đầu tiên; Single; Multi; Null; token context trung vị/p90; số chunk trong Sources;
  % context đổi; **và danh sách câu đang tốt bị mất bằng chứng**. Dùng thống kê ghép cặp (McNemar chính xác) cho kết
  cục nhị phân, nhưng **không** diễn giải mức giữ bằng chứng offline thành accuracy QA.

## ⛔ Luật dừng offline — chốt trước khi xem kết quả

Đi tiếp phải đạt **tất cả 8**:

| # | Cổng |
|---|---|
| 1 | **Độ phủ 20 ca:** số ca nhóm A ≥ 10 (xem màn sàng dưới) |
| 2 | **Giữ đủ bằng chứng toàn dev:** net > 0 (mất→giữ nhiều hơn giữ→mất) |
| 3 | **Multi không tụt đáng kể:** net Multi ≥ −1 ở cả "đủ bằng chứng" lẫn "đáp án nguyên văn" |
| 4 | **Null không tăng bằng chứng gây nhầm:** số sự kiện phân biệt trung vị trong Sources câu Null tăng ≤ 25%, **và** số câu Null có chunk *mới vào* khớp đủ thực thể câu hỏi ≤ 7/20 (mốc so sánh: tín hiệu tất định tốt nhất đạt 15–16/20 → bị loại) |
| 5 | **Không đẩy có hệ thống chunk gây nhầm đã biết:** trong 3 ca `L002/L055/L052`, không ca nào chunk gây nhầm lên hạng 1; không quá 1 ca nó tăng hạng |
| 6 | **Cùng trần 4.000 token:** không câu nào vượt; token Sources trung vị trong ±5% B2 |
| 7 | **Không thêm lời gọi LLM nào** |
| 8 | **Độ trễ chấp nhận được:** ≤ 3 s/câu trên CPU ở cấu hình đã ghim |

**Màn sàng độ phủ (dùng logic headroom cũ, không phải ngưỡng ý nghĩa thống kê):**

| Số ca nhóm A / 20 | Kết luận |
|---|---|
| ≈ 3–5 | không đủ → **DỪNG** |
| ≈ 10+ kèm rủi ro phụ thấp | ứng viên đáng tin |
| ở giữa (6–9) | **không chắc** — báo cáo, không tự động đẩy tiếp |

**Câu hỏi phân định, chốt cách đo trước:** model hành xử như tín hiệu **HỖ TRỢ** hay chỉ là tín hiệu **LIÊN QUAN ngữ
nghĩa mạnh hơn**?
- *Hỗ trợ*: chunk đáp án lên hạng ở câu trả lời được, **đồng thời** chunk khớp chủ đề ở câu Null **không** lên hạng
  (cổng 4 và 5 đạt).
- *Chỉ liên quan mạnh hơn*: cả hai cùng lên — đúng vết đã làm 9 tín hiệu tất định bị loại. Khi đó **DỪNG**, kể cả khi
  cổng 1 đạt.

Trượt bất kỳ cổng nào → dừng ngay, không chạy QA, không sửa runtime, ghi kết quả phủ định, giữ B2, **không tự động thử
reranker thứ hai**, không vặn ngưỡng để cứu kết quả, không fine-tune.

## Diễn giải khoa học được phép (kể cả khi thành công)

Mạnh nhất được viết: *"Một mô hình học tương tác câu hỏi–chunk cải thiện thứ tự bằng chứng bên trong đúng tập ứng viên
B2 và đúng ngân sách token hiện có."* **Không** được viết "đã giải quyết ảo giác" hay "đã giải quyết Null". Nếu truy hồi
tổng thể tốt lên nhưng Null xấu đi thì reranker **trượt** thí nghiệm này.
