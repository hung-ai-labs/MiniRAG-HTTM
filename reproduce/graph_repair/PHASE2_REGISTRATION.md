# Graph repair — giai đoạn 2: sửa thang điểm của luồng điểm đường đi (đăng ký trước)

> Viết 09/11/2026, **trước** khi có bất kỳ số đo nào của các nhánh dưới đây. Đóng băng bằng sha256 ghi ở
> `logs/graph_repair/phase2/REGISTRATION.sha256` trước lượt chạy đầu tiên. Thay đổi về sau chỉ thêm ở cuối file, có
> ghi ngày và nói rõ đã xem kết quả nào. Đã xem trước khi viết: báo cáo giai đoạn 1 (`PHASE1_REPORT.md`) và kết quả
> bước 2 của `LIHUA_FLOW.md` (C2/C3 làm hại Evidence Recall trên 435 câu ngoài dev).

## Vấn đề quan sát được

1. Luồng điểm của Hùng (`MINIRAG_PATH_SCORE_FLOW=1`, = C2) nhân vào đóng góp của mỗi chunk trong `kwd2chunk` một
   tổng thô `Σ_đường (a+e+1) × số lần chunk xuất hiện`. Tổng này tỉ lệ với **số đường đi** của thực thể xuất phát, nên
   thực thể hub (`LIHUA`, bậc 331) lấn át: C2 giữ đủ đáp án ở ~25% câu ngoài dev so với ~37% của C0 (12–15 lên /
   58–60 xuống mỗi lượt sinh, p ≤ 4·10⁻⁷).
2. Tầng mất mát lớn nhất của C0 là **L1** (70/207 chunk đáp án, 69/180 câu dev): chunk đáp án có trong Counter của một
   thực thể xuất phát nhưng ngoài 3 chunk được chọn (hạng tốt nhất trung vị 17,5). Mọi đường đi đều cộng **toàn bộ**
   chunk của chính thực thể xuất phát và của mọi node trên đường với trọng số 1, nên chunk của node sở hữu hàng trăm
   chunk được đếm ngang chunk của node chỉ sở hữu 2 chunk.

## Giả thuyết

- **H-A (thang đo):** chuẩn hoá điểm luồng theo từng thực thể xuất phát (chunk tốt nhất = 1) loại bỏ phần hại của C2,
  vì điểm không còn tỉ lệ với số đường đi. Không đổi 3 chunk được chọn trong mỗi thực thể ⇒ dự đoán **ngang C0**.
- **H-B (độ đặc hiệu):** một node sở hữu `df` chunk góp vào mỗi chunk của nó trọng số `1/df` thay vì 1 (tương tự IDF,
  tính trên đồ thị). Chunk được nhiều node đặc hiệu cùng trỏ tới sẽ lên đầu trong thực thể xuất phát; node hub gần như
  không còn quyết định chọn chunk ⇒ nhắm thẳng vào L1.

## Cơ chế (công tắc mới, mặc định tắt, chỉ có nghĩa khi `MINIRAG_PATH_SCORE_FLOW=1`)

| Công tắc | Tác động trong `path2chunk` |
|---|---|
| `MINIRAG_FLOW_NORM=max` | `PathChunkScores[c] ← điểm(c) / max_c' điểm(c')` trong cùng thực thể xuất phát |
| `MINIRAG_FLOW_SPEC=idf` | mỗi lần chunk `c` vào `text_units` từ node `v` (hoặc cạnh), cộng `1/df(v)` thay vì 1; `df` = số chunk trong `source_id` của node/cạnh đó (trước bộ lọc Levenshtein). Thực thể cô lập: điểm `1/df` của chính nó |

Không tham số tự do. Mọi thứ khác giữ như C2: `MINIRAG_PATH2CHUNK_FIX=1` (ngầm qua luồng điểm), thưởng ×2 và ×10 giữ
nguyên (giai đoạn 1: bỏ chúng làm hại), `MINIRAG_PATH_SCORE` tắt (P2 không đổi gì), `top_k` 60, A1@4000,
`MINIRAG_ANSWER_TYPE_FIX=1`, đồ thị `LiHua-World-qwen-modal`, cache parser từ khoá.

| Nhánh | Công tắc |
|---|---|
| **C2** (đối chứng phụ, đã có) | `MINIRAG_PATH_SCORE_FLOW=1` |
| **G-A** | C2 + `MINIRAG_FLOW_NORM=max` |
| **G-B** | C2 + `MINIRAG_FLOW_SPEC=idf` |
| **G-AB** | C2 + cả hai |
| **C0** (đối chứng chính, đã có) | MiniRAG gốc |

## Giai đoạn 2a — dev 180 câu có Evidence (offline, chỉ dùng để CHỌN)

Biến chính: **số câu giữ đủ mọi chunk đáp án** trong Sources cuối (sau A1), như `PHASE1_REPORT.md`. Phụ: Evidence
Recall micro, phân tầng L0–L3, trung vị token Sources. So từng câu với C0 đóng băng
(`logs/c_ablation/graph/C0/C0_records.jsonl`, 75/180), McNemar chính xác.

**Luật chọn (một lần, không chỉnh thêm):** chọn nhánh G-* có số câu đủ đáp án cao nhất; hoà thì chọn nhánh ít thành
phần hơn (G-A < G-B < G-AB). **Chỉ sang 2b nếu nhánh được chọn có lên ≥ xuống so với C0 trên dev.** Không thì dừng,
ghi kết quả phủ định.

**Dự đoán:** G-A ≈ C0 (|lên − xuống| ≤ 5); G-B và G-AB > C2; G-AB tốt nhất trong ba nhánh. Không dự đoán được G-AB có
vượt C0 hay không.

## Giai đoạn 2b — 435 câu ngoài dev × 3 lượt sinh (offline, KẾT QUẢ CHÍNH về truy hồi)

Nhánh được chọn, đặt tên `L-SPEC` (hoặc `L-NORM` nếu G-A được chọn), dựng context bằng `phased_qa.py contexts` với đúng
giao thức `LIHUA_FLOW.md` (cùng `kw_s{101,202,303}.jsonl`, cùng index, `PYTHONHASHSEED=13`). So với L-C0R
(`runs/lihua_world/flow_v1/`), từng lượt sinh, trên 388 câu có Evidence: số câu đủ đáp án, McNemar chính xác.

- "Truy hồi **tốt hơn** C0": cả 3 lượt sinh cùng chiều dương và p < 0,05 ở từng lượt.
- "**Kém hơn**": cả 3 cùng chiều âm, p < 0,05 mỗi lượt. Còn lại: "chưa có bằng chứng khác C0".

## Giai đoạn 2c — accuracy (chỉ khi 2b "tốt hơn" VÀ người dùng đồng ý chi GPU)

Sinh Qwen2.5-3B cho L-SPEC và L-C0R trong cùng deployment Modal, chấm `judge_session.py` 3 lượt, luật đọc F1 của
`LIHUA_FLOW.md`; báo acc / err / neither, theo Single / Multi / Null. Rủi ro đã biết phải báo: Evidence Recall không
đo được câu Null (không có Evidence); trộn RRF từng làm Null đi ngược.

## Hiệu suất

Cùng ngân sách Sources 4.000 token. Báo thêm thời gian truy hồi trung vị / câu so với C0 (chi phí tính `1/df` là tra
`source_id` đã có sẵn trong node — dự đoán không đổi đáng kể).

## Kiểm hồi quy bắt buộc

Tắt cả hai công tắc: C0 khớp `chunk_ids` 180/180 với bản đóng băng; C2 khớp 180/180 với
`logs/c_ablation/graph/C2/C2_records.jsonl`. Test `tests/test_path_score_flow.py`, `tests/test_c_ablation.py` qua.

## Không được trình bày

- Nếu thắng: không gọi là "đồ thị tốt hơn vector" — không so với vector/RRF trong đợt này.
- G-A một mình là sửa thang đo của một bản sửa có sẵn, không phải cơ chế mới; đóng góp chỉ là H-B (hoặc A+B).
- Không suy ra accuracy từ Evidence Recall.

## Sửa đổi 1 (09/11/2026) — kế hoạch ablation, thêm TRƯỚC khi xem bất kỳ số nào của G-A / G-B / G-AB

Chưa xem đầu ra nào của `logs/graph_repair/phase2/` ngoài việc chạy thử `compare_phase2.py` trên hai nhánh đóng băng
C0 (75/180) và C2 (53/180) — đã biết từ giai đoạn 1. Các mục trên không đổi.

**Thiết kế giai thừa 2 × 3** — trục chọn chunk trong thực thể xuất phát × trục điểm đưa vào `kwd2chunk`:

| Chọn chunk ↓ / điểm → | không đưa (như gốc) | tổng thô | chuẩn hoá max |
|---|---|---|---|
| đếm thô mọi đường | C1 (`PATH2CHUNK_FIX=1`) | C2 | G-A |
| đếm `1/df` | **G-B0** (`PATH2CHUNK_FIX=1 FLOW_SPEC=idf`, luồng điểm tắt) | G-B | G-AB |

Mốc: C0. G-B0 thêm vào giai đoạn 2a như nhánh **mô tả** (không tham gia luật chọn ở trên).

**Giai đoạn 2b mở rộng (chỉ khi 2a cho phép sang 2b):** dựng context cho đủ 6 ô + L-C0R trên 435 câu ngoài dev × 3
lượt sinh. Kết quả chính vẫn là nhánh được chọn so với L-C0R (luật ở trên). Ablation, mỗi lượt sinh một họ Holm:
- E1 `1/df` khi không đưa điểm: G-B0 − C1
- E2 `1/df` khi đưa điểm chuẩn hoá: G-AB − G-A
- E3 chuẩn hoá khi có `1/df`: G-AB − G-B
- E4 chuẩn hoá khi đếm thô: G-A − C2
- E5 đưa điểm (chuẩn hoá) so với không đưa, khi có `1/df`: G-AB − G-B0

"Có đóng góp" = cả 3 lượt sinh cùng dấu và p Holm < 0,05 ở từng lượt; còn lại "chưa có bằng chứng". Biến: số câu giữ
đủ chunk đáp án (388 câu có Evidence), McNemar chính xác. Kèm: dịch chuyển tầng L0–L3, tỉ phần token Sources của
thực thể hub top-1% (theo bậc hoặc `df`), Single / Multi.

**Giai đoạn 2c (GPU, cần người dùng đồng ý):** nhánh được chọn vs L-C0R là phép so chính; thêm tối đa một nhánh ablation
(nhánh bỏ `1/df` tương ứng) nếu được duyệt chi thêm. `top_k` 10/5 và ngân sách 2.000 chỉ là sensitivity, không phải
phương pháp.
