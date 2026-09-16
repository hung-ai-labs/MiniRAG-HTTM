# Thành viên 1 — chấm lại nhóm Null (việc Đ1)

> Giao 16/09/2026 · khoảng **1 giờ** · hoàn toàn độc lập với việc cắt tỉa đường đi của bạn, không đụng file code nào.
> Giao thức đã đăng ký trước: [`reproduce/null_audit/preregistration/D1_nguoi_cham_lai_null.md`](../../reproduce/null_audit/preregistration/D1_nguoi_cham_lai_null.md).
> Bối cảnh: [`../DE_XUAT_CAI_THIEN_NULL.md`](../DE_XUAT_CAI_THIEN_NULL.md).

## 1. Vì sao cần bạn

Nhóm đã chốt **B2** sau tầng D. Điểm yếu duy nhất còn lại của nó là nhóm Null: 57,78 so với 62,22 của B1.

Đã loại trừ được hai cách giải thích:
- **Không phải model bịa nhiều hơn** — tỉ lệ trả lời sai của B2 ở nhóm Null là thấp nhất trong bốn cấu hình.
- **Không phải giám khảo chấm hên xui** — chấm lại 3 lượt (việc Đ2) cho kết quả y hệt, thậm chí hơi nặng hơn.

Còn đúng một câu hỏi, và nó là câu hỏi dành cho **người**, không phải cho máy:

> Khi model nói "dữ liệu không có chi tiết này" rồi kể thêm một sự kiện gần giống, thì đó là **trả lời đúng** hay là **né**?

Gemini đang chấm phần lớn những câu như vậy là "né". Việc của bạn là cho biết một người đọc thì thấy thế nào. Bạn chưa từng nhìn
các câu trả lời này nên bạn khách quan hơn Hùng — đó là lý do việc này giao cho bạn chứ không phải người đã chạy thí nghiệm.

## 2. File bạn mở

```
logs/null_audit/d1_judge_audit/sheet_A.csv
```

40 dòng. Mở bằng gì cũng được: Excel, Numbers, LibreOffice, hay VS Code. Lưu lại đúng **CSV, UTF-8**.

**Giữ nguyên** số dòng, thứ tự dòng và ba cột đầu. Chỉ điền bốn cột cuối:

| Cột | Bạn làm gì |
|---|---|
| `id` | không sửa |
| `cau_hoi` | đọc |
| `cau_tra_loi` | đọc |
| `phan_quyet` | điền `CHINH_XAC` / `SAI` / `KHONG_BIET` |
| `noi_ro_khong_co` | điền `CO` / `KHONG` |
| `khang_dinh_them` | điền `CO` / `KHONG` |
| `ghi_chu` | tuỳ ý — **nên ghi** ở những dòng bạn thấy khó xử |

## 3. Bốn file không được mở cho tới khi chấm xong

| File | Vì sao |
|---|---|
| `logs/null_audit/d1_judge_audit/key_KHONG_MO_TRUOC.csv` | chứa phán quyết của Gemini và tên cấu hình của từng dòng |
| `logs/stage_d/*_judged.csv` | phán quyết của Gemini cho từng câu |
| `logs/null_audit/b2_null_stage_d.txt` | thống kê đã phân loại sẵn các câu này |
| `logs/null_audit/d2_rejudge/` | phán quyết của ba lượt chấm |

Nhìn thấy máy chấm gì trước khi bạn chấm thì cả phiếu mất giá trị, và một giờ của bạn thành công cốc.

`sheet_B.csv` cứ để trống — đó là chỗ dành cho người thứ hai nếu sau này có ai rảnh chấm chồng vài dòng.

## 4. Luật chấm

Cả 40 dòng đều thuộc nhóm **Null**: với những câu hỏi này, **đáp án đúng là "dữ liệu không có thông tin để trả lời"**. Câu hỏi
thường hỏi một chi tiết nghe rất hợp lý nhưng corpus không hề ghi.

| Nhãn | Khi nào chọn |
|---|---|
| `CHINH_XAC` | câu trả lời truyền đạt được ý "không có thông tin" |
| `SAI` | câu trả lời khẳng định một đáp án cụ thể như thể dữ liệu có, mà không thừa nhận là mình không chắc |
| `KHONG_BIET` | câu trả lời né, lạc đề, hoặc không nói được gì |

**Chỗ khó — và cũng chính là lý do tồn tại của việc này.** Nhiều câu trả lời vừa nói "không có thông tin", vừa kể một sự kiện gần
giống. **Tôi cố ý không hướng dẫn bạn phải chấm loại này thế nào.** Cách bạn đọc chính là dữ liệu cần thu. Cứ chấm theo cảm nhận
trung thực của bạn về ba định nghĩa trên.

Hai cột cờ thì khác: chúng ghi **sự thật quan sát được**, không phải ý kiến, nên hãy điền độc lập với `phan_quyet`.

- `noi_ro_khong_co = CO` nếu **ở bất kỳ đâu** trong câu trả lời có nói rõ rằng chi tiết được hỏi không có trong dữ liệu.
- `khang_dinh_them = CO` nếu ngoài lời từ chối, câu trả lời còn khẳng định một chi tiết cụ thể.

### Ví dụ minh hoạ — không nằm trong phiếu của bạn

Câu hỏi: *"Li Hua ăn món gì vào bữa tối ngày 20/1/2026?"* (corpus không ghi bữa tối hôm đó)

| Câu trả lời | `phan_quyet` | `noi_ro_khong_co` | `khang_dinh_them` |
|---|---|---|---|
| "Dữ liệu không ghi Li Hua ăn gì vào tối hôm đó." | `CHINH_XAC` | `CO` | `KHONG` |
| "Li Hua ăn lẩu Tứ Xuyên với Wolfgang." | `SAI` | `KHONG` | `CO` |
| "Hôm đó trong khu phố có nhiều hoạt động thú vị." | `KHONG_BIET` | `KHONG` | `KHONG` |

Ba ví dụ này đều thuộc loại dễ. Loại khó — "không có thông tin, **nhưng** có thể suy ra là…" — bạn tự quyết.

## 5. Chấm xong thì làm gì

```bash
.venv/bin/python reproduce/null_audit/score_judge_audit.py | tee logs/null_audit/d1_judge_audit/ket_qua.txt
```

Script sẽ in ra mức khớp giữa bạn và Gemini, và tỉ lệ câu Gemini chấm "né" mà bạn chấm là đúng. Lúc này mở file key thoải mái.

Rồi commit lên nhánh riêng và push:

```bash
git checkout -b tv1/d1-cham-null
```

```bash
git add logs/null_audit/d1_judge_audit/sheet_A.csv logs/null_audit/d1_judge_audit/ket_qua.txt
```

```bash
git commit -m "Đ1: chấm tay 40 câu Null"
```

```bash
git push -u origin tv1/d1-cham-null
```

Xong thì báo Hùng một câu, đừng tự merge vào `dev`.

## 6. Quy tắc

- **Không sửa file nào khác**, không chạy QA, không gọi API. Việc này chỉ đọc và điền.
- Dòng nào hỏng (thiếu câu trả lời, cắt cụt) thì ghi vào `ghi_chu`, **đừng xoá dòng**.
- Kết quả **chỉ dùng cho phân tích độ nhạy và Limitations**. Không ai được dùng nó để đổi số chính thức của tầng D, đổi cổng E4,
  hay đổi kết luận chọn B2.
- Vì chỉ có một người chấm nên không tính được độ đồng thuận. Bài sẽ ghi rõ đây là **cách đọc của một người** — đó là hạn chế đã
  biết và đã được ghi vào đăng ký.
