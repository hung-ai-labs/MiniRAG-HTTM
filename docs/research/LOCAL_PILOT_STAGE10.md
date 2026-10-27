# Pilot 2Wiki local — mốc đầu 10/200 đoạn

Đã chạy thật 26/10/2026 trên nhánh research/2wiki-qwen. Đây là lô kỹ thuật đầu của pilot, chưa phải pilot 200 hoàn tất hoặc benchmark QA.

## Kết quả

| Chỉ số | Giá trị |
|---|---:|
| Tài liệu/chunk đã index | 10 / 10 |
| Pilot dự kiến | 200 đoạn thuộc corpus của 2.000 câu |
| Đồ thị | 77 node / 32 cạnh |
| Request | 20/20 thành công = 10 extract + 10 glean |
| Model | Qwen2.5-3B-Instruct Q4_K_M trên Ollama local |
| Token sinh | 12.921 |
| Chạm trần 4096 | 1/20 request (5%); thuộc extraction |
| Thời gian request | 182,161 giây |
| Tổng thời gian 10 doc (không tính import ban đầu) | 184,186 giây |
| Kiểm toàn vẹn | 7/7 đạt, xác minh lại bằng --verify |

Tất cả response do qwen2.5:3b local trả về; mọi request gắn doc_id/chunk_id/phase, messages/options/raw response, latency, token và finish reason. Chưa gọi Gemini/judge hoặc QA 2Wiki. Sau chạy đã unload, /api/ps rỗng.

## Phát hiện cần review trước mở rộng

- Một extraction sinh đủ 4.096 token và chứa nhiều đoạn lặp: chia theo delimiter ## được 409 segment nhưng chỉ 48 segment duy nhất sau strip. Có marker COMPLETE trong response. Đây là chẩn đoán chuỗi, không phải số entity/relationship chính thức.
- Tăng trần output chưa chắc khắc phục vòng lặp; không tự tăng cap, thêm stop marker, đổi prompt hoặc làm sạch record vì sẽ thay điều kiện index. Giữ raw response để nhóm review.
- Một số đoạn không có relationship; chưa quy kết do SLM yếu hoặc do bug nếu chưa đọc nội dung và output tương ứng. Không sửa gold hoặc lọc tài liệu vì hiện tượng này.

## Dự toán từ lô nhỏ

- Trung bình 18,419 giây/doc; median và phân bố ở env/2wiki_local_pilot_stage10.json.
- Ngoại suy pilot 200: khoảng 61,4 phút tổng; còn khoảng 58,3 phút nếu tốc độ không đổi.
- Ngoại suy 11.657 đoạn corpus: khoảng 59,6 giờ local. Không phải cam kết thời gian; mẫu mới 10 doc, chịu ảnh hưởng độ dài, vòng lặp, đồ thị tăng, nhiệt máy và cold start.
- Chưa có kết luận accuracy, lợi ích B2 hoặc chi phí GPU cloud từ số này. Không bắt đầu index toàn corpus.

## Artifact và checkpoint

- Run: runs/2wiki/local/pilot200/20261026_01/.
- Index mới: indexes/2wiki-local-q4km-pilot200-n2000-s13/; không ghi index LiHua.
- index_manifest.json: config/source/docs/model identity, danh sách doc đã commit, hash từng store, 7 kiểm liên kết và metrics.
- requests.jsonl, events.jsonl, index_progress.jsonl, runtime.json: flush từng record.
- Checkpoint bất biến: checkpoints/docs-0010/ gồm bản copy stores và checkpoint_manifest.json, đã đối chiếu checksum.
- Public report chỉ thống kê/hashes: docs/research/env/2wiki_local_pilot_stage10.json.

Runner commit sau khi ainsert lưu xong mọi store. Resume yêu cầu đúng docs/model/config/source và store hashes; bỏ qua doc đã commit. Nếu phát hiện torn write thì từ chối sửa tại chỗ, giữ index và snapshot để phục hồi sang thư mục mới. Chưa có lệnh recovery tự động; không coi test phát hiện torn write là đã tự phục hồi mọi crash.

## Tái lập/tiếp tục

38 test offline đã đạt trước chạy model, gồm kiểm đường dẫn, identity đổi, torn checkpoint, thiếu vector và metric stage. Không phải fixture chung S-08/S-09 đã hoàn tất.

```bat
set PYTHONUTF8=1
set PYTHONHASHSEED=13
.venv\Scripts\python.exe reproduce\research\local_index_pilot.py --docs dataset\2WikiMultiHopQA\processed\pools\n2000_seed13\pilot_docs.jsonl --index indexes\2wiki-local-q4km-pilot200-n2000-s13 --run-dir runs\2wiki\local\pilot200\20261026_01 --verify
.venv\Scripts\python.exe reproduce\research\local_index_pilot.py --docs dataset\2WikiMultiHopQA\processed\pools\n2000_seed13\pilot_docs.jsonl --index indexes\2wiki-local-q4km-pilot200-n2000-s13 --run-dir runs\2wiki\local\pilot200\20261026_01 --max-new-docs 10 --resume
```

Lệnh thứ hai xử lý tối đa 10 doc mới; không gửi lại 10 doc đã commit. Lưu báo cáo stage mới bằng tên mới sau mỗi mốc. Corpus/split QA và backup chung còn các cổng đã ghi trong PROJECT_STATE.md.
