# Kiểm tra lại P2 sau khi nối luồng điểm

## Vấn đề và phạm vi bản sửa

P2 tạo trọng số cho path; `edge_vote_path` thêm phiếu cạnh. Nhưng mặc định
`path2chunk` chỉ lấy Counter của path cuối, rồi bỏ điểm khi chuyển thành ID.
`kwd2chunk` sau đó dùng điểm seed để xếp hạng. Vì vậy kết quả âm trước đây chưa
đủ để bác bỏ công thức P2 trong một pipeline có truyền đầy đủ điểm.

`MINIRAG_PATH_SCORE_FLOW=1` bật đồng thời hai bước nối dây:

1. Chọn từ Counter cộng dồn **mọi path**, kể cả khi `MINIRAG_PATH2CHUNK_FIX=0`.
2. Giữ điểm của các chunk đã chọn trong `PathChunkScores` và nhân nó vào đóng
   góp của seed ở `kwd2chunk`. `Path` vẫn là danh sách ID như trước.

Cụ thể, với seed s và chunk c:

    S_s(c) = sum_p count(c trong nguồn của p) * (node_score(p) + edge_votes(p) + 1)
    contribution_s(c) = upstream_seed_boost(s, c) * S_s(c)

Chỉ top-3 chunk mỗi seed được chuyển tiếp như pipeline hiện tại. Seed không có
path dùng số lần xuất hiện nguồn làm điểm dự phòng. Giữ nguyên công thức P2,
giới hạn ứng viên, các boost upstream và A1; chưa thêm chuẩn hóa/phạt hub.
Đặc biệt, boost vector upstream có hành vi nhân x10 vào biến score rồi giữ
cho các chunk tiếp theo của seed; bản sửa này cũng giữ hành vi ấy để cô lập
việc nối điểm. Raw sum vẫn có thể ưu ái hub và P2 vẫn chứa seed_score trước khi
nhân thêm điểm seed downstream. Đây là các hạn chế cần đo, chưa phải cơ chế mới.

Công tắc mặc định tắt để giữ các kết quả lịch sử. Context log khi bật có thêm
`path_score_flow`, `path_score_mode`, `path_chunk_scores` để truy vết.

`vector` và `vector_bm25` thay bảng xếp hạng đồ thị nên bị từ chối khi bật công
tắc này. Muốn thử P2 trong Sources, dùng đồ thị thuần, `rrf` hoặc `rrf_bm25`.
Chưa có cơ chế thêm tín hiệu path vào B2/NOGRAPH trong bản sửa này.

## Kiểm tra không gọi API

Từ thư mục gốc repo:

```bash
.venv/bin/python -m unittest discover -s tests -p test_path_score_flow.py -v
```

Các ca tổng hợp kiểm tra cả trường hợp **ID chunk theo seed không đổi nhưng
thứ hạng toàn cục đổi**, và đường truyền tới Sources sau cắt ngân sách. Tokenizer
trong test được thay bằng đếm từ, không phải phép đo retention A1 thật.

## Đối chứng offline trên dữ liệu thật

Chạy P0 và P2 trên **cùng đường truyền đã sửa**, cùng fusion và cache parser:

```bash
.venv/bin/python reproduce/path/eval_offline.py --mode step0 --score-flow --fusion graph --limit 5
.venv/bin/python reproduce/path/eval_offline.py --mode p2 --score-flow --fusion graph --limit 5
```

Bỏ `--limit 5` để đo toàn bộ 180 câu dev có Evidence. Cần có embedding local và
tokenizer đã cache. Script chỉ dựng context, cấm gọi parser API khi cache thiếu,
và chạy trên bản sao index tạm. Kết quả mới nằm trong `logs/path_score_flow/graph/`,
gồm báo cáo và từng câu trong `step0_records.jsonl` / `p2_records.jsonl`.
Chạy lại cùng mode sẽ thay báo cáo mới đó; `logs/path/` lịch sử được giữ nguyên.
`--output-dir` cho phép tách từng lượt. Với `--fusion rrf` hoặc `rrf_bm25`, kết quả
mặc định đi vào thư mục riêng theo fusion.

So sánh theo câu: `graph_ids`, `ranked_ids`, `chunk_ids`, `context_sha256`,
retention và số câu giữ đủ evidence. Retention bằng nhau không chứng minh hai
context giống nhau; cần đối chiếu ID/thứ tự/hash. Evidence chỉ làm nhãn đánh giá.

Để phân rã tác động, đo bốn ô P0/P2 × score-flow tắt/bật với cùng điều kiện.
Không lấy P2 đã sửa so riêng với P0 chưa sửa rồi quy toàn bộ chênh lệch cho P2.
Sau đó mới so với B2/NOGRAPH mạnh nhất, cùng budget và prompt. Bật lại graph
fusion là một thay đổi riêng, cần có đối chứng graph không P2.

Đây là **sửa luồng điểm**, chưa phải bằng chứng accuracy tăng hoặc đóng góp
thuật toán. Chỉ chạy generation/judge sau khi phép đo offline có tín hiệu tốt;
đánh giá cuối báo acc/err/neither, nhiều lượt sinh, McNemar ghép cặp và latency.
Không cần index lại vì chỉ đổi ranking.
