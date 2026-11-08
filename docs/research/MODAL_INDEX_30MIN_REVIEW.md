# Review đợt index 30 phút — 30/10/2026

## Lượt resume batch32/async16 (kết thúc 22:57 giờ Việt Nam)

- Từ288 lên768 đoạn checkpoint, tăng480 đoạn (15 lô32), tổng6,59% corpus.
- Events ghi1785,5 giây từ resume đến time_limit; timer1800 giây còn gồm setup.
  Thông lượng ~16,13 đoạn/phút, còn10.889 đoạn, ngoại suy ~11,25 giờ chưa bảo đảm.
- Trace1.033 attempts: 1.023 response thành công, 9 APITimeoutError, 1 hủy khi
  hết giờ. Cả9 timeout đều có response thành công ở retry cùng request_id.
  Không tự diễn giải timeout mạng thành lỗi extraction hoặc bỏ câu.
- Finish reasons: 1.021 stop, 2 length. Tổng completion693.320 token; ghi nhận
  truncation, không đổi cap/prompt trong index đang resume.
- Không gọi thêm cloud trong review. Chờ số Billing tích lũy mới để kiểm trần
  tổng25 USD, giữ khoảng8 USD cho QA/dự phòng trước khi cấp lượt tiếp.

Nguồn local: `indexes/2wiki-modal-n2000-s13-dev20test80/`.
Không gọi cloud, không sửa index trong bước review.

| Mục | Kết quả |
|---|---:|
| Trạng thái | partial / time_limit |
| Tài liệu đã checkpoint | 288 / 11.657 (2,47%) |
| Lô đã checkpoint | 18 × 16 đoạn |
| HTTP attempts được trace | 608 |
| Response thành công | 607, đều Qwen/Qwen2.5-3B-Instruct |
| Request hủy | 1 CancelledError khi hết giờ |
| Finish reasons | 606 stop / 1 length |
| Prompt / completion tokens | 1.551.962 / 428.029 |
| Tốc độ checkpoint sơ bộ | 9,6 đoạn/phút |
| Đoạn còn lại | 11.369 |
| Giờ còn lại nếu giữ cùng tốc độ | 19,74 |

Ước lượng tuyến tính từ nửa giờ đầu, không bảo đảm. Cold start, độ dài đoạn,
output sampling, embedding/ghi graph và kích thước index tăng dần có thể làm
tốc độ khác. Không suy ra tiền từ tổng latency request: các request chồng lấp.
Chưa có số billing thực tế để ước lượng chi phí.

Một gleaning response chạm 4.096 token, thuộc chunk đã checkpoint
`chunk-795e009f9bfac18bb7a83e3f84257dd1`. Đầu ra dạng danh sách giải thích và
bị cắt giữa một quan hệ, không phải response hoàn chỉnh đúng delimiter. Chưa
đánh giá ảnh hưởng chất lượng. Không tự đổi prompt/cap hoặc tái tạo chunk đã lưu
trong cùng index; phải giữ điều kiện so sánh và ghi nhận giới hạn extraction.

Đợt dừng đúng timer, không phải crash. Chỉ 288 đoạn thuộc các lô hoàn tất được
cam kết resume; lô đang chạy khi bị hủy có thể phải làm lại. Không dùng index
partial để chạy/chấm QA rồi gọi đó là benchmark đầy đủ 2.000 câu.

**Bước tiếp:** chưa tự resume. Chờ ngân sách tổng và billing nửa giờ từ người
dùng, đối chiếu tốc độ/chi phí rồi quyết định tiếp tục hay đo thêm thông lượng
có giới hạn. Giữ nguyên corpus 2.000 câu, index, checkpoint, source và model.
