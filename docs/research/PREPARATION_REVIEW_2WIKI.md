# Review chuẩn bị 2Wiki — 26/10/2026

Trạng thái: chuẩn bị offline đã kiểm chứng; chưa chọn corpus hoặc khóa split; chưa index hoặc gọi LLM/judge.
Nhánh: `research/2wiki-qwen`, nền `9c59062a9cfaaab47b4e8b303829ce0d00624e91`.
Protocol tham chiếu: nhánh MultiHop tại `790e0171a9e4e7c542aabc41993f48a37bff41ca`; bản review là đề xuất, không phải phê duyệt thay nhóm.

## Kết quả dữ liệu

- Archive khớp SHA-256 theo README; dev 12.576 câu có nhãn, 54.957 đoạn ứng viên.
- 463 câu có title lặp, tổng 523 lượt lặp cùng nội dung: gộp tài liệu theo title, giữ toàn bộ câu hỏi.
- 70/30.687 supporting fact có chỉ số câu ngoài đoạn, nằm ở 70 câu: giữ nguyên nhãn nguồn, `fact=null`, ghi lý do. Đánh giá cấp đoạn còn dùng được title; đánh giá fact/chunk phải báo tỷ lệ ánh xạ, không loại câu âm thầm hoặc đoán vị trí.
- `id_aliases.json` là JSONL; mọi answer_id có bản ghi alias tương ứng.
- `processed/docs.jsonl` là kho ứng viên toàn dev, KHÔNG phải corpus được duyệt để index.
- Checksum từng đầu ra có trong `processed/manifest.json`; `prepare_2wiki.py --check` tái tính và đối chiếu byte.

## Quy mô và split ứng viên

Lấy pool bằng sắp xếp `_id`, shuffle Python seed 13, lấy prefix. Mỗi corpus ứng viên gồm hợp cả 10 context của mọi câu pool (gold và distractor). Chunk theo chính hàm hiện có: 1.200/100, tiktoken `gpt-4o-mini`.

| N | Đoạn | Chunk | Token tài liệu | Call index tĩnh | Dev/test ứng viên |
|---:|---:|---:|---:|---:|---:|
| 200 | 1.535 | 1.535 | 151.949 | 3.070 | 160/40 |
| 500 | 3.446 | 3.446 | 351.569 | 6.892 | 400/100 |
| 1.000 | 6.387 | 6.388 | 668.649 | 12.776 | 800/200 |
| 2.000 | 11.657 | 11.661 | 1.248.590 | 23.322 | 1.599/401 |

Call tĩnh = 2 × chunk duy nhất, chưa tính retry/cache và không quy đổi thành chi phí GPU. Tỷ lệ test 20% là ứng viên, chưa khóa. Pool 500 là phương án để review ngân sách, chưa phải quyết định đã duyệt.

## Kiểm rò rỉ và gần trùng

- Nhóm thành phần liên thông theo title gold; cả bốn phương án có 0 title gold chung giữa hai phía.
- Chuẩn hóa text: Unicode NFKC, casefold, thay ký tự không phải chữ/số bằng khoảng trắng, gộp khoảng trắng.
- Jaccard tập character 5-gram >= 0,85; join chính xác có prefix/length filter, đã đối chiếu exhaustive trên fixture. Đây là kiểm cấu trúc dữ liệu, không dùng answer/judge để chọn ngưỡng.
- Kiểm câu hỏi và thân đoạn gold bỏ title: 0 cặp vượt ngưỡng trên cả bốn pool. Không phát sinh nhóm mới; split ứng viên giữ nguyên.
- Không phải bộ phát hiện paraphrase ngữ nghĩa. Chưa nhóm gần trùng mọi thân đoạn distractor. Các phía cùng corpus nên vẫn chung title context: 50/160/281/437 theo N=200/500/1.000/2.000. Không tuyên bố không rò rỉ tuyệt đối.
- Báo cáo chỉ có thống kê và hash; không xuất ID/nội dung câu test, không mở test để phân tích lỗi.

## Phần chung đã nhận và sai khác cần review

- Có runner/judge trên nhánh MultiHop; chưa tích hợp toàn bộ nhánh vào 2Wiki.
- Giữ Gemini Flash theo yêu cầu luồng 2Wiki. MultiHop đổi sang Flash-Lite là sai khác có chủ đích; chưa phê duyệt thay đổi judge 2Wiki.
- ID Flash phải kiểm qua chính project, lưu raw response/model; chưa có lượt gọi nào từ luồng này.
- Rubric nguyên văn hiện chưa nhận aliases 2Wiki; cần thống nhất schema/version và parse_failed trước run đầu.
- Index đề xuất output 4096, QA 1024. Index 2Wiki phải đo lại bằng pilot; không áp số MultiHop như số đo 2Wiki.
- Model revision và sampling trong serving config có phần suy luận; phải ghi provenance và xác minh endpoint. Python client 3.13.5 đã chốt; image Modal mẫu dùng 3.12, cần làm rõ quy định Python có áp cho server trước deployment.
- `metrics.py` và ba ablation B2 vẫn cần triển khai/review. Chưa sửa `minirag/` hoặc mặc định retrieval.
- V-01/MR_FULL và cách paper dựng corpus 2Wiki vẫn chưa đủ bằng chứng; mọi số 2Wiki phải ghi chuyển đổi benchmark do nhóm đề xuất.

## Cổng trước pilot 200 đoạn

1. Nhóm review schema, rubric, runner/logger và fixture; không coi bảy kiểm thử dữ liệu là toàn bộ S-08/S-09.
2. Nhóm chọn N/tỷ lệ split, ngưỡng chênh phân bố loại câu chấp nhận được và vị trí giữ bản split đầy đủ.
3. Chốt backup, ngân sách còn lại và trần riêng cho pilot. Ghi endpoint riêng 2Wiki và runtime đã xác minh.
4. Parameterize index/QA cho 2Wiki; không dùng mặc định đường dẫn MultiHop.
5. Tạo corpus/split manifest riêng, pilot chọn đoạn có seed. Không dùng toàn bộ 54.957 đoạn để index.

## Tái lập offline

```bat
set PYTHONUTF8=1
.venv\Scripts\python.exe reproduce\research\prepare_2wiki.py --raw dataset\2WikiMultiHopQA\raw\extracted --out dataset\2WikiMultiHopQA\processed --check
.venv\Scripts\python.exe -m pytest tests\research\test_2wiki_preparation.py -q
.venv\Scripts\python.exe reproduce\research\audit_2wiki_duplicates.py --repo . --out runs\2wiki\audit-repeat\near_duplicates.json
```

Audit yêu cầu báo cáo pool đã có ở `docs/research/env/2wiki_pool_measurements_seed13.json`; từ chối ghi đè output. Khi tái chạy so phần results, source hash và script hash; đường dẫn output không ảnh hưởng kết quả. Không cần API key/GPU.
