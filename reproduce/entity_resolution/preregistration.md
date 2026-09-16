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
