# Công thức (2) của bài báo — hiện thực trung thành và kiểm offline (đăng ký trước)

> Viết 09/11/2026, trước khi chạy bất kỳ nhánh nào dưới đây trên dev 180. Đã xem trước khi viết: chạy thử 3 câu dev đầu
> (C1 + công tắc) để kiểm code chạy được — ω_e tính mất 135–400 ms/câu, ~1.400 cạnh ứng viên, nhiều cạnh hoà tại ngưỡng
> cắt. Chưa xem số đủ-đáp-án của nhánh nào. Đóng băng bằng sha256 ở `logs/graph_repair/eq2/REGISTRATION.sha256`.

## Vai trò — kiểm độ trung thực khi tái tạo, KHÔNG phải Proposed Method

`PAPER_CODE_AUDIT.md` dòng 3: code không tính Công thức (2). Cuộc thảo luận 09/11 kết luận "(2) không cứu được" dựa trên
G-AB — nhưng G-AB (1/df, chuẩn hoá max) không hiện thực (2). Đợt này trả lời đúng câu hỏi: **nếu hiện thực (2) như bài
báo viết, truy hồi có khá hơn không?** Theo CLAUDE.md §1b, khôi phục cơ chế của bài báo không phải đóng góp; kết quả
dương hay âm đều chỉ là *finding* về tái tạo. Hướng xếp hạng lại tất định (đóng 20/09) không mở lại: đây là cơ chế của
chính bài báo, không phải tín hiệu bề mặt mới.

## Cơ chế — `MINIRAG_EDGE_SCORE=paper` (mặc định tắt), `minirag/paper_edge_score.py`

ω_e(e) = số node thuộc V̂_s ∪ V̂_a nằm trong vùng k bước quanh một trong hai đầu mút của e. Ê_α = các cạnh xếp hạng cao
nhất theo ω_e. Thành phần Σ_{e∈p∧Ê_α} ω_e(e) của Công thức (3) dùng ω_e thật thay cho 1.

Các điểm bài báo bỏ ngỏ, chốt một lần:

| Điểm | Chốt | Lý do |
|---|---|---|
| k | 2 | Giới hạn bước mà code đã dùng cho đường đi |
| V̂_s ∪ V̂_a | `imp_ents` của code (seed + node đúng kiểu đáp án, có bản vá G1) | Giữ nguyên định nghĩa node của hệ thống; chỉ đổi phép chấm cạnh |
| Cạnh ứng viên | Các cạnh nằm trên đường đi ứng viên | Chỉ chúng đổi được điểm đường đi |
| \|Ê_α\| | Bằng số cạnh `goodedge` của code cho câu đó | Chỉ đổi *cạnh nào*, không đổi *bao nhiêu* |
| Hoà điểm | Theo tên cạnh (tất định) | Báo cáo tỉ lệ hoà tại ngưỡng cắt |
| Chiều cạnh | Khớp cả hai chiều (đồ thị vô hướng) | Code gốc chỉ khớp theo chiều `src→tgt` trả về từ vector DB |
| `pairs_append` | Các cạnh Ê_α trên đường, xếp theo hạng ω | Tương tự code xếp theo hạng vector |

Mọi thứ khác giữ nguyên: đồ thị `LiHua-World-qwen-modal`, cache parser từ khoá, `top_k` 60, A1@4000,
`MINIRAG_ANSWER_TYPE_FIX=1`, khung `run_offline.py`.

## Nhánh — mỗi nhánh so với chính nó khi tắt công tắc (chỉ khác đúng phép chấm cạnh)

| Nhánh | Đối chứng (đã có, đóng băng) | Vai trò |
|---|---|---|
| C1 + (2) | C1 `logs/c_ablation/graph/C1` | Họ chính — điểm đường quyết định chọn chunk trong seed |
| C2 + (2) | C2 `logs/c_ablation/graph/C2` | Họ chính — điểm thô đưa vào `kwd2chunk` |
| G-A + (2) | G-A `logs/graph_repair/phase2/g_a` | Họ chính — điểm chuẩn hoá đưa vào `kwd2chunk` |
| C0 + (2) | C0 `logs/c_ablation/graph/C0` | Mô tả — kiểm tuyên bố "trong code gốc điểm không tới đích" |

## Biến và luật đọc (một lần, không chỉnh thêm)

Biến chính: **số câu giữ đủ mọi chunk đáp án** trong Sources cuối, 180 câu dev có Evidence; McNemar chính xác từng câu.
Phụ: Evidence Recall micro, trung vị token Sources.

- Họ chính 3 phép so, hiệu chỉnh Holm. "(2) cải thiện truy hồi trên dev" chỉ khi ≥ 1 phép so có lên > xuống và p Holm
  < 0,05. Ngay cả khi đạt, đó mới là sàng lọc trên dev (đã dùng để chọn ở phase 2) — muốn khẳng định phải theo giao
  thức 2b (435 câu ngoài dev × 3 lượt sinh), không làm trong đợt này.
- Không đạt ⇒ viết "hiện thực trung thành Công thức (2) không cải thiện truy hồi trên dev 180", **không** viết
  "(2) sai về lý thuyết".

## Đo cơ chế (trả lời "bức tường 1" và "bức tường 2" của cuộc thảo luận)

1. **Chi phí:** thời gian tính ω_e/câu (trung vị, p90) so với `retrieval_ms` của cả bước truy hồi.
2. **Bão hoà:** số giá trị ω phân biệt, số cạnh hoà tại ngưỡng cắt và phần của Ê_α do phá hoà theo tên; so với k = 1
   (chỉ ghi số đo, không chạy truy hồi).
3. **Cạnh vàng:** cạnh có `source_id` chứa chunk đáp án của câu. So độ chính xác và độ phủ cạnh vàng của Ê_α theo (2)
   với Ê_α của code (giới hạn trong cạnh ứng viên).

## Dự đoán (ghi trước)

- Chi phí: trung vị < 1 s/câu, < 10% `retrieval_ms` ⇒ "bức tường 1" sai.
- Bão hoà: phần lớn câu có hoà lớn tại ngưỡng cắt.
- Hiệu quả: không phép so nào đạt p Holm < 0,05; C0 + (2) gần như không đổi so với C0.
- Cạnh vàng: không dự đoán chiều.

## Kiểm hồi quy

Công tắc tắt ⇒ code đi đúng nhánh `edge_vote_path` cũ (không đổi dòng nào). Test: `tests/test_paper_edge_score.py`, và
`test_path_score_flow`, `test_flow_spec_norm`, `test_c_ablation` qua. Thêm: C0 tắt công tắc, 3 câu đầu, khớp `chunk_ids`
với C0 đóng băng.
