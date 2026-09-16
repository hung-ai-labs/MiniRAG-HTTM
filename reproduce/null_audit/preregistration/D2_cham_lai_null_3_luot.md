# Đăng ký trước — Đ2: chấm lại nhóm Null của tầng D thêm 2 lượt

**Việc:** Đ2 (xem [`docs/DE_XUAT_CAI_THIEN_NULL.md`](../../../docs/DE_XUAT_CAI_THIEN_NULL.md) mục 4).
**Ngày chốt:** 16/09/2026 — chốt TRƯỚC khi chấm lượt nào.

## Vì sao

Tầng D đăng ký trước là **một** lượt chấm cho mỗi lượt sinh. Nhưng chỗ B2 mất điểm Null lại đúng vào vùng giám khảo chấm
kém ổn định nhất (câu trả lời pha trộn). Trên 637 câu, 3 lượt chấm cho sd chỉ 0,3 điểm, nên thêm 2 lượt là cách rẻ nhất để
biết mức giảm Null có bền qua nhiễu giám khảo không.

## Mẫu và cách chạy

- 45 câu Null ngoài dev × **8 lượt sinh của tầng D** (b1/b2/vec × seed 101/202/303) = 360 câu trả lời.
- Mỗi câu chấm thêm **2 lượt** bằng `Step_2_evaluate.py --repeats 2` (mặc định seed 13, xáo thứ tự như giao thức bài báo),
  cộng lượt chấm chính thức thành 3.
- Khoảng 720 lời gọi Gemini Flash-Lite, **free tier**.
- Chạy bằng `reproduce/null_audit/rejudge_null_stage_d.py`.

## Cách tính

Phán quyết đa số tuyệt đối trên 3 lượt chấm (chia đều → không tính là đúng, cùng luật với `analyze_stage_d.py`). Báo:
Null acc / err / neither từng nhánh, và Null net từng cặp lượt của H2 (B2 với vector thuần) và H3 (B2 với B1).

## Cách dùng kết quả

**ĐỘ NHẠY.** Không thay số chính thức trong `logs/stage_d/stage_d_report.*`; **không** dùng để xét lại cổng E4 hay đổi
phân loại H1–H3; không dùng để chọn biến thể. Nếu số mới khác số chính thức, báo cả hai cạnh nhau trong Limitations.

## File kết quả

`logs/null_audit/d2_rejudge/` — `<tag>_null.csv` (câu trả lời đã lọc), `<tag>_judged2.csv` (2 lượt chấm mới), `ket_qua.txt`.
