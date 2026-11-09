# QA C0/C1/C3 — còn thiếu một phần lượt judge thứ ba

Worker dừng do daily quota của các key miễn phí. Đã có 600 đáp án và 1.492/1.800 phán quyết. Lượt 1/2 đủ 200 câu × ba bản; lượt 3 có 292/600 phán quyết, tương ứng 97 câu đủ cả ba bản và một phán quyết lẻ. Còn thiếu 308 phán quyết. Không gọi API trả phí hoặc đổi model để tiếp tục.

## Hai lượt đủ 200 câu — chỉ là báo cáo tạm

Bảng trung bình ± sd giữa HAI lượt judge hoàn tất; không trộn 97 câu của lượt 3 vào mẫu 200. Đây không phải kết quả đủ ba lượt judge theo protocol.

| Bản | acc | err | neither |
|---|---:|---:|---:|
| C0 | 57.75 ± 1.06 | 21.75 ± 0.35 | 20.50 ± 0.71 |
| C1 | 63.25 ± 0.35 | 24.00 ± 1.41 | 12.75 ± 1.06 |
| C3 | 66.00 ± 2.12 | 21.00 ± 1.41 | 13.00 ± 0.71 |

## Kiểm định ghép cặp từng lượt hoàn tất

Các p dưới đây là descriptive/interim. Kiểm định chính trên majority BA judge của đủ 200 câu chưa tính được.

| Lượt | C3 so với | Lên / xuống | p chính xác | p Holm, hai đối chứng trong lượt |
|---|---|---:|---:|---:|
| 1 | C0 | 41 / 20 | 0.00985345 | 0.0197069 |
| 1 | C1 | 10 / 2 | 0.0385742 | 0.0385742 |
| 2 | C0 | 38 / 26 | 0.168643 | 0.337286 |
| 2 | C1 | 9 / 6 | 0.607239 | 0.607239 |

Lợi thế kiểm định ở lượt 1 không lặp lại ở lượt 2. Không kết luận cải tiến cấu hình hoặc chọn lượt thuận lợi để báo. Cần hoàn thành judge 3, sau đó xác nhận bằng lặp sinh/đánh giá độc lập nếu muốn công bố.

Điều kiện: một lượt sinh Gemini free-tier; graph/parser Qwen cố định, context từ study offline. Không chạy lại retrieval/evidence. Đây là C3 relation-lift, không phải source-witness/W(p), và không phải benchmark SLM cuối.

## Tiếp tục

Chỉ khởi động một worker khi có quota khả dụng. Kiểm tra lock nếu có worker khác. Giữ nguyên nguồn trong manifest.

```sh
.venv/bin/python reproduce/path/run_p0_qa.py --output logs/p0_qa/20261109_dev200
```

Sau khi đủ 1.800 phán quyết:

```sh
.venv/bin/python reproduce/path/verify_p0_qa.py logs/p0_qa/20261109_dev200
```

Nguồn số: partial_accuracy_report.json, status.json, answers.jsonl, judgments.jsonl. Verifier đã kiểm tra checkpoint hiện có; toàn bộ hash nguồn/index được đối chiếu lại và khớp. API failures không được tính thành nhãn error/neither.
