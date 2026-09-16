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

## Cách tính

`reproduce/null_audit/score_label_audit.py`: Cohen's κ giữa hai người; và bảng độ nhạy Null acc / err / neither của **mọi cấu
hình cùng lúc** khi bỏ các câu `CO_DU`, rồi bỏ thêm `CO_MOT_PHAN`.

## Cách dùng kết quả

**Chỉ độ nhạy và Limitations.** Không thay số chính thức, không đụng cổng tầng D, không dùng để chọn biến thể.

## File kết quả

`logs/null_audit/d3_label_audit/` — `sheet_A.csv`, `sheet_B.csv`, `ket_qua.txt`.
