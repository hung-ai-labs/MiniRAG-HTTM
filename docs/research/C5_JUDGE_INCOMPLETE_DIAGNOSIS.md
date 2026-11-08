# C5 judge: một câu lỗi định dạng lặp — 02/11/2026

## Vì sao resume nhiều lần vẫn false

Snapshot sau lần người dùng báo lỗi: **1.200/1.203 phiếu hợp lệ**. Ba phiếu chưa
hợp lệ đều thuộc query `8cc029e708c311ebbd8dac1f6bf848b6`, cả ba lượt judge.
Latest statuses: một parse_failed, hai judge_failed. Những lần trước của cả ba
phiếu đều có parse_failed lặp; gần đây phát sinh thêm RateLimitError.

Gemini nhiều lần trả giải thích dài và một nhãn ở cuối, thay vì đúng một nhãn.
Có phản hồi stop nhưng vẫn sai định dạng, có phản hồi length bị cắt. Đây không
chỉ là quota: chờ quota rồi resume không bảo đảm giải quyết lỗi định dạng.
Qwen đã đủ401 đáp án; không cần sinh lại hoặc đổi cap cho riêng câu này.

## Quy tắc dự án và cách xử lý hiện tại

PROTOCOL_MHR_REVIEW.md, mục hợp đồng nhãn (dòng40): chỉ đúng một trong
accurate/error/neither, bỏ qua hoa/thường và dấu bao quanh; còn lại hỏi lại ba
lần rồi parse_failed, không tự gán nhãn. Judge2Wiki đã giữ hợp đồng này trong
test_judge_2wiki.py và rubric v2.

Do đó **không** lấy chữ cuối của phần giải thích, gán nhãn bằng tay, sửa gold,
đổi model/prompt/rubric, hoặc đánh dấu complete=true. Giữ nguyên judge.jsonl,
requests.jsonl và manifest. Không đổi parser để ép hoàn tất sau khi đã xem kết quả.
Không khuyến nghị tiếp tục resume lặp vô hạn cho ca lỗi này.

Nếu nhóm sau này chọn một hợp đồng output khác, cần đăng ký/version rõ ràng và
áp dụng nhất quán cho các cấu hình so sánh. Không ghép điểm từ parser/rubric
khác nhau như cùng điều kiện. Trong giao thức hiện tại, chỉ phản hồi đúng định
dạng của Gemini mới hoàn tất được ba phiếu; chưa có cách đảm bảo bằng retry.

## Bản phân tích tạm, không thay run hoàn chỉnh

Đã dùng metrics.py hiện có để báo incomplete minh bạch và ghép **400 cặp đủ
phiếu ở cả C1/C5**, loại đúng một query incomplete khỏi phép so, không xóa nó
khỏi dữ liệu dev hoặc tạo một split mới. C5 còn một query khác có no_majority
(ba nhãn khác nhau), được giữ riêng và tính không-accurate đúng hợp đồng metrics.

Artifact snapshot:
`runs/2wiki/analysis/c1-c5-dev-s101-fl35-v2-partial-1200/`
gồm unresolved.json, C1_metrics, C5_metrics, hai adapter manifest, comparison.json.
Unresolved lưu hash judge.jsonl tại thời điểm chẩn đoán; snapshot không tự cập
nhật nếu người dùng tiếp tục resume.

- C1/C5 paired n_expected401, n_paired_complete400, n_excluded_incomplete1.
- Accuracy theo majority trên400 cặp:42 lên/40 xuống, net+2, McNemar p=0,912157.
  Query bootstrap CI95[-3,76;+4,75] điểm. Đây là kết quả tạm một seed, không kết
  luận cải tiến hay tương đương.
- Error chuyển vào66/rời42, net+24, p=0,026424. Đây là chỉ số phụ trong phân
  tích tạm sau nhiều phép so; không dùng riêng con số này để tuyên bố Entities
  có tác dụng nhân quả hoặc chọn phương pháp. Cần run hoàn chỉnh/lặp và review.
- Giữ trong Limitations: một output QA C5 chạm1024 token, đã ghi từ trước judge.

Run C5 **vẫn incomplete**, chưa có summary401 cuối cùng. Không mở test1599 hay
coi toàn bộ các cổng nghiên cứu đã đạt. Không gọi thêm API/GPU trong chẩn đoán này.
