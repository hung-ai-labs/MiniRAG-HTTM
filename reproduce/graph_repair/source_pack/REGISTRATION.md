# Người 2 — xếp chunk theo giá trị trên token (đăng ký trước)

> Viết 09/11/2026, **trước** mọi lượt chạy pipeline của các biến thể dưới đây. Đóng băng bằng sha256 ở
> `logs/graph_repair/p_pack/REGISTRATION.sha256`. Sửa về sau chỉ thêm ở cuối, có ngày và nói rõ đã xem số nào.
>
> **Đã xem trước khi viết (phải khai):** `DIAGNOSIS.md`, gồm mô phỏng offline S0–S14 trên dev 180 *đã có đáp án*. Hệ quả: các
> biến thể dưới đây trùng hoặc gần trùng S1, S4, S12; số dev của chúng **đã biết trước** và pipeline thật chỉ tái hiện lại (tất định).
> Vì vậy dev ở đây chỉ làm cổng loại bỏ, không phải bằng chứng. Bằng chứng duy nhất là 435 câu ngoài dev, chưa ai xem.

## Vấn đề quan sát được (số từ DIAGNOSIS.md)

1. Khoảng trống: oracle xếp lại 30 chunk có sẵn cho 104/180 câu đủ đáp án, C0 chỉ 75.
2. Chunk đáp án bị A1 cắt (L3: 33 chunk / 31 câu) nằm ở hạng trung vị 12 với **6.038 token phía trên**, gần 1,5 lần ngân sách 4.000;
   32/33 ca có chunk ≥ 600 token phía trên.
3. Câu mất đáp án có chunk dài hơn (trung vị 599 so với 510 ở 75 câu đủ) nên chỉ vừa 5 chunk thay vì 7. Tập trung vào một từ khoá
   và đói từ khoá **không** phân biệt hai nhóm (DIAGNOSIS Q3, Q4).
4. Ràng buộc: chunk đáp án bị mất dài (trung vị 670) hơn chunk đáp án giữ được (311). Phạt độ dài vì thế vừa giúp vừa hại.

## Giả thuyết

**H-P (chi phí ngân sách).** C0 trả công cho chunk theo điểm nhưng bỏ qua phần ngân sách chunk đó chiếm. Chia điểm cho `token^α`
đưa nhiều chunk độc lập hơn vào 4.000 token và giữ thêm chunk đáp án, **với điều kiện** lợi từ chunk ngắn lớn hơn hại từ việc phạt chunk
đáp án dài. Dự đoán trước: hai tác động gần triệt tiêu trên dev (xem Dự đoán).

## Cơ chế (công tắc mới, mặc định tắt, không tham số tự do)

Chỉ sửa `kwd2chunk` (xuất điểm cuối) và đoạn A1 trong `_build_mini_query_context`. Ngân sách 4.000 và `top_k` = 60 giữ nguyên;
tập 30 chunk **không đổi**, chỉ đổi thứ tự trước A1 và (ở một biến thể) cách lấp ngân sách.

| Công tắc | Tác động |
|---|---|
| `MINIRAG_PACK_ALPHA=a` | xếp lại 30 chunk giảm dần theo `điểm_chunk / token(chunk)^a`; sắp xếp ổn định (hoà giữ thứ tự cũ); `điểm_chunk` là tổng đóng góp của C0 sau ×2/×10; `token` = độ dài mà A1 đo. Trống = tắt |
| `MINIRAG_PACK_FILL=firstfit` | A1 duyệt hết danh sách, bỏ chunk làm tràn rồi lấy tiếp chunk vừa; trống = dừng ở chunk tràn đầu tiên như C0 |

`a` chỉ nhận hai giá trị đóng băng **1** (mật độ thuần) và **0,5** (nửa chi phí): hai đầu mút đã đo ở B1, không dò thêm.

## Biến thể (tối đa 4)

| Nhánh | Công tắc | Vai trò |
|---|---|---|
| **P-FF** | `PACK_FILL=firstfit` | **Đối chứng**, = sửa bước cắt (baseline fix). Không phải phương pháp |
| **P-D1** | `PACK_ALPHA=1` | Phương pháp: mật độ thuần |
| **P-D05** | `PACK_ALPHA=0.5` | Phương pháp: nửa chi phí |
| **P-D05F** | `PACK_ALPHA=0.5` + `PACK_FILL=firstfit` | Phương pháp + lấp ngân sách |

Đối chứng chính vẫn là C0 (`logs/c_ablation/graph/C0/`). Các công tắc `MINIRAG_PATH_*`, `FLOW_*`, `ANSWER_TYPE_FIX=1` không đổi.

## Giai đoạn dev 180 (offline, chỉ để CHỌN / LOẠI)

Biến chính: **số câu giữ đủ mọi chunk đáp án** trong Sources cuối. Phụ: chunk đáp án giữ được, Single/Multi, micro recall, trung vị token
Sources, tập chunk đổi so với C0. So từng câu với C0 đóng băng, McNemar chính xác.

**Luật chọn (áp một lần, không chỉnh):**
1. Chỉ xét P-D1, P-D05, P-D05F. Chọn nhánh có số câu đủ cao nhất. Hoà → nhiều chunk đáp án hơn; vẫn hoà → P-D05 (ít đổi khỏi C0).
2. Nhánh được chọn **chỉ sang 435 câu ngoài dev nếu** cả hai điều kiện đúng: (a) lên ≥ xuống so với C0, và (b) số câu đủ **lớn hơn** P-FF.
   Điều kiện (b) tách "xếp lại" khỏi "lấp ngân sách".
3. Không đạt → dừng, ghi kết quả phủ định. Không thêm biến thể.

## Dự đoán (viết trước khi chạy pipeline)

| Nhánh | Câu đủ | Lên / xuống vs C0 |
|---|---:|---|
| P-FF | 77 | 2 / 0 |
| P-D1 | 76 | 7 / 6 |
| P-D05 | 77 | 6 / 4 |
| P-D05F | 77 ± 1 | cùng cỡ P-D05 |

(Ba dòng đầu lấy từ mô phỏng B1; P-D05F chưa mô phỏng.) Không nhánh phương pháp nào có McNemar p < 0,05 trên dev.
**Dự đoán chính: điều kiện (b) thất bại** (P-D05 = P-FF = 77) ⇒ kết quả phủ định: xếp lại thuần đồ thị theo chi phí token không vượt
sửa bước cắt. Nếu bất ngờ vượt, vẫn phải qua 435 câu × 3 lượt sinh với tiêu chí của nhóm (cùng chiều, p < 0,05 mỗi lượt).

## Ablation (khi sang 435 câu, nếu qua cổng)

1. P-FF so với C0: phần "lấp ngân sách".
2. Nhánh chọn so với P-FF: phần "xếp lại".
3. α = 1 so với α = 0,5.
4. Tách nhóm Null và Single/Multi; độ nhạy `top_k` = 10 (sensitivity, không phải phương pháp).

## Rủi ro

- Câu Null: mật độ ưu tiên chunk ngắn; Evidence Recall không đo được Null; chỉ accuracy mới kết luận được.
- Hiệu ứng biến mất khi `top_k` nhỏ (A1 không còn là nút thắt ở `top_k` = 5).
- Dev đã bị xem qua mô phỏng (xem khai ở đầu).
- Chunk đáp án bị mất dài hơn chunk giữ được, nên phạt độ dài về nguyên tắc có thể hại.
