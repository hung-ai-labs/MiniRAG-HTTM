# Đăng ký trước — Đ1: người chấm lại nhóm Null, phân tầng theo kiểu câu trả lời

**Việc:** Đ1 (xem [`docs/DE_XUAT_CAI_THIEN_NULL.md`](../../../docs/DE_XUAT_CAI_THIEN_NULL.md) mục 4).
**Ngày chốt:** 16/09/2026 — chốt TRƯỚC khi có bất kỳ nhãn nào của người.

## Câu hỏi cần trả lời

Với câu Null, đáp án vàng "Insufficient information" vừa là nội dung cần truyền đạt, vừa trùng với định nghĩa `neither`
("nói không biết, từ chối"). Rubric không nói câu trả lời **pha trộn** — nêu sự kiện gần giống rồi nói chi tiết được hỏi
không có — phải chấm thế nào. Đ1 đo xem người và Gemini lệch nhau ở đâu, và lệch bao nhiêu.

## Mẫu

- Tổng thể: 45 câu Null ngoài dev × 4 nhánh (V3, vector thuần, B1, B2) × 3 lượt sinh = 540 câu-lượt.
- Rút **100 câu trả lời**: mỗi nhánh 25 câu, phân tầng theo kiểu câu trả lời (`answer_kind.py`): tối đa 8 "từ chối thuần",
  8 "từ chối rồi suy đoán", 9 "khẳng định"; lớp nào thiếu thì bù từ lớp còn lại theo cùng thứ tự ngẫu nhiên.
- Seed: `random.Random(16092026)`. Sinh bằng `reproduce/null_audit/make_judge_audit_sheet.py`.
- Phiếu xáo thứ tự; **không** ghi nhánh, lượt, kiểu câu trả lời hay phán quyết của Gemini.

## Sửa đăng ký, 16/09/2026 — rút phiếu xuống 40 dòng

**Chốt trước khi có bất kỳ nhãn nào của người** (phiếu 100 dòng chưa ai chấm), nên đây là đổi thiết kế, không phải chọn số liệu.

- **Lý do 1 — công sức.** 100 dòng tốn 2–3 giờ mỗi người, quá nặng cho một nhóm 3 người đang viết bài.
- **Lý do 2 — Đ2 đã thu hẹp câu hỏi.** Chấm lại 3 lượt cho thấy mức giảm Null của B2 không phải nhiễu giám khảo
  (`logs/null_audit/d2_rejudge/ket_qua.txt`). Thứ còn phải hỏi người chỉ là **lớp câu Gemini chấm `neither`**.
- **Thiết kế mới:** 40 dòng, mỗi nhánh 10 câu, phân tầng theo **phán quyết của Gemini** thay vì theo kiểu câu trả lời:
  6 `neither`, 2 `accurate`, 2 `error`. Hai lớp sau là **đối chứng hai chiều**, để đo cả trường hợp Gemini chấm đúng mà người
  thấy sai — nếu chỉ rà lớp `neither` thì mọi hiệu chỉnh sẽ một chiều.
- Vẫn giữ seed `16092026`, vẫn mù nhánh và mù phán quyết, vẫn hai người độc lập.
- **Hệ quả bắt buộc khi báo cáo:** mẫu này **cố ý lệch** về lớp `neither`, nên κ tổng giữa người và Gemini trên mẫu **không**
  đại diện cho toàn bộ. Chỉ được báo các tỉ lệ **có điều kiện** — p(người chấm đúng | Gemini chấm X) — rồi mới nhân với phân bố
  thật của từng nhánh.
- Lệnh sinh: `make_judge_audit_sheet.py --focused`.

## Sửa đăng ký lần 2, 16/09/2026 — một người chấm thay vì hai

**Vẫn chốt trước khi có bất kỳ nhãn nào.** Nhóm quyết định giao Đ1 cho **một thành viên** (hướng dẫn:
[`docs/phan-cong/THANH_VIEN_1_CHAM_LAI_NHOM_NULL.md`](../../../docs/phan-cong/CHAM_LAI_NHOM_NULL.md)).

- **Cái mất:** không tính được Cohen's κ giữa hai người, nên không có thước đo độ tin cậy của việc gán nhãn.
- **Hệ quả bắt buộc khi báo cáo:** mọi con số của Đ1 phải ghi rõ là **cách đọc của một người**, không được trình bày như
  đồng thuận của nhóm. Đây là điểm yếu phải nêu trong Limitations.
- **Giảm nhẹ:** người chấm ghi bằng chứng vào cột `ghi_chu` cho mọi dòng mà họ thấy khó xử, để người khác kiểm lại được.
- **Nếu sau này có người thứ hai rảnh:** chấm lại **10 dòng bất kỳ** trong `sheet_B.csv` là đủ để ước lượng thô độ đồng thuận;
  script tự nhận ra và tính κ trên phần chồng lấn.

## Người gán nhãn và cách làm mù

Hai người, mỗi người một file (`sheet_A.csv`, `sheet_B.csv`), làm **độc lập**, không trao đổi trong lúc chấm và **không mở**
`key_KHONG_MO_TRUOC.csv`. Câu bất đồng do người thứ ba quyết, sau khi hai người đã nộp.

## Nhãn phải điền

| Cột | Giá trị | Nghĩa |
|---|---|---|
| `phan_quyet` | `CHINH_XAC` / `SAI` / `KHONG_BIET` | đúng rubric của `Step_2_evaluate.py`: truyền đạt đáp án vàng / khẳng định trái đáp án vàng mà không thừa nhận không chắc / nói không biết, từ chối, lạc đề |
| `noi_ro_khong_co` | `CO` / `KHONG` | câu trả lời có nói rõ rằng **chi tiết được hỏi** không có trong dữ liệu không |
| `khang_dinh_them` | `CO` / `KHONG` | ngoài lời từ chối, câu trả lời có khẳng định thêm chi tiết cụ thể nào không |
| `ghi_chu` | tự do | tuỳ chọn |

## Hai cách đọc, chốt trước

- **Đọc chặt:** kết quả là `phan_quyet` của người.
- **Đọc rộng:** `CHINH_XAC` nếu `noi_ro_khong_co = CO`; ngược lại lấy `phan_quyet`.

Hai cách đọc được suy ra bằng script, người gán nhãn không phải chọn.

## Cách tính

`reproduce/null_audit/score_judge_audit.py`: Cohen's κ giữa hai người; κ giữa người (đồng thuận) và Gemini; bảng nhầm lẫn;
trong số câu Gemini chấm `neither`, tỉ lệ người chấm `CHINH_XAC` kèm khoảng tin cậy Wilson 95%; và Null acc từng nhánh chiếu
theo hai cách đọc.

## Cách dùng kết quả

**Chỉ độ nhạy và Limitations.** Không thay số chính thức của tầng D, **không** dùng để xét lại cổng E4, không dùng để chọn
biến thể. Áp cùng lúc cho cả bốn nhánh.

## File kết quả

`logs/null_audit/d1_judge_audit/` — `sheet_A.csv`, `sheet_B.csv`, `key_KHONG_MO_TRUOC.csv`, và báo cáo `ket_qua.txt`.
