# Chẩn đoán độ sâu xếp hạng — 20 ca mất bằng chứng không phải do chunk tràn đầu tiên

> 19/09/2026 · offline, dev 200, B2 đông lạnh (`vector_bm25_dev_ctx.jsonl`, hash trùng 198/198).
> Không reranker, không đăng ký trước reranker, không sinh, không chấm.
> Evidence chỉ dùng để đánh giá.

## Định nghĩa chốt TRƯỚC khi xem số đếm theo nhóm

**Tập 20 ca:** câu có evidence, mọi chunk đáp án có trong ứng viên, ít nhất một chunk đáp án không vào Sources, và chunk
tràn đầu tiên của A1 **không** phải chunk đáp án. Mỗi câu xét chunk đáp án bị cắt có hạng RRF cao nhất.

**"Cao" trong một bộ truy hồi = hạng ≤ 5 trong top-30 của bộ đó.** Lý do: Sources của B2 chứa trung vị 8 chunk, RRF xen kẽ
hai danh sách, nên chunk đứng top-5 ở một bộ thì nếu chỉ xét riêng bộ đó sẽ nằm trong khoảng hạng trộn ≤ 10 — vùng vào
được ngân sách. "Thấp" = hạng > 10 hoặc không có trong top-30. 6–10 = giữa.

| Nhóm | Điều kiện |
|---|---|
| A | BM25 cao, vector không cao → RRF kéo xuống |
| B | vector cao, BM25 không cao → RRF kéo xuống |
| C | cả hai cao nhưng hạng trộn vẫn quá sâu |
| D | không bộ nào cao |
| E | khác, chỉ khi có bằng chứng rõ |

**Tín hiệu "có thể cứu" một ca (điều kiện cần, không phải mô phỏng):** gọi *nợ token* = tổng token từ đầu danh sách tới hết
chunk đáp án trừ 4.000. Tín hiệu cứu được ca đó nếu các chunk **không phải đáp án** đứng trên chunk đáp án và có giá trị
tín hiệu **kém hơn hẳn** chunk đáp án có tổng token ≥ nợ token — tức hạ chúng xuống dưới chunk đáp án là đủ chỗ.

**Rủi ro với câu đang tốt (151 câu đủ đáp án):** đối xứng — chunk đáp án đang trong Sources bị đẩy ra nếu các chunk không
phải đáp án đứng **dưới** nó có tín hiệu **tốt hơn hẳn** và tổng token ≥ phần ngân sách còn dư sau nó.

**Rủi ro Null:** trên 20 câu Null dev, tín hiệu được coi là tăng bằng chứng gây nhầm nếu nó đưa lên Sources những chunk
khớp thực thể/từ khoá câu hỏi nhiều hơn B2 — đúng dạng "sự thật gần giống" gây ảo giác. Thêm kiểm trên các chunk gây nhầm
đã xác định khi đọc 9 câu Null B2 sai (`giai_phap_null_b2_do_phu.md`).

## Kết quả (`ranking_depth.txt`) → **DỪNG: không tín hiệu nào đáng làm thí nghiệm xếp hạng lại**

Kiểm tái dựng: BM25 khớp 200/200; vector khớp 200/200 khi áp ngưỡng cosine 0,2 của nano-vectordb (34/200 câu có < 30
kết quả vector vì ngưỡng này).

**Phân nhóm 20 ca:** A 8 · B 0 · C 0 · D 12.
- A (8): BM25 xếp chunk đáp án hạng 1–5, vector không có nó (6/8 vắng hẳn trong danh sách vector). RRF chỉ cho điểm một
  danh sách, nên thua chunk có mặt ở cả hai danh sách dù hạng tầm thường → **RRF pha loãng**.
- D (12): không bộ nào xếp chunk đáp án ≤ 5 → **cả hai bộ truy hồi đều yếu** với các chunk này.
- Nguồn chunk đáp án ở 20 ca: chỉ BM25 10 · chỉ vector 5 · cả hai 5 — trong khi trên toàn dev 85% chunk đáp án có mặt ở cả
  hai. Thất bại độ sâu tập trung ở chunk đáp án **một nguồn**.

**Chunk chiếm chỗ (372):** 74% có cosine cao hơn chunk đáp án, 59% BM25 cao hơn, 48% có mặt ở cả hai danh sách, 42% khớp
đủ thực thể câu hỏi, 30% dài ≥ 800 token; gần trùng 0%, cùng tài liệu 4%, sai ngày 3%. Dạng trội: **cùng thực thể / cùng chủ
đề mà chính các bộ truy hồi chấm là liên quan hơn**.

| Tín hiệu | Cứu được (điều kiện cần) | Câu tốt có rủi ro | Multi (cứu / rủi ro) | Null: kéo chunk ngoài vào / dạng gần giống | Khuyến nghị |
|---|---:|---:|---|---|---|
| S1 đồng thuận hai bộ | 0 | 0 | 0 / 0 | 0 / 0 | loại — chính là nguyên nhân nhóm A |
| S2 độ phủ idf | 9 | 12 | 2 / 6 | 15 / 10; chunk gây nhầm L052 đứng đầu | loại — Null |
| S3 độ phủ thực thể | 3 | 3 | 1 / 0 | 6 / 3 | loại — độ phủ thấp |
| S4 khớp ngày | 2 | 0 | 0 / 0 | 2 / 1 | loại — độ phủ thấp |
| S5 chunk ngắn | 6 | 111 | 2 / 9 | 20 / 10 | loại — rủi ro lớn |
| S6 khác tài liệu | 0 | 6 | 0 / 0 | 0 / 0 | loại |
| S7 điểm BM25 | 9 | 7 | 2 / 2 | 16 / 9; L052 đứng đầu | loại — Null |
| S8 cosine | 3 | 34 | 1 / 4 | 18 / 7 | loại |
| S9 hạng tốt nhất một bộ | 5 | 8 | 1 / 2 | 16 / 11 | loại — vùng 3–5 và Null |

Hai tín hiệu phủ nhiều nhất (S2, S7: 9/20) nằm ở vùng "không chắc", và cả hai đẩy đúng chunk gây nhầm của L052 (lời khuyên
whey) lên đầu, kéo chunk ngoài vào 15–16/20 câu Null, trong đó 9–10 câu là chunk khớp đủ thực thể — dạng "sự thật gần giống".
Theo luật quyết định: tín hiệu tăng bằng chứng gây nhầm cho Null thì loại trước khi mô phỏng.
