# Kiểm toán truy hồi B2 — hồ sơ kết quả phủ định (19–20/09/2026)

> Toàn bộ **offline**: 0 lời gọi sinh, 0 lời gọi giám khảo, 0 GPU. Không sửa một dòng nào trong `minirag/`.
> Evidence và đáp án vàng **chỉ** dùng để đánh giá/chẩn đoán, không bao giờ là đầu vào lúc chạy.
> Hướng **xếp hạng lại tất định (deterministic reranking)** đóng lại ở đây theo quyết định của nhóm 20/09/2026.

Chi tiết nằm ở hai file, file này là bản tổng hợp và nhật ký quyết định:
- [`BASELINE_B2.md`](BASELINE_B2.md) — giai đoạn 0–3: mốc B2, chẩn đoán, cơ chế cửa sổ W = 400, luật dừng, overflow-rescue.
- [`RANKING_DEPTH.md`](RANKING_DEPTH.md) — chẩn đoán độ sâu xếp hạng và bảng độ phủ 9 tín hiệu tất định.

## 1. Tái dựng B2 đông lạnh

`dump_contexts.py` dựng lại context dev 200 hoàn toàn offline (parser từ khoá đọc cache, `MINIRAG_KW_CACHE_ONLY=1`):
`context_sha256` **trùng 198/198** câu có context với B2 đã đông lạnh; 2 câu còn lại vốn không có context. Tái dựng A1 từ
`ranked_ids` khớp `chunk_ids` 200/200. Tính lại hạng BM25 khớp `bm25_ids` đã log 200/200; hạng vector khớp 200/200 khi áp
ngưỡng `cosine_better_than_threshold = 0,2` của nano-vectordb (34/200 câu vì ngưỡng này mà có < 30 kết quả vector).

→ Mọi số bên dưới nói về đúng hệ thống đang chạy, không phải một bản dựng lại gần giống.

## 2. Recall ứng viên — không phải nút thắt

| | B2, 180 câu dev có evidence |
|---|---:|
| chunk đáp án có trong ứng viên (≤ 60 chunk trộn) | 203/207 = **98,1%** |
| câu đủ **mọi** chunk đáp án trong ứng viên | 97,8% |

Bước truy hồi tìm ra bằng chứng. Vấn đề nằm ở bước chọn sau đó.

## 3. Chẩn đoán cắt A1@4000 — bằng chứng mất ở khâu chọn theo ngân sách cố định

| | |
|---|---:|
| chunk đáp án còn sau A1 | 178/207 = 86,0% |
| câu đủ mọi chunk đáp án sau A1 | 83,9% (151/180) — tụt từ 97,8% |
| trong 29 câu hỏng: **tìm được nhưng bị A1 cắt** | **25 (86%)** |
| không có trong ứng viên | 4 (14%) |
| ngân sách bỏ trống vì A1 dừng ở chunk đầu tiên làm tràn | trung vị 398 token |
| chính chunk đáp án dài 1.200 token | 16/25 |

**Khoảng trống đo được:** B2 đúng 85,9% ở câu đủ chunk đáp án nhưng chỉ 20,0% ở 25 câu bị cắt → trần của mọi cơ chế chọn
chunk ≈ **+8,2 điểm acc dev**, lớn hơn sàn nhiễu sinh (3 lượt V3 cùng cấu hình chênh 1,5 điểm) và gấp đôi ngưỡng tầng D
(4,18 điểm). Khoảng trống này **vẫn còn mở**.

## 4. Kết quả phủ định 1 — cửa sổ trong chunk dài, W = 400 (chỉ mô phỏng offline)

Luật dừng 6 cổng chốt **trước** khi chạy (xem `BASELINE_B2.md`). Kết quả: **trượt 3/6 cổng**.

| Cổng | Kết quả | |
|---|---|---|
| P — đáp án nguyên văn trong Sources (94 câu) | 82 → 85 · 5 lên / 2 xuống · p = 0,45 | **TRƯỢT** |
| E — đủ chunk đáp án (180 câu) | 151 → 163 · 12 lên / 0 xuống · p = 0,0005 | đạt |
| Multi net ≥ −1 | E +1 · P 0 | đạt |
| token Sources trung vị ±5% | 3.602 → 3.867 (**+7,4%**) | **TRƯỢT** |
| context đổi ≥ 20 câu | 178/200 | đạt |
| an toàn Null: sự kiện phân biệt +≤ 25% | Null 10,5 → 14,0 (**+33%**) | **TRƯỢT** |

Cửa sổ nạp thêm ~60% số mảnh vào cùng ngân sách (8 → 13 chunk), nên câu Null có thêm 33% sự kiện phân biệt để ghép thành
sự kiện sai — đúng cơ chế ảo giác đang phải tránh.

## 5. Kết quả phủ định 2 — overflow-rescue, dừng ngay ở bước đo độ phủ (chỉ mô phỏng offline)

Cơ chế chỉ tác động lên đúng một chunk (chunk đầu tiên làm tràn), nên chỉ cứu được câu mà chunk đó là chunk đáp án.

| | |
|---|---|
| độ phủ | **5/25** ca (Single 5/21, **Multi 0/4**); 5/17 ca chunk đáp án dài |
| trần tuyệt đối | ≈ +1,6 điểm dev — **dưới** dải nhiễu sinh 1,5 và ≈ 40% ngưỡng tầng D |
| Null | chunk tràn đầu tiên thuộc **sự kiện mới** ở **20/20** câu Null |

Không tiền đăng ký, không mô phỏng, không viết code. Hệ quả quan trọng: chính sách "dừng ở chunk tràn đầu tiên" chỉ gây
5/25 ca mất bằng chứng — **20/25 ca còn lại là do thứ tự xếp hạng**, không phải do biên tràn.

## 6. Chẩn đoán độ sâu xếp hạng (20 ca còn lại)

| Nhóm | Số ca | Nghĩa |
|---|---:|---|
| A — BM25 xếp cao, RRF kéo xuống | **8** | BM25 đặt chunk đáp án hạng 1–5, vector không có nó (6/8 vắng hẳn) |
| B — vector xếp cao, RRF kéo xuống | 0 | |
| C — cả hai cao mà hạng trộn vẫn sâu | 0 | |
| D — không bộ nào xếp cao | **12** | cả BM25 lẫn dense đều yếu với chunk này |

Chunk đáp án: hạng BM25 `[1,1,2,2,2,3,5,5,6,7,10,11,12,18,26, +5 ngoài top-30]`; hạng vector
`[12,14,15,16,16,20,20,23,27,28, +10 ngoài top-30]`.

**372 chunk chiếm chỗ:** 74% cosine cao hơn chunk đáp án · 59% BM25 cao hơn · 48% có ở cả hai danh sách · 42% khớp đủ thực
thể câu hỏi · 30% dài ≥ 800 token · gần trùng 0% · cùng tài liệu 4% · sai ngày 3%. Dạng trội là **cùng thực thể, cùng chủ
đề, và chính các bộ truy hồi chấm là liên quan hơn chunk đáp án**.

## 7. Phân tích BM25 / vector / RRF — phát biểu đúng phạm vi

Nguồn chunk đáp án ở 20 ca: **chỉ BM25 10 · chỉ vector 5 · cả hai 5**, trong khi trên toàn dev 85% chunk đáp án có mặt ở
cả hai danh sách.

- **Được viết:** trên bộ dữ liệu LiHua-World và cấu hình này, RRF (k = 60) chỉ cộng điểm từ danh sách nào chứa chunk, nên
  **một phần** chunk đáp án chỉ được **một** bộ truy hồi tìm thấy bị pha loãng so với chunk có mặt ở cả hai danh sách dù
  hạng tầm thường — đó là 8/20 ca. **Phần lớn ca còn lại (12/20) đã yếu sẵn ở cả BM25 lẫn dense**, nên đổi cách trộn không
  cứu được chúng.
- **Không được viết:** "RRF xấu", "RRF làm hại truy hồi", hay bất kỳ phát biểu phổ quát nào về reciprocal rank fusion.
  Chưa hề có phép thử RRF trên corpus khác, tham số k khác, hay bộ truy hồi khác.

## 8. Bảng độ phủ 9 tín hiệu tất định (điều kiện cần, không phải mô phỏng)

| Tín hiệu | Cứu /20 | Câu tốt có rủi ro /151 | Multi (cứu / rủi ro) | Null: kéo chunk ngoài vào / dạng gần giống | Kết |
|---|---:|---:|---|---|---|
| S1 đồng thuận hai bộ | 0 | 0 | 0 / 0 | 0 / 0 | loại — chính là nguyên nhân nhóm A |
| S2 độ phủ idf | **9** | 12 | 2 / 6 | 15 / 10; chunk gây nhầm L052 đứng đầu | loại — Null |
| S3 độ phủ thực thể | 3 | 3 | 1 / 0 | 6 / 3 | loại — độ phủ thấp |
| S4 khớp ngày | 2 | 0 | 0 / 0 | 2 / 1 | loại — độ phủ thấp |
| S5 ưu tiên chunk ngắn | 6 | **111** | 2 / 9 | 20 / 10 | loại — phá câu đang tốt |
| S6 khác tài liệu | 0 | 6 | 0 / 0 | 0 / 0 | loại |
| S7 điểm BM25 | **9** | 7 | 2 / 2 | 16 / 9; L052 đứng đầu | loại — Null |
| S8 cosine | 3 | 34 | 1 / 4 | 18 / 7 | loại |
| S9 hạng tốt nhất ở một bộ | 5 | 8 | 1 / 2 | 16 / 11 | loại — vùng 3–5 và Null |

Không tín hiệu nào dùng Evidence, Type hay phán quyết lúc chạy. Cột "cứu" là **cận trên** (điều kiện cần theo nợ token),
không phải kết quả xếp lại thật.

## 9. An toàn Null — lý do loại trực tiếp

Hai tín hiệu phủ nhiều nhất (S2 độ phủ idf, S7 điểm BM25, cùng 9/20) đều dựa trên mức khớp từ vựng với câu hỏi:
- kéo chunk ngoài Sources vào ở **15–16/20 câu Null**, trong đó 9–10 câu là chunk khớp **đủ** thực thể câu hỏi — đúng dạng
  "sự thật gần giống";
- cả hai xếp **chunk gây nhầm của L052** (lời khuyên dùng whey tháng 2, bị gán sang ngày 19/09) lên **hạng 1** (percentile 0,00).

Luật quyết định đã chốt trước: tín hiệu làm tăng bằng chứng gây nhầm cho Null thì **loại trước khi mô phỏng**. Cả hai bị loại.

## 10. Vì sao dừng

Cái làm nổi bằng chứng thật cho câu trả lời được **cũng chính là** cái làm nổi sự thật gần giống cho câu Null. Mọi tín
hiệu bề mặt tất định đã thử đều là biến thể của "mức khớp câu hỏi", nên chúng không tách được hai nhóm này.

- **Được viết:** *"Khoảng trống truy hồi vẫn còn và đo được (≈ +8,2 điểm dev). Nhưng các tín hiệu bề mặt tất định đã thử
  không thu hồi được nó một cách an toàn: chúng đồng thời làm tăng bằng chứng gây nhầm cho nhóm Null."*
- **Không được viết:** "truy hồi đã hết dư địa", "không còn gì để cải thiện ở khâu truy hồi".

**Đóng lại:** không viết reranker, không tiền đăng ký reranker, không chạy sinh/giám khảo cho hướng này.
**W = 400 và overflow-rescue là thí nghiệm phủ định offline** — `simulate.py` là script mô phỏng, **không** phải tính năng
runtime; không có dòng nào của hai cơ chế này nằm trong `minirag/`.

## Hiện vật

| File | Vai trò |
|---|---|
| `reproduce/retrieval_audit/dump_contexts.py` | dựng lại context dev 200 offline (0 lời gọi LLM) |
| `reproduce/retrieval_audit/run_offline.sh` | wrapper env cho hai script trên |
| `reproduce/retrieval_audit/diagnose.py` | chỉ số 1–9 + bảng phân loại thất bại |
| `reproduce/retrieval_audit/simulate.py` | **mô phỏng offline** quy tắc cửa sổ W = 400 (kết quả phủ định) |
| `reproduce/retrieval_audit/ranking_depth.py` | phân nhóm A–E, đặc điểm chunk chiếm chỗ, 9 tín hiệu, kiểm Null |
| `logs/retrieval_audit/*.txt`, `fail_list.json`, `ranking_depth.json` | kết quả thô |
| *(bỏ khỏi git)* `vector_bm25_dev_ctx.jsonl` 4,4 MB, `simulate_ids.json` | dựng lại bằng `dump_contexts.py` / `simulate.py` |

**Giới hạn của chính hồ sơ này:** "cứu được"/"rủi ro" là điều kiện cần tính theo nợ token, không phải xếp lại thật; kiểm
Null dùng proxy cộng 3 chunk gây nhầm do tôi xác định khi đọc (L002, L055, L052), chưa có người rà lại; dev chỉ có 20 ca
độ sâu và 20 câu Null.
