# Thiết kế lại path scoring trên P0 — kết quả 09/11/2026

Đã bỏ P2 weighted cũ khỏi các profile chính. Phiên bản hiện hành là
`20261109-p0-relation-lift`; **C3 hiện tại là phương pháp P0 mới**, không phải
C3/P2 của các lượt thử cũ. C0/C1/C2 giữ nguyên; dữ liệu lịch sử không đổi tên.

## Cơ chế và giả thuyết

Đối chiếu MiniRAG v1 §2.2.2: paper chấm path bằng seed similarity, answer-node
presence và trọng số các key relationship; bước chọn chunk cũng đã dùng
similarity giữa câu hỏi với chunk kèm mô tả cạnh
([nguồn chính](https://arxiv.org/html/2501.06713v1)). P0/P2 là tên nội bộ của
implementation/thí nghiệm, không phải tên thuật toán paper đặt. Vì vậy query
affinity được code bổ sung trong repo nhưng không tự nó là novelty so paper.
Khác biệt thiết kế đang thử là R(path) từ ngữ nghĩa từng hop và hiệu chỉnh
nguồn bằng F/B; hiệu quả của khác biệt đó phải đọc qua ablation bên dưới.

P0 gốc vẫn chạy, giữ nguyên:

```text
q0(path) = số node đúng kiểu đáp án + số edge vote gốc + 1
```

Thay vì thêm hệ số seed và độ dài cố định của P2, bản mới đọc cosine giữa
câu hỏi và vector quan hệ hiện có của **mọi cạnh vật lý trên path**. Trung bình
nhân qua các hop cho mức hỗ trợ ngữ nghĩa R(path):

```text
q(path) = q0(path) * R(path)
```

Việc đọc cosine không thay thế semantic edge search, goodedge hoặc edge vote
gốc. Không thêm/bớt path, không thay index/embedding, không tạo nguồn mới.
Tính ba bản chiếu nguồn node/cạnh trên cùng tập path:

- Prior: dùng q0, để giữ nguyên cách C1 chọn ứng viên.
- Background B: mọi path có trọng số 1, đo mức nguồn được nhắc do cấu trúc.
- Query F: dùng q, đo hỗ trợ từ P0 và độ liên quan của các cạnh.

Điểm chunk mới là `query_chunk_affinity * F/B`. Phép chia giảm lợi thế chỉ do
nhiều path cùng trích một nguồn. B>0 trên mọi chunk được chọn; không thêm hệ
số làm trơn hoặc quét tham số. Nếu toàn bộ path của một seed có R=0, fallback
về q0 được định nghĩa trước và ghi nhận riêng. Node cô lập giữ nguồn node gốc.

**Giữ đúng ID và thứ tự ba chunk/seed của C1.** Chỉ trọng số đưa vào kwd2chunk
thay đổi; không chuẩn hóa local_mean lần nữa vì F/B đã là tỷ số không đơn vị.
Seed score, first-seed boost, dense boost và phạm vi boost cũ giữ nguyên.

## So sánh chính — evidence, không phải accuracy

Cùng dev 200, gồm 180 câu có evidence và 207 cặp query/chunk chuẩn; cùng Qwen
index, parser cache, all-MiniLM-L6-v2, top_k=60, local ba, graph top-30 và
Sources 4.000 token. **Không RRF/BM25 trong phép so chính.**

| Bản | Evidence sau cap /207 | Câu giữ đủ evidence /180 |
|---|---:|---:|
| C0 | 96 (46,38%) | 75 (41,67%) |
| C1 | 126 (60,87%) | 102 (56,67%) |
| C2 — P0 hiệu chuẩn trước đó, chỉ tham chiếu | 125 (60,39%) | 102 (56,67%) |
| **C3 — P0 thiết kế mới** | **132 (63,77%)** | **108 (60,00%)** |

McNemar trên câu giữ đủ evidence:

| C3 so với | Lên / xuống | Net | p chính xác | p Holm, hai phép so chính |
|---|---:|---:|---:|---:|
| C0 | 48 /15 | +33 | 0,0000376 | **0,0000752** |
| C1 | 9 /3 | +6 | 0,146 | **0,146** |

C3 tăng số lượng so với C1 nhưng **chưa chứng minh được cải thiện vượt C1**.
Các câu đổi kết quả là retention của chunk chuẩn, không phải đáp án QA đúng/sai.

## Ablation bắt buộc

Mọi ablation dùng cùng danh sách/thứ tự ứng viên C1:

| Bản | Evidence /207 | Câu đủ evidence /180 |
|---|---:|---:|
| Full C3 | 132 | 108 |
| Không dùng độ liên quan quan hệ: F dùng q0 | 133 | 109 |
| Không chia nền B | 101 | 83 |
| Chỉ dùng query–chunk affinity ở ranking | 133 | 109 |
| Không truyền điểm chung | 126 | 102 |

Full so với không dùng quan hệ: 1 lên /2 xuống, p=1. So với affinity-only:
2 lên /3 xuống, p=1. **Chưa có bằng chứng phần quan hệ/đồ thị thêm lợi ích
so với tín hiệu query–chunk.** Không được quy toàn bộ mức tăng so với C0 cho
path scoring mới: C1 đã cải thiện phần lớn nhờ chọn ứng viên trước đó.

Hiệu chỉnh nguồn lặp có tác dụng so với nhân khối lượng nguồn thô: full so
với không chia B có 33 lên /8 xuống, p=0,000112. Nhưng việc hồi phục bản điểm
thô chưa đủ chứng minh phương pháp tốt hơn C1 hay affinity-only.

## Các luồng gốc vẫn chạy

Entity/type search, tất cả path gốc và seed eligibility, cal_path_score_list
(P0), semantic relationship search, edge_vote_path, nguồn node/cạnh,
path2chunk, scorednode2chunk, dense search/boost, kwd2chunk và Entities/Sources
đều giữ. Không thay bằng graph-flow/P3, không pruning và không đổi top-k/token.
Hàm P2 weighted cũ bị chặn bằng assertion trong toàn bộ lượt chạy: **0 lần gọi**.

Đã tính trên 3.979.701 path gốc. Có 540.468 path nhận hỗ trợ quan hệ bằng 0;
chúng vẫn được duyệt và chiếu, không bị cắt khỏi danh sách path. Có 774
seed/query fallback theo quy tắc q0 đã đăng ký trước. Đó là số lần fallback
trên seed, không phải 774 câu hỏi.

## Kiểm tra và giới hạn

- C1 và ablation không truyền điểm khớp từng byte với 200 context đã đóng băng.
- C3 chạy qua pipeline thật trên 200 câu, khớp context tái dựng và source IDs.
- Sáu lượt chạy độc lập C0/C1/C2 trên hai câu đầu đều khớp.
- 48 test liên quan đã qua. Runner cấu hình hiện hành cũng khớp tám context
  thật C0/C1/C2/C3 trên hai câu đầu.
- Replay độc lập tái tạo 600 thứ hạng C1/C2/C3; 200 tập ID/thứ tự ứng viên,
  group và vector ranking khớp dữ liệu C1 cũ.
- Index, parser, dữ liệu, baseline.yaml và nguồn thí nghiệm giữ nguyên hash
  trong lượt đo; dùng bản sao index tạm; không có lời gọi API hoặc generation.
- Single: C3 giữ đủ 98/159 câu, C1 93. Multi: C3 10/21, C1 9. Không kết luận
  cải thiện multi-hop từ một câu chênh trên dev nhỏ.
- Context C3 đổi ở 172/200 câu so C1, gồm 19/20 câu Null. Chưa đo acc/err/neither
  của các thay đổi đó. Nhiều câu đổi context không đồng nghĩa tăng accuracy.
- Median scoring mới 604 ms; median retrieval trong lượt chạy 1.001 ms (khoảng một giây), có
  cache embedding trong tiến trình. Không tuyên bố speedup so baseline tái dùng.

Đây là lượt phát triển trên dev đã xem nhiều lần. Chưa có QA accuracy, xác nhận
held-out, lặp lượt sinh hoặc bằng chứng novelty. Chưa đủ để chốt C3 làm đóng
góp khoa học vượt C1; kết quả không được sửa bằng cách chọn lại hệ số sau đo.

## Code và chạy lại

Code chính: `minirag/p0_path_scoring.py`; projector dùng chung độc lập scorer:
`minirag/path_projection.py`. P2 cũ chỉ giữ cho lịch sử, không profile chính nào
bật nó. C3 hiện hành đặt:

```text
MINIRAG_PATH_SCORE=
MINIRAG_PATH_PROJECTION=p0_relation_lift
MINIRAG_PATH_SELECTION=c1_affinity
MINIRAG_PATH_SCORE_FLOW=1
MINIRAG_PATH_SCORE_CALIBRATION=
```

Đăng ký trước: `P0_RELATION_LIFT_PROTOCOL.md`. Artifacts ở
`logs/p0_paths/20261109_dev200/`: manifest, source snapshots, inputs, contexts,
replay, report và independent_replay_validation.json.

```sh
TIKTOKEN_CACHE_DIR=/private/tmp/minirag-score-flow-tiktoken .venv/bin/python reproduce/path/eval_p0_paths.py --output logs/p0_paths/NEW_RUN
.venv/bin/python reproduce/path/replay_p0_paths.py logs/p0_paths/NEW_RUN
```

Runner từ chối ghi đè lượt cũ. Tên C3 trong các study trước giữ nghĩa lịch sử;
không dùng số 101 của P2 cũ làm kết quả cho C3 mới.
