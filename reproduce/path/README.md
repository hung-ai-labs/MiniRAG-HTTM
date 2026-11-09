# C0 / C1 / C2 / C3 hiện hành

Phiên bản cấu hình: **20261109-p0-relation-lift**. Từ phiên bản này, tên C1/C2/C3
trong runner hiện hành chỉ có nghĩa trong bảng dưới. Không dùng bảng tên cũ
của các thí nghiệm lịch sử để chạy benchmark mới.

| Bản hiện hành | Chọn ứng viên | Điểm dùng tại ranking chung | Scorer | Câu đủ evidence /180 |
|---|---|---|---|---:|
| C0 | MiniRAG baseline của nhóm | Gốc | P0 | 75 |
| C1 | Nguồn đồ thị + query affinity | Seed score/boost gốc; không nhân PathChunkScores | P0 | 102 |
| C2 | Chính xác danh sách và thứ tự ứng viên C1 | PathChunkScores hiệu chuẩn trung bình 1 trong seed | P0 | 102 |
| C3 — thử nghiệm mới | Chính xác danh sách và thứ tự ứng viên C1 | Điểm P0 theo quan hệ và hiệu chỉnh nguồn lặp | P0 relation-lift | 108 |

C1 và C2 giữ nguyên. **P2 weighted cũ đã bỏ khỏi phương án chính**: cả bốn
profile hiện hành đều dùng P0 làm nền. C3 nay là bản thiết kế mới, không phải
đổi tên P2. C3 của phiên bản `20261109-calibrated` trước đây dùng P2, đạt 101
câu; số đó chỉ còn là kết quả lịch sử và không được gán cho C3 hiện tại.
Nguồn dữ liệu C1/C2 vẫn là `C1_affinity`/`P0_fixed_mean`; C3 mới có study riêng
ở `logs/p0_paths/20261109_dev200`. Không sửa tên dữ liệu lịch sử.

Các số trên là retrieval offline trên dev, chưa phải accuracy. C0 là baseline
MiniRAG trong repo, cùng bản vá answer-type, index và Sources 4.000 token;
không phải tái chạy upstream nguyên xi.

## Query affinity là phần code bổ sung

Đây là đoạn code đã bổ sung vào implementation trong repo. **Ý tưởng dùng
độ giống câu hỏi–chunk không phải ý tưởng mới so với paper**: MiniRAG v1,
§2.2.2 đã có bước tính similarity với nội dung chunk và mô tả cạnh liên quan
([paper](https://arxiv.org/html/2501.06713v1)). Cách code hiện tại dùng vector
chunk sẵn có, không phải bản sao nguyên xi bước nối chunk+mô tả của paper.
Không được gọi riêng query affinity là novelty. Nó dùng **chính embedding
all-MiniLM-L6-v2 đang có**, không đổi model:

```text
affinity(query, chunk) = max(0, cosine(vector_query, vector_chunk))
điểm chọn chunk = điểm chiếu từ path × affinity(query, chunk)
```

Mục đích: trong các đoạn văn do đồ thị đưa ra, ưu tiên đoạn hợp nội dung câu
hỏi thay vì đoạn chỉ nhắc nhiều lần tên một thực thể. Ví dụ, câu hỏi về ngày
trả tiền thuê cần đoạn nói về việc trả tiền, không chỉ đoạn có tên Li Hua.
Độ giống ngữ nghĩa là tín hiệu hỗ trợ, không bảo đảm chunk đó trả lời đúng.

Thứ tự tính: entity/type search → mọi path gốc → node/edge score và edge vote
→ nguồn node/cạnh → affinity → ba chunk/seed → scorednode2chunk → dense search
→ kwd2chunk → Sources 4.000 token. C2/C3 khóa ứng viên theo C1, chỉ đổi cách
dùng điểm ở ranking chung. C3 dùng P0, bổ sung độ liên quan query–relation cho
mọi hop và so điểm nguồn với nền cấu trúc đồng nhất để giảm phiếu do lặp path.
Các hàm P2 cũ chỉ còn phục vụ tái lập lịch sử, không profile chính nào chọn nó.

**Không dùng RRF hoặc BM25 trong bốn profile này.** Dense search và dense
boost của pipeline vẫn chạy. Query affinity cũng là tín hiệu vector, nhưng
không phải reciprocal rank fusion.

## Chạy cấu hình hiện hành

Xem các biến retrieval mà một profile sẽ đặt, không gọi API:

```sh
.venv/bin/python reproduce/path/c_profiles.py C3
```

Kiểm tra offline đủ bốn profile từ đầu vào đã đóng băng, kèm hai câu chạy
qua pipeline thật. Dùng thư mục output mới:

```sh
TIKTOKEN_CACHE_DIR=/private/tmp/minirag-score-flow-tiktoken .venv/bin/python reproduce/path/benchmark_c.py --profiles C0 C1 C2 C3 --live-limit 2 --output logs/c_benchmark/NEW_RUN
```

Thí nghiệm C3 mới và các ablation chạy bằng `eval_p0_paths.py`, sau đó xác
minh bằng `replay_p0_paths.py`. Runner kiểm tra không được dùng kết quả P2
cũ để báo cho C3 mới. Thiết kế trước đo: `P0_RELATION_LIFT_PROTOCOL.md`.

Áp dụng profile cho một lệnh QA mà nhóm đã cấu hình backend/model:

```sh
.venv/bin/python reproduce/path/c_profiles.py C3 -- .venv/bin/python reproduce/Step_1_QA.py <các tham số benchmark của nhóm>
```

Wrapper chỉ đặt biến retrieval, không tự gọi API, không thay backend/model,
key hoặc rate limiter. Benchmark phải giữ cùng index, parser, model, top_k=60,
Sources 4.000 token và đủ các lượt sinh/chấm theo giao thức đã chốt.

## Dữ liệu và kết quả lịch sử

Nguồn cấu hình hiện hành duy nhất là `c_profiles.py`. `c_ablation.py` và
`C_ABLATION.md` chỉ giữ định nghĩa C0–C3 của lần sửa bug trước đây; CLI cũ đã
dừng để tránh chạy nhầm tên C3. P2 weighted còn trong thư viện để tái lập lịch sử,
không được profile hiện hành nào chọn.

Các runner offline cần index Qwen, parser cache và các artifacts đóng băng
`logs/path_calibration/20261109_dev200` và `logs/p0_paths/20261109_dev200`.
Những tài sản lớn này không nằm trong commit; một checkout mới phải nhận đúng
bộ artifacts có hash tương ứng từ nhóm trước khi chạy replay. Chạy QA qua
`c_profiles.py` không phụ thuộc hai bộ replay này. Bảng kết quả và giới hạn:
`P0_RELATION_LIFT_FINDINGS.md`; mô tả thay đổi: `ALGORITHM_CHANGES.md`.

## Audit provenance và QA bổ sung

- `NEXT_GRAPH_IMPROVEMENT_RESEARCH_20261109.md`: findings và hướng nghiên cứu có điều kiện.
- `SOURCE_PROVENANCE_IMPLEMENTATION.md`: audit và capture nguồn trước merge cho lần index mới.
- `P0_QA_PROTOCOL.md`, `run_p0_qa.py`, `verify_p0_qa.py`: generation/judge và xác minh checkpoint.
- `results/20261109/qa/RESULTS_PARTIAL.md`: QA chưa hoàn tất; 600 đáp án,
  1.492/1.800 phán quyết, thiếu 308 vì hết quota ngày. Không phải ba lượt judge đầy đủ.
- `results/20261109/source_provenance/`: inventory nguồn và hash study.
- `results/20261109/funnel/`: phễu C1 đã replay khớp 200/200.

Các report là artifact lịch sử từ workspace thí nghiệm, không phải lượt đo mới
trên checkout phát hành. Full answers/judgments/context, index và parser cache
không được đính kèm. Để resume cần lấy đúng checkpoint và tài sản có hash tương
ứng từ nhóm; không tạo checkpoint mới rồi gộp nhãn với study cũ. Source hashes
trong manifest của study kiểm soát resume; một checkout khác có thể bị từ chối
nếu các nguồn snapshot không trùng, dù mục đích thuật toán tương đương.

`source_witnesses.py` chỉ ghi provenance khi được bật trong driver index riêng;
không sửa C0/C1/C3 và chưa có scorer W(p) hoặc mức tăng QA của witness.
