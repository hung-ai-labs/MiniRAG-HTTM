# Entity Resolution E1 — Preregistration

Ngày chốt: 16/09/2026

Danh sách nhóm gộp đã rà tay:
reproduce/entity_resolution/merge_review.csv

Nhóm bị loại khỏi danh sách và lý do:
- BLOOD AND WINE: normalized name giống nhau nhưng semantic role/type QUEST và EXPANSION mâu thuẫn; không đủ bằng chứng là cùng thực thể.
- 10:00 AM / 10:00AM: cùng literal time nhưng thuộc hai sự kiện khác nhau; merge có nguy cơ tạo liên kết giả giữa ngữ cảnh không liên quan.
- KIDS / KIDS': entity_type mâu thuẫn LOCATION/PERSON và KIDS' có dấu hiệu là possessive bị parser cắt; không đủ bằng chứng cùng thực thể.

Chỉ số chính:
- Full-evidence retention trong graph top-30
- Full-evidence retention trong final chunk_ids sau giới hạn context 4k
- Paired McNemar trên 180 câu dev có evidence
- Báo riêng Single và Multi
- Ghi nhận graph_seeds, graph_paths, retrieval_ms

Cổng:
- Tất cả integrity checks phải PASS
- Graph-only: full-evidence net >= +9 và p < 0.01
- RRF: full-evidence net >= 0
- Multi chỉ báo riêng, không dùng làm gate

Dự báo trước khi đo:
- Entity resolution sẽ tăng full-evidence retention ở graph-only, kỳ vọng net khoảng +10 đến +15 câu trên 180 câu.
- RRF kỳ vọng không giảm, net khoảng 0 đến +5 câu.
- Hiệu ứng kỳ vọng rõ hơn ở Multi so với Single, nhưng Multi không dùng làm gate vì n nhỏ.

Nếu trượt cổng:
- Ghi negative finding vào ROADMAP.
- Không chạy QA.
- Không chỉnh lại danh sách merge dựa trên kết quả retrieval.
- Không chuyển sang fuzzy merge trong cùng experiment E1.

---

# Amendment 17/09/2026 — before retrieval measurement

Bổ sung TRƯỚC khi mở bất kỳ kết quả truy hồi nào. Không sửa, không xoá nội dung đăng ký gốc ở trên.

## Vấn đề phát hiện

`minirag/llm/hf.py:177-188` (`hf_embed`) lấy mean trên `last_hidden_state` qua **cả vị trí padding**
và không dùng `attention_mask`. Vì `NanoVectorDBStorage.upsert` gom văn bản thành lô
(`embedding_batch_num = 32`), vector của một bản ghi phụ thuộc vào chuỗi **dài nhất trong lô** lúc
index — một đại lượng ngẫu nhiên theo lô, không tái tạo được từ nội dung.

Bằng chứng (`logs/entity_resolution/embedding_parity.json`, 30 bản ghi untouched):
- nhúng lại như hiện tại so với vector đã commit: trung vị cosine **0,68**;
- quét mọi độ dài pad rồi lấy tốt nhất: trung vị cosine **1,000000**, nhỏ nhất 0,979563;
- ví dụ `"ALICE"`: khớp cosine **1,0000000** tại đúng `pad_len = 9` (5 token thật + 4 pad).

Nghĩa là hàm nhúng, model và cách dựng `content` đều đúng tuyệt đối; thứ không tái tạo được chỉ là
artefact padding. Hệ quả: bản gộp E1 nhúng lại 143/1.463 bản ghi quan hệ, tạo ra **hai chế độ nhúng
lẫn lộn trong cùng một kho** — một confound nằm thẳng trên `relationships_vdb.query`
(`minirag/operate.py:1411`), tức là đúng thứ E1 đo.

## Quyết định (chốt trước khi xem kết quả truy hồi)

Nhúng lại **toàn bộ** kho quan hệ của **cả hai nhánh** — control (chưa gộp) và treatment (đã gộp) —
bằng cùng một chính sách tất định:

- hàm nhúng **giữ nguyên**: `sentence-transformers/all-MiniLM-L6-v2` + `hf_embed` hiện có;
- **batch size = 1**, để không có bất kỳ padding chéo giữa các bản ghi;
- **không** đổi sang attention-mask pooling, **không** đổi model, **không** đổi công thức `content`;
- **không** nhúng lại `vdb_entities_name` và `vdb_chunks`;
- graph, chunk id, text chunks, full docs giữ nguyên.

Lý do chọn batch = 1: `minirag/kg/nano_vector_db_impl.py:138` nhúng truy vấn bằng
`embedding_func([query])`, luôn một phần tử. Batch = 1 đặt vector lưu trữ vào **đúng cùng chế độ
padding với vector truy vấn**, thay vì một chế độ lô ngẫu nhiên.

Cả hai nhánh chịu cùng một phép biến đổi, nên khác biệt còn lại giữa chúng đúng bằng một biến:
entity resolution.

## Không thay đổi

- Tập đo: **180 câu** dev có evidence = 159 Single + 21 Multi + 0 Null (`eval_set.py` chặn cứng).
- Chỉ số: full-evidence retention trong graph top-30 và trong `chunk_ids` sau cắt 4.000; McNemar ghép cặp; báo riêng Single/Multi; ghi `graph_seeds`, `graph_paths`, `retrieval_ms`.
- Cổng: graph-only net >= +9 và p < 0,01; RRF net >= 0; Multi chỉ mô tả.
- Danh sách gộp: 18 MERGE / 3 REJECT, không đổi.
- Dự báo: giữ nguyên như đăng ký gốc.

---

# Clarification 17/09/2026 (bổ sung sau khi retrieval đã khởi chạy)

Không sửa hai mục ở trên. Mục này làm rõ cách diễn đạt và ghi lại các thay đổi ở lớp phân tích.
Nó **không** phải đăng ký trước đo lường cho các thay đổi được mô tả bên dưới.

## 1. Về câu "đúng tuyệt đối" trong Amendment

Câu *"hàm nhúng, model và cách dựng `content` đều đúng tuyệt đối"* nói quá mức bằng chứng cho phép.
Diễn đạt đúng là: phép đo parity trên 30 bản ghi untouched là **bằng chứng hỗ trợ mạnh giả thuyết
batch-padding dependence** — nhúng lại như hiện tại cho trung vị cosine 0,68, còn khi quét độ dài pad
thì trung vị đạt 1,000000 (nhỏ nhất 0,979563). Đây không phải chứng minh cho toàn bộ kho. Quyết định
nhúng lại hai nhánh bằng batch = 1 không đổi.

## 2. Sửa ánh xạ cổng RRF (lớp phân tích)

Cổng RRF được sửa từ `graph_top30` sang `final_chunks`, vì `graph_ids` được chụp **trước** bước
fusion (`minirag/operate.py:1489`) nên `graph_top30` không đổi theo mode và không thể đánh giá RRF.

- Thời điểm: áp vào `eval_offline.py` lúc 22:52:08, **sau** khi full run khởi chạy lúc 22:43:00 và
  **trước** khi raw log full-run đầu tiên tồn tại (`control_graph.jsonl` tạo lúc 23:25:45).
- Mức độ kết quả đã xem lúc sửa: đã thấy số liệu của smoke test 3 câu (mode graph, n = 3); chưa có
  kết quả full-run nào tồn tại trên đĩa.
- Ngưỡng không đổi: graph-only net >= +9 và p < 0,01; RRF net >= 0.
- Đây là sửa lỗi ánh xạ metric **sau khi đã khởi chạy đo**, không phải đăng ký trước.

## 3. Lớp báo cáo fail-closed

Báo cáo chỉ kết luận cổng khi mọi check hợp lệ bắt buộc PASS. Check thiếu bằng chứng là UNVERIFIED và
chặn cổng. Thay đổi này không đổi danh sách gộp, cài đặt truy hồi, mẫu, định nghĩa metric hay ngưỡng.
