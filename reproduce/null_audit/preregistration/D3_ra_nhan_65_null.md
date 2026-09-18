# Đăng ký trước — Đ3: rà tay toàn bộ 65 nhãn Null

**Việc:** Đ3 (xem [`docs/DE_XUAT_CAI_THIEN_NULL.md`](../../../docs/DE_XUAT_CAI_THIEN_NULL.md) mục 4).
**Ngày chốt:** 16/09/2026 — chốt TRƯỚC khi có nhãn nào của người.

## Vì sao

Cả 65 câu Null dùng chung đáp án vàng "Insufficient information". Kiểm toán 15/09 đã tìm được 1 câu nhãn sai rõ ràng và 2 câu
đáng tranh luận, nhưng **chỉ tìm trong số câu bị chấm sai**. Câu Null thực ra có đáp án mà model từ chối thì vẫn được chấm
`accurate` — tức cộng điểm oan cho cấu hình ít chịu trả lời.

## Mẫu và bằng chứng đưa cho người rà

- Toàn bộ 65 câu Null trong `dataset/LiHua-World/qa/query_set.csv`.
- Mỗi câu kèm: **10 chunk khớp nhất theo BM25** trên nguyên văn câu hỏi (Okapi k1 = 1,2, b = 0,75 — cùng cấu hình với B1/B2),
  và các chunk **đã từng vào Sources** của bất kỳ nhánh nào (đọc từ log context của tầng D nếu có trên máy). Với mỗi chunk
  hiển thị 2 dòng khớp nhất.
- **Lệch so với đề xuất ban đầu, đã khai báo:** không dùng top-10 theo vector. Lý do: dựng lại danh sách vector cần nạp model
  embedding, làm phiếu khó tái lập; danh sách "đã vào Sources" là bằng chứng sát hơn và tái lập được từ file đã commit.
- Sinh bằng `reproduce/null_audit/make_label_audit_sheet.py`. Người rà được phép tra thêm corpus tự do.

## Sửa đăng ký, 16/09/2026 — phiếu tốt hơn, và một người rà

**Chốt trước khi có bất kỳ nhãn nào.**

**(a) Bằng chứng trong phiếu.** Bản đầu chỉ có BM25 top-10 và chunk đã vào Sources; thử đọc thì thấy với nhiều câu, BM25 trả về
đoạn hội thoại không liên quan (hỏi giờ ăn sáng, trả về chuyện đàn guitar). Phiếu mới ghép **bốn** nguồn ứng viên, bỏ trùng, trung
bình 17 chunk mỗi câu:

| Nhóm | Cách lấy | Có ứng viên ở |
|---|---|---|
| MỐC THỜI GIAN | ngày tháng nhắc trong câu hỏi khớp dấu thời gian của chunk; ngày trần ("ngày 9") phải kèm đúng người được nhắc | 6/65 câu |
| NGƯỜI | mọi người được nhắc trong câu hỏi cùng xuất hiện trong chunk | 63/65 câu |
| BM25 | top 10 trên nguyên văn câu hỏi | 65/65 câu |
| ĐÃ VÀO CONTEXT | chunk từng vào Sources của bất kỳ nhánh nào | 63/65 câu |

**(b) Một người rà thay vì hai.** Nhóm giao Đ3 cho **thành viên 2 (Anh Tài)**; hướng dẫn:
[`docs/phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md`](../../../docs/phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md).
- **Cái mất:** không tính được Cohen's κ, nên không có thước đo độ tin cậy của việc gán nhãn.
- **Hệ quả khi báo cáo:** mọi con số của Đ3 phải ghi là **cách đọc của một người**, và nêu trong Limitations.
- **Giảm nhẹ:** bắt buộc ghi `chunk_id` và `trich_dan` cho mọi câu gán `CO_DU` hoặc `CO_MOT_PHAN`, để người khác kiểm lại được
  mà không phải đọc lại từ đầu.
- Nếu sau này có người thứ hai rảnh, rà 10 câu bất kỳ trong `sheet_B.csv` là script tự tính κ trên phần chồng lấn.

## Người gán nhãn và cách làm mù

Hai người, mỗi người một file (`sheet_A.csv`, `sheet_B.csv`), làm **độc lập**. Phiếu **không** chứa câu trả lời của bất kỳ
cấu hình nào và **không** chứa phán quyết của giám khảo. Câu bất đồng do người thứ ba quyết.

## Nhãn phải điền

| Cột | Giá trị | Nghĩa |
|---|---|---|
| `nhan` | `KHONG_CO` / `CO_DU` / `CO_MOT_PHAN` | corpus không có đáp án / có đủ đáp án / có một phần hoặc mơ hồ |
| `doi_mot_chi_tiet` | `CO` / `KHONG` | câu hỏi có đổi một chi tiết so với sự kiện có thật không (sai ngày, sai dịp, sai từ như *bread* so với *pastries*) |
| `chunk_id` | mã chunk | bằng chứng, bắt buộc khi `nhan` khác `KHONG_CO` |
| `trich_dan` | trích nguyên văn | bằng chứng |
| `ghi_chu` | tự do | tuỳ chọn |

**Quy tắc chốt trước:** câu `doi_mot_chi_tiet = CO` mặc định vẫn là `KHONG_CO` (Null đúng thiết kế); cờ này chỉ để bảng độ
nhạy tách được hai cách hiểu.

## ⚠ Nhiễm — phát hiện 18/09/2026, sau khi người rà đã nộp

Bản hướng dẫn giao cho người rà ([`docs/phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md`](../../../docs/phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md),
mục "Ví dụ minh hoạ") ghi là ví dụ **không nằm trong phiếu**, nhưng thực ra cả bốn ví dụ đều là câu có thật trong phiếu, và bảng ví
dụ nêu luôn nhãn mong đợi. Lỗi của người viết hướng dẫn (Hùng), không phải của người rà.

| Dòng | Câu hỏi | Nhãn hướng dẫn gợi ý | Nhãn người rà điền |
|---|---|---|---|
| `L005` | bữa tối 20/1/2026 | `KHONG_CO` / `KHONG` | `KHONG_CO` / `KHONG` |
| `L023` | góp ý của Yuriko tại buổi gặp | `CO_MOT_PHAN` / `CO` | `CO_MOT_PHAN` / `CO` |
| `L031` | loại bánh mì mới | `KHONG_CO` / `CO` | `KHONG_CO` / `CO` |
| `L054` | số đo cửa sổ | `CO_DU` / `KHONG` | `CO_DU` / `KHONG` |

Bốn dòng trùng khớp hoàn toàn với gợi ý, nên **không được coi là phán đoán độc lập**. Nặng thêm ở chỗ ba trong bốn dòng (cửa sổ,
bánh mì, Yuriko) đúng là ba câu mà đợt kiểm toán 15/09 đã nghi là nhãn sai — tức là phần hướng dẫn này làm lộ đúng giả thuyết mà
mục 4 của chính nó cấm người rà biết trước.

**Xử lý, chốt 18/09:**
- `L005`, `L023`, `L031`, `L054` đánh dấu **nhiễm**. `score_label_audit.py` in thêm một cột đã bỏ bốn dòng này, bên cạnh các cột cũ;
  mọi chỗ trích dẫn Đ3 phải kèm cột đó.
- Không yêu cầu rà lại bốn dòng: người rà đã đọc gợi ý, làm lại cũng không lấy lại được tính độc lập. Muốn có nhãn sạch cho bốn câu
  này thì phải là **người khác** và có đăng ký mới.
- Ví dụ trong cả hai bản hướng dẫn đã đổi sang tình huống bịa (18/09).
- Kết luận của Đ3 (nhãn không giải thích được khoảng cách Null của B2) vẫn giữ: nó là phân tích độ nhạy, và câu hỏi rubric sau đó đã
  được Đ6 đo trực tiếp.

## Cách tính

`reproduce/null_audit/score_label_audit.py`: Cohen's κ giữa hai người; và bảng độ nhạy Null acc / err / neither của **mọi cấu
hình cùng lúc** khi bỏ các câu `CO_DU`, rồi bỏ thêm `CO_MOT_PHAN`.

## Cách dùng kết quả

**Chỉ độ nhạy và Limitations.** Không thay số chính thức, không đụng cổng tầng D, không dùng để chọn biến thể.

## File kết quả

`logs/null_audit/d3_label_audit/` — `sheet_A.csv`, `sheet_B.csv`, `ket_qua.txt`.
