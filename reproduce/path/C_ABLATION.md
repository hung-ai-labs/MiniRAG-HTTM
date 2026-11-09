> Historical bug-fix profiles only. Current C0–C3: [README.md](README.md).

# Benchmark C0 / C1 / C2 / C3

| Arm | PATH2CHUNK_FIX | PATH_SCORE_FLOW | Scorer |
|---|---:|---:|---|
| C0 — pipeline cũ | 0 | 0 | P0 |
| C1 — sửa chọn Counter | 1 | 0 | P0 |
| C2 — truyền đầy đủ điểm | 1 | 1 | P0 |
| C3 — phương pháp P2 | 1 | 1 | P2 (`weighted`) |

C1 chọn `node_chunk_id` cộng dồn mọi path thay vì Counter path cuối. C2 giữ
`PathChunkScores` và dùng nó trong kwd2chunk. C3 chỉ đổi scorer P0 sang P2 trên
cùng luồng đã sửa. Giữ nguyên path, answer-type, phiếu cạnh, nguồn node/cạnh,
dense và boost upstream (kể cả hành vi x10 hiện tại). Không có P3/graph-flow,
chuẩn hóa path, thay projection, LEEF hay thay đổi prompt/model trong nhánh này.
C1 đã có công tắc trên dev; gói này thêm C2 và profile benchmark C0–C3 rõ ràng.

Mặc định thư viện vẫn giữ hành vi lịch sử. Không sửa baseline.yaml và không cần
index lại khi chỉ đổi các profile này. Đây là bản sửa luồng điểm và công thức P2
cần kiểm chứng; chưa có tuyên bố accuracy tăng hay đóng góp mới từ sửa bug.

## Kiểm thử và kiểm tra profile

```bash
python -m unittest discover -s tests -p 'test_*flow.py' -v
python -m unittest discover -s tests -p 'test_c_ablation.py' -v
python reproduce/path/c_ablation.py --arm C3 --fusion graph
```

## Offline LiHua dev

Cần cùng index, embedding local, tokenizer và cache parser đã có. Cache thiếu
phải lỗi, không gọi parser API. Chạy mỗi arm trên bản sao index tạm; kết quả và
records nằm riêng trong logs/c_ablation/<fusion>/<arm>. Lệnh không gọi generation
hay judge. Offline này dùng 180 câu dev có nhãn evidence và A1@4000.

```bash
python reproduce/path/eval_offline.py --arm C0 --fusion graph --workingdir ./LiHua-World-qwen-modal
python reproduce/path/eval_offline.py --arm C1 --fusion graph --workingdir ./LiHua-World-qwen-modal
python reproduce/path/eval_offline.py --arm C2 --fusion graph --workingdir ./LiHua-World-qwen-modal
python reproduce/path/eval_offline.py --arm C3 --fusion graph --workingdir ./LiHua-World-qwen-modal
```

Thêm `--limit 5` để smoke test. Nếu chạy RRF, đổi cả bốn lệnh sang `--fusion rrf`;
không so arm graph-only với arm RRF. Cache mặc định logs/path/cache/kw_cache.jsonl
chỉ dành cho tập câu hỏi tương ứng, không dùng nhầm cho dataset khác.

## QA với cùng cấu hình

Wrapper dưới đây đóng băng profile, Sources budget, parser cache và ghi manifest.
Thay C3/output/manifest tương ứng cho C0–C3, giữ mọi đối số còn lại giống nhau.
Backend/model lấy từ môi trường hiện tại; ví dụ này không tự khởi động GPU hay
chọn dịch vụ trả phí. Dùng model đã dùng để dựng index cho benchmark SLM cuối.

```bash
python reproduce/path/c_ablation.py --arm C3 --fusion graph \
  --kw-cache logs/path/cache/kw_cache.jsonl \
  --manifest logs/c_ablation/graph/C3/qa_manifest.json -- \
  python reproduce/Step_1_QA.py --workingdir ./LiHua-World-qwen-modal \
  --model YOUR_INDEX_MODEL --embedmodel local --mode mini --topk 60 \
  --maxtokentextunit 4000 --questions logs/devset.csv \
  --outputpath logs/c_ablation/graph/C3/answers.csv
```

Chỉ dùng lệnh QA khi backend/index/model và cache tương ứng đã sẵn sàng. Với
dataset/tập câu hỏi khác, đóng băng cache parser chung phù hợp trước. Wrapper
không đọc hoặc ghi API key vào manifest. Không gọi script shell cũ có thể ghi đè
các công tắc profile. Giữ output riêng cho mỗi arm và mỗi lượt sinh.

Để dùng Sources budget khác (ví dụ profile 6000), đặt `--sources-budget 6000` và
đối số query tương ứng, áp dụng cùng giá trị cho cả bốn arm. Không so trực tiếp
kết quả đó với dev A1@4000; budget/định dạng context phải ghi trong báo cáo.

Chấm bằng Step_2_evaluate.py theo giao thức dự án: đủ acc/err/neither, ba lượt
judge, ghép từng câu để báo McNemar. C1−C0 đo sửa Counter; C2−C1 đo truyền điểm;
**C3−C2 cô lập công thức P2**. Benchmark cuối cần lặp lượt sinh, không chỉ lặp judge.
