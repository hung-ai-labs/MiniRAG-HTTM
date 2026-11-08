# Review pilot Modal 20 đoạn — 30/10/2026

## Lượt so sánh batch16/async8

Đã chạy `indexes/2wiki-modal-pilot20-b16-c8`, cùng checksum tập tài liệu với
lượt cũ (`cde913e8355e444003bdc6d31bc1f4e430678ad61de0776c10466b1007df013c`).

| Mục | Batch4/async4 | Batch16/async8 |
|---|---:|---:|
| Wall index (giây) | 293,32 | 165,08 |
| Requests thành công / tổng | 40/40 | 40/40 |
| Output length | 0 | 0 |
| Completion tokens | 24.426 | 26.946 |
| Completion dài nhất | 2.111 | 2.631 |
| Node / cạnh | 145 / 67 | 168 / 66 |
| Chunk không cite trong graph | 1 | 0 |

Lượt mới ngắn hơn 128,24 giây (~43,7%, tỷ số 1,78). Chưa phải benchmark cùng tải
có kiểm soát: khác cold-start state, sampling và số output token. Không suy ra
node nhiều hơn là chất lượng tốt hơn hoặc khẳng định giảm tiền cùng tỷ lệ.
Chọn batch16/async8 làm cấu hình ứng viên cho đợt tiếp theo có giới hạn thời gian.
Chưa chạy full index; cần người dùng chọn trần đợt chạy và theo dõi Billing.

Script modal_slm.py local đã bổ sung --revision đúng snapshot cache và --dtype
bfloat16; cần redeploy mới có hiệu lực. Hai pilot lịch sử dùng server chưa pin;
giữ nguyên artifact/manifest, không sửa lại để gán provenance mới cho pilot cũ.

Index: `indexes/2wiki-modal-pilot20-dev20test80`. Review chỉ đọc artifact local;
không gọi thêm Modal/Gemini. Đây là pilot index, chưa phải QA hay benchmark.

| Mục | Kết quả |
|---|---|
| Docs/chunks | 20/20 |
| Graph | 145 node, 67 cạnh |
| Kiểm toàn vẹn | Cả 6 mục đạt |
| HTTP attempts | 40: 20 extract, 20 glean, tất cả thành công |
| Model response | Qwen/Qwen2.5-3B-Instruct ở cả 40 request |
| Finish reason | 40 stop, 0 length |
| Completion dài nhất | 2.111 token, dưới cap 4.096 |
| Tổng prompt/completion tokens | 102.432 / 24.426 |
| Wall index (start → finish) | 293,32 giây, gần 4 phút 53 giây |
| Thời gian 5 lô | 140,27 / 42,15 / 60,29 / 28,67 / 21,82 giây |
| Chunk không được graph cite | 1 |

Chunk không được cite là đoạn cực ngắn `Where Did We Go Wrong may refer to:`.
Extract chỉ trả content_keywords; glean yêu cầu cung cấp thêm văn bản. Đây không
phải thất lạc chunk: chunk/vector/extracted checkpoint vẫn có. Ghi nhận là hành
vi extraction với đoạn không đủ nội dung, không gọi là crash hoặc tự xóa đoạn.

Chưa kiểm tay toàn bộ thực thể/quan hệ, chưa có chứng cứ chất lượng retrieval.
Số node/cạnh không tự chứng minh graph đúng. Toàn corpus của pool 2.000 câu vẫn
là 11.657 đoạn, 11.661 chunk; chưa được index trong lượt pilot này.

## Quyết định bước tiếp

Pilot đạt kiểm toàn vẹn/cap, nhưng chưa đủ để chốt thời gian và chi phí toàn
corpus. Đo throughput trên cùng 20 đoạn với một index mới, thử batch16/async8
trước full indexing. Đây là cấu hình thử hiệu năng, không phải cải tiến khoa học
hoặc cam kết nhanh gấp đôi. Không ghi đè/resume pilot đã hoàn tất với điều kiện
khác. Giữ nguyên seed chọn tài liệu, cap, model và corpus. Khác concurrency có thể
làm đầu ra sampling/graph khác; so cả lỗi/truncation và counts, không chỉ thời gian.

Tổng latency request có chồng lấp và có thể gồm cold start; không cộng latency
để tính tiền GPU. Lô đầu chậm hơn có thể gồm khởi động; chưa đủ bằng chứng quy
toàn bộ chênh lệch cho cold start. Không áp dự toán 1–2 USD của LiHua cho 2Wiki.
Chưa có billing Modal thực tế để báo chi phí. Trước full benchmark còn cần pin
revision, xác minh serving/sampling, backup và chốt ngân sách.

Lệnh thử tiếp theo (có GPU tính phí, khoảng 40 call trước retry):

```powershell
python reproduce/research/index_run.py --dataset-id 2wiki --docs dataset/2WikiMultiHopQA/processed/pools/n2000_seed13/docs.jsonl --subset pilot --pilot-size 20 --workingdir indexes/2wiki-modal-pilot20-b16-c8 --max-output-tokens 4096 --serving-config configs/research/2wiki/serving_modal.json --llm-max-async 8 --batch-docs 16
```

Nguồn: index_manifest.json, events.jsonl, index_requests.jsonl và graph/chunk
stores trong index pilot. Tất cả bước review chạy offline.
