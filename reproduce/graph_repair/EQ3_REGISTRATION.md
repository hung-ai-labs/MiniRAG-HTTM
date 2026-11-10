# Công thức (3) và top-k đường của bài báo — đăng ký trước

> Viết 09/11/2026, trước mọi lượt chạy Eq. (3) trên dev 180. Đã đọc PDF bài báo, §3.2.2 tr. 37125 và Phụ lục A.3 tr. 37134; `PHASE1_REPORT.md`, `PHASE2_REGISTRATION.md`, `GRAPH_TEAM_PLAN.md`, `EQ2_REGISTRATION.md`. **Chưa xem kết quả EQ2**. Đóng băng bằng `logs/graph_repair/eq3/REGISTRATION.sha256`. Sau khi đóng băng, chỉ thêm phụ lục có ngày và khai báo kết quả đã xem.

## Vai trò — độ trung thực tái tạo, KHÔNG phải Proposed Method

`PAPER_CODE_AUDIT.md` dòng 4–5: mã công bố thiếu hệ số ω_v, không chọn top-k đường và cuối vòng lặp chọn chunk theo duy nhất đường cuối. Đây là nấc `+Eq3` của baseline thứ hai **C-paper**, không phải cải tiến giải thuật mới theo CLAUDE.md §1b. Kết quả dương hoặc âm đều là finding. C0 và các đối chứng đã đóng băng không đổi.

## Cơ chế — `MINIRAG_PATH_SELECT=paper` (mặc định tắt)

Sau `edge_vote_path` (hoặc công tắc Eq. 2), mỗi đường p nhận `ω_p(p|v_q) = ω_v(v_s|v_q) × (1 + Σ ω_e(e) + Σ count(v,p))`. Xếp hạng, chỉ giữ 50 đường đầu cho mỗi cặp còn biểu diễn được; sau đó `path2chunk` cộng `ω_p × số lần chunk xuất hiện` qua **mọi đường được giữ** trong seed, chọn tối đa 3 chunk. Điểm đường như vậy thật sự tham gia thứ tự chunk; luồng điểm C2/G-A, nếu bật, tiếp tục nhận tổng điểm chunk như trước. Không đổi thuật toán `kwd2chunk`, boost ×2/×10, A1@4000 hoặc top-k seed/chunk.

| Điểm bài báo bỏ ngỏ / khác mã | Chốt một lựa chọn | Lý do và giới hạn |
|---|---|---|
| `ω_v(v_s|v_q)` | `Score` của seed từ `entity_name_vdb.query`, trường `distance` tức cosine tên entity–query entity | Cùng phép tìm seed hiện có; không embedding hoặc gọi model mới |
| `K` đường/cặp | **50**, cố định, không sweep | Phụ lục A.3, bảng A3 thử 4/10/50 và 50 cao nhất; bài báo **không ghi default rõ ràng**. Đây là lựa chọn mơ hồ đã chốt trước khi đo |
| Một “cặp” | Một query entity–seed còn lại sau phép gộp dict hiện tại; seed trùng giữa query entities giữ `Score` của lần khớp cuối | Mã gộp trước duyệt đường, không còn đủ dữ liệu để tái lập tất cả cặp gốc; nêu là giới hạn fidelity |
| Đường ứng viên | Các đường 2-hop mà `get_neighbors_within_k_hops` trả về, không sinh đường mới | Cô lập bước Eq. (3); khác chiều dài n=4 ví dụ ở A.3 |
| `Σ count(v,p)` | `scorelist[0]` từ `cal_path_score_list` | Cùng tập answer node và đếm hiện tại; không thay answer-type |
| `Σ ω_e(e)` | `scorelist[1]` | Eq. 2 tắt: số cạnh `goodedge` khớp, mỗi cạnh =1; Eq. 2 bật: tổng ω_e thực. Hai switch độc lập và kết hợp được |
| Chọn chunk sau top-k | Counter cộng dồn mọi đường được giữ, từng đóng góp nhân `ω_p`; chọn 3 chunk lớn nhất trong seed | Sửa dòng 5 của audit cùng lúc để điểm đường đến được Sources; không dùng Counter của đường cuối |
| Hoà điểm đường | Tên đường tuple theo thứ tự từ điển tăng | Tất định cả khi hoà ở vị trí thứ 50 |
| Seed không có đường | Giữ fallback chunk từ node seed | Không bỏ seed cô lập |

## Nhánh — so với chính nó khi tắt công tắc

| Nhánh | Đối chứng đóng băng | Vai trò |
|---|---|---|
| C1 + Eq3 | C1 `logs/c_ablation/graph/C1` | Họ chính: Counter cộng dồn, không luồng điểm |
| C2 + Eq3 | C2 `logs/c_ablation/graph/C2` | Họ chính: điểm thô vào `kwd2chunk` |
| G-A + Eq3 | G-A `logs/graph_repair/phase2/g_a` | Họ chính: chuẩn hoá max trước `kwd2chunk` |
| C0 + Eq3 | C0 `logs/c_ablation/graph/C0` | Mô tả: cùng công tắc tự sửa lỗi đường cuối |
| C1 + Eq2 + Eq3 | C1 + Eq2 (lượt Eq2 đang chạy) | Mô tả tính kết hợp, **không** đưa vào họ Holm; không suy diễn tác dụng riêng Eq3 từ so với C1 |

Mọi lượt: đồ thị Qwen `LiHua-World-qwen-modal`, parser cache, `top_k=60`, A1@4000, `MINIRAG_ANSWER_TYPE_FIX=1`. Đối chứng có cùng biến môi trường khác; Eq. 2 chỉ bật trong dòng kết hợp. Không chỉnh `baseline.yaml`.

## Biến chính và luật đọc

**Số câu giữ đủ mọi chunk đáp án** trong Sources cuối của 180 câu dev có Evidence. Ghép từng câu với đối chứng cùng họ, báo b (thiếu→đủ), c (đủ→thiếu), McNemar chính xác hai phía. Ba phép so họ chính hiệu chỉnh Holm; “Eq3 tăng retention trên dev” chỉ khi ít nhất một phép b>c và p Holm<0,05. Phụ: Evidence Recall micro, token Sources trung vị, Single/Multi, số chunk vàng lên/xuống. Nếu không đạt: chỉ nói “chưa thấy lợi ích trên dev”, không kết luận công thức vô ích.

Dev 180 đã được dùng để chọn trong phase 2, nên **chỉ là sàng lọc**. Xác nhận cần 435 câu ngoài dev × 3 lượt sinh/parser seed theo giao thức `LIHUA_FLOW.md`, ghép cặp từng lượt và xét tính cùng chiều; không suy accuracy từ Evidence Recall. Nhiễu giữa lượt sinh theo CLAUDE.md §3 quan trọng hơn sàn nhiễu judge.

## Đo chi phí và cơ chế

Ghi `paths_before`, `paths_after`, số cặp và thời gian chọn đường mỗi câu bằng `MINIRAG_PATH_SELECT_LOG`; báo trung vị/p90 thời gian, phần trăm thời gian truy hồi, phân bố tỷ lệ giữ đường và số ca hoà tại ranh K (nếu trích xuất từ điểm). Giữ cùng ngân sách token, đo median Sources tokens. Không chạy thử tham số K khác trong họ chính.

## Dự đoán ghi trước

- Chọn đường giảm mạnh số đường từ trung vị khoảng 20.000/câu; chi phí xếp hạng tăng nhưng dưới 10% thời gian truy hồi.
- C1 có khả năng đổi nhiều chunk L1 vì điểm đường nay đến Counter; không dự đoán dấu retention do đường vàng cũng có thể bị cắt.
- C2 có khả năng giảm tác hại hub vì chỉ giữ tối đa 50 đường/seed, nhưng điểm thô vẫn cộng theo số đường; không dự đoán vượt C0.
- C0 không còn bất biến như D1 (0/180 của mã cũ), vì sửa đường truyền điểm và chọn top-k; kết quả của Eq2+Eq3 không được dùng để chọn lại Eq3.

## Kiểm hồi quy

Công tắc tắt đi đúng nhánh cũ từng dòng và không tạo `PathPaperScores`. Unit test: tắt không đổi, thứ tự top-k và hoà, hệ số ω_v, cộng chunk qua đường được giữ, phối hợp Eq2, lặp lại tất định. Chạy `test_paper_*.py`, `test_path_score_flow.py`, `test_flow_spec_norm.py`, `test_c_ablation.py`. Khi có quyền chạy offline riêng: C0 tắt khớp `chunk_ids` 180/180 với bản đóng băng, trước mọi phép đo Eq3; **không chạy offline trong worktree này lúc máy đang bận**.

## Không được trình bày

- Không gọi Eq3, top-k đơn thuần, hoặc sửa Counter đường cuối là Proposed Method.
- Không so điểm nhánh bật với đối chứng thuộc họ khác để quy nguyên nhân cho Eq3.
- Không nói đồ thị thắng vector/RRF, Multi-hop hay accuracy từ riêng retention dev.
- Không coi K=50 hay cách gộp cặp là mặc định được tác giả xác nhận; ghi giới hạn này khi trích kết quả.

## Sửa đổi 1 (09/11/2026) — thêm sau khi đóng băng, TRƯỚC mọi lượt chạy Eq3; chưa xem kết quả EQ2 hay Eq3

Không đổi cơ chế, nhánh hay luật đọc; chỉ bổ sung một hệ quả toán học cho phần dự đoán. `ω_v(v_s|v_q)` là **hằng số
trong một seed** (mọi đường của seed nhân cùng `Score`), nên nó không đổi thứ tự top-K đường trong seed, cũng không đổi
thứ tự 3 chunk được chọn trong seed. Do đó:

- **C1 + Eq3:** ω_v không có tác dụng; mọi thay đổi so với C1 đến từ `(1 + Σω_e + Σcount)`, cắt top-K và việc dùng
  điểm đường trong Counter.
- **G-A + Eq3:** chuẩn hoá max theo seed triệt tiêu ω_v; như trên.
- **C2 + Eq3:** ω_v là thành phần duy nhất của Eq3 tác động *giữa các seed* (qua tổng điểm thô vào `kwd2chunk`).

Khi trình bày: không quy bất kỳ hiệu ứng nào của nhánh C1/G-A cho ω_v. Bản đăng ký gốc giữ nguyên hash ở
`logs/graph_repair/eq3/REGISTRATION.sha256`; hash sau sửa đổi ghi ở `REGISTRATION_AMEND1.sha256`.
