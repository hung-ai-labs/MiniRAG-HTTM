# Thay đổi thuật toán path scoring: P0 relation-lift

Phiên bản: `20261109-p0-relation-lift`. Đây là bản thử nghiệm mới của C3,
không phải C3/P2 weighted trong các lần chạy trước. Nhánh này nối tiếp bản
sửa luồng điểm `423707d`; định nghĩa chạy hiện hành nằm trong `c_profiles.py`.

## 1. Vấn đề và mục tiêu

Bản sửa Counter khôi phục tích lũy điểm từ mọi path. Truyền tiếp điểm đó vào
`kwd2chunk` khiến tín hiệu trước đây bị bỏ qua thực sự ảnh hưởng thứ hạng.
Tuy nhiên tổng điểm thô dễ ưu tiên nguồn xuất hiện nhiều lần trên các path
quanh hub; sửa đúng luồng code không bảo đảm tín hiệu đó hữu ích.

Giả thuyết đang thử: giữ tín hiệu P0, bổ sung hỗ trợ ngữ nghĩa của từng hop,
rồi so khối lượng nguồn nhận được với nền cấu trúc dùng cùng phép chiếu.
Nguồn được lặp chỉ do cấu trúc sẽ không tự nhận lợi thế tương ứng ở ranking.

## 2. Phần nào khác paper, phần nào chỉ là bổ sung implementation?

[MiniRAG v1, §2.2.2](https://arxiv.org/html/2501.06713v1) đã chấm path bằng
seed similarity, sự hiện diện của answer node và trọng số key relationship.
Paper cũng đã có query similarity với chunk kèm mô tả cạnh. Vì vậy:

- P0/P2 là tên nội bộ trong repo, không phải tên thuật toán của paper.
- Query–chunk affinity được thêm vào implementation hiện tại; ý tưởng này
  **không phải novelty so với paper**. Code dùng vector chunk có sẵn, không
  tái tạo nguyên xi cách nối nội dung chunk với mô tả cạnh của paper.
- Thay đổi thiết kế mới đang kiểm chứng là độ liên quan liên tục qua mọi hop
  và tỷ số bằng chứng/nền `F/B`. Chưa xác lập novelty so với toàn bộ literature.

## 3. Công thức và thứ tự xử lý mới

Với seed `s`, giữ mọi path gốc `p`. P0 trong implementation đang dùng:

```text
q0(p) = answer_type_count(p) + original_edge_vote_count(p) + 1
r(e)  = max(0, cosine(query_vector, existing_relation_vector(e)))
R(p)  = geometric_mean(r(e) trên mọi cạnh kề nhau của p)
q(p)  = q0(p) × R(p)
```

`q0` là công thức của code P0, không phải bản chép nguyên phương trình (3)
của paper. Seed similarity tiếp tục tham gia ở bước gom điểm chung.

Đọc cosine cho các cạnh vật lý thuộc path gốc bằng `score_pairs`; không
thay semantic edge search hoặc danh sách edge vote. Nếu mọi `q` của một seed
đều bằng 0, dùng lại `q0` cho seed đó và ghi số fallback. Node cô lập giữ
nguồn node gốc. Path có trọng số 0 vẫn nằm trong tập path được xử lý.

Chiếu ba phân bố trên **cùng tập path và nguồn node/cạnh**:

| Phân bố | Trọng số path trước chuẩn hóa | Vai trò |
|---|---|---|
| Prior | `q0(p)` | Chọn đúng ứng viên của C1 |
| Background `B` | `1` | Đo khối lượng nguồn do cấu trúc |
| Query evidence `F` | `q(p)` | Đo hỗ trợ từ P0 và ngữ nghĩa quan hệ |

Mỗi phân bố chuẩn hóa trọng số path trong từng seed. Với mỗi path, ngân sách
được chia đều cho các kênh node/cạnh có nguồn hợp lệ; trong mỗi kênh chia qua
các source occurrence. Kênh cạnh dùng toàn bộ nguồn của các cạnh được vote.
Giữ heuristic đối chiếu description/source của node từ C1. Đây là thay đổi
phép chiếu nguồn so với lỗi cũ chỉ lấy nguồn cạnh đầu và có thể mất nguồn
node do cache; không khẳng định sửa bug là đóng góp khoa học.

Tính `a(c) = max(0, cosine(query, chunk))` bằng vector chunk sẵn có.
Chọn ba chunk/seed theo `Prior(c) × a(c)` như C1. **Khóa cả ID lẫn thứ tự**
này cho C2/C3 và mọi ablation. Trên những ID đã chọn, C3 tính:

```text
PathChunkScores_s(c) = a(c) × F_s(c) / B_s(c)
```

`B > 0` trên các chunk được chọn; không thêm smoothing hoặc hệ số dò sau đo.
Không chuẩn hóa local-mean lần nữa ở C3. `kwd2chunk` nhân điểm mới với seed
score và boost hiện có; giữ nguyên cả phạm vi dense boost x10 cũ để cô lập
biến. `edge_vote_path(indexed=True)` chỉ tăng tốc tra cứu, giữ thứ tự,
duplicate và hướng cạnh như bản cũ.

## 4. Định nghĩa ablation hiện hành

| Bản | Chọn ứng viên | Điểm tại `kwd2chunk` |
|---|---|---|
| C0 | Baseline nhóm | Gốc, không truyền PathChunkScores |
| C1 | Prior × affinity | Seed score/boost gốc |
| C2 | Chính xác ID/thứ tự C1 | Điểm chiếu P0 × affinity, hiệu chuẩn trung bình 1 trong seed |
| C3 | Chính xác ID/thứ tự C1 | `affinity × F/B` |

Tất cả dùng P0 làm nền; profile chính không chọn P2 weighted. Các hàm P2 cũ
giữ để tái lập lịch sử. CLI `c_ablation.py` cũ dừng để tránh chạy nhầm C3;
dùng `c_profiles.py` cho tên C hiện hành.

Entity search → mọi path hai hop → answer-type/P0 → semantic relationship
search → edge vote → node/edge provenance → path2chunk → scorednode2chunk →
dense search/boost → kwd2chunk → Entities/Sources đều chạy. Phép so chính
không dùng RRF/BM25, không pruning và không thay bằng graph-flow.

## 5. Kết quả đo và cách diễn giải

Dev 200 gồm 180 câu có evidence, 207 cặp query/chunk chuẩn. Cùng Qwen index,
parser cache, embedding all-MiniLM-L6-v2, top_k=60, ba chunk/seed,
graph top-30, Sources 4.000 token; 0 API call, không sinh đáp án.

| Bản | Cặp evidence sau cap /207 | Câu giữ đủ evidence /180 |
|---|---:|---:|
| C0 | 96 | 75 |
| C1 | 126 | 102 |
| C2 | 125 | 102 |
| C3 mới | 132 | 108 |
| C3 không dùng relation signal | 133 | 109 |
| C3 không chia background | 101 | 83 |
| Affinity-only trên cùng ID C1 | 133 | 109 |
| C3 không truyền score | 126 | 102 |

C3 so C0: **48 lên /15 xuống**, McNemar chính xác `p=0,0000376`,
Holm cho hai phép so chính `p=0,0000752`. C3 so C1: **9 lên /3 xuống**,
`p=0,146`. So bản không relation: 1/2, `p=1`; so affinity-only: 2/3, `p=1`.

**C3 tốt hơn C0 về retention offline nhưng chưa chứng minh vượt C1. Phần
relation chưa cho lợi ích vượt affinity-only. Đây chưa phải accuracy QA.**
Không quy toàn bộ mức tăng so C0 cho path scorer: C1 đã tạo phần lớn mức tăng.
Không thể kết luận cải thiện multi-hop hoặc contribution khoa học từ lượt này.

Median scoring khoảng 604 ms, retrieval khoảng 1.001 ms trong tiến trình có
cache embedding; chưa có phép đo đối chứng đủ để tuyên bố speedup. Dev đã
được xem nhiều lần; bước xác nhận chất lượng cần QA held-out cùng SLM/index,
báo acc/err/neither, ghép cặp và lặp lượt sinh/chấm theo giao thức của nhóm.

## 6. File và cách chạy

- `minirag/p0_path_scoring.py`: trọng số từng hop, F/B và ablation.
- `minirag/path_projection.py`: chiếu chung nguồn node/cạnh.
- `minirag/path_affinity.py`: chọn ứng viên có query affinity.
- `minirag/path_calibration.py`: hiệu chuẩn local-mean riêng cho C2.
- `minirag/operate.py`: nối điểm vào pipeline và trace.
- `minirag/kg/nano_vector_db_impl.py`: đọc cosine trên ID/cạnh cố định.
- `P0_RELATION_LIFT_PROTOCOL.md`: thiết kế đăng ký trước lượt đo.
- `P0_RELATION_LIFT_FINDINGS.md`: kết quả và giới hạn chi tiết.
- `results/20261109/`: báo cáo số và chứng thực replay của lượt đã chạy.

In cấu hình, không gọi API:

```sh
python reproduce/path/c_profiles.py C3
```

Nhóm cấu hình backend SLM/index và tham số dataset như benchmark đang dùng,
rồi bọc lệnh QA hiện có, lần lượt thay C0/C1/C2/C3:

```sh
python reproduce/path/c_profiles.py C3 -- python reproduce/Step_1_QA.py <tham-số-benchmark>
```

Wrapper chỉ quản lý retrieval, không đổi model, credentials hoặc limiter.
Chạy replay đầy đủ bằng `benchmark_c.py` cần bộ index/cache/artifacts có hash
tương ứng nêu trong README; các tài sản lớn không được đính kèm commit này.
File report là kết quả lượt đo trước khi đóng gói nhánh, không phải một lượt
đo độc lập mới. `baseline.yaml` và index không được sửa.

Kiểm tra bản đóng gói: 40 test liên quan qua; replay khớp 600 thứ hạng
C1/C2/C3 và tám context chạy thật (hai câu × bốn profile). Bộ test 48 của
lượt phát triển trước đó được ghi riêng trong findings, không phải số test
của checkout gọn để phát hành này.
