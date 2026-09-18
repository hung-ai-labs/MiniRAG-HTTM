# Anh Tài (thành viên 2) — rà 65 nhãn Null (việc Đ3)

> Giao 16/09/2026 · khoảng **3 giờ** · chỉ đọc và điền, **không đụng index, không chạy QA**, nên chạy song song được với việc
> hợp nhất thực thể của bạn.
> Giao thức đã đăng ký trước: [`reproduce/null_audit/preregistration/D3_ra_nhan_65_null.md`](../../reproduce/null_audit/preregistration/D3_ra_nhan_65_null.md).
> Bối cảnh: [`../DE_XUAT_CAI_THIEN_NULL.md`](../DE_XUAT_CAI_THIEN_NULL.md).

## 1. Vì sao cần bạn

Bộ dữ liệu có 65 câu gọi là **Null**: những câu mà đáp án vàng ghi "Insufficient information" — nghĩa là corpus **không có** thông
tin để trả lời. Chưa ai kiểm xem điều đó có đúng không.

Nếu một câu thực ra **có** đáp án trong corpus mà vẫn bị gán nhãn Null, kết quả sẽ méo theo một hướng rất khó chịu:

- Cấu hình truy hồi **kém**, không tìm ra, rồi nói "không biết" → được chấm **đúng**.
- Cấu hình truy hồi **tốt**, tìm ra đáp án thật, rồi trả lời → bị chấm **sai**.

Tức là cải tiến bị phạt vì làm đúng việc của nó. Việc của bạn là đọc corpus và cho biết: với mỗi câu hỏi, dữ liệu **có** hay
**không có** đáp án.

**Tôi cố ý không nói cho bạn biết mình đã nghi câu nào**, để bạn đọc độc lập. Nếu bạn kết luận trùng thì đó là xác nhận thật; nếu
tôi nói trước thì kết luận của bạn mất giá trị.

## 2. File bạn mở

```
logs/null_audit/d3_label_audit/sheet_A.csv
```

65 dòng, mỗi dòng một câu hỏi. Mở bằng Excel, Numbers, LibreOffice hay VS Code đều được; lưu lại đúng **CSV, UTF-8**.

**Giữ nguyên** số dòng, thứ tự dòng và ba cột đầu. Chỉ điền năm cột cuối:

| Cột | Bạn điền gì |
|---|---|
| `id`, `cau_hoi`, `bang_chung` | không sửa — đọc thôi |
| `nhan` | `KHONG_CO` / `CO_DU` / `CO_MOT_PHAN` |
| `doi_mot_chi_tiet` | `CO` / `KHONG` |
| `chunk_id` | **bắt buộc** khi nhãn là `CO_DU` hoặc `CO_MOT_PHAN` |
| `trich_dan` | câu nguyên văn trong corpus chứng minh điều đó |
| `ghi_chu` | tuỳ ý, nên ghi khi bạn phân vân |

Vì chỉ có một người rà nên `chunk_id` và `trich_dan` là thứ giúp người khác kiểm lại mà không phải đọc lại từ đầu. Đừng bỏ trống.

## 3. Cột `bang_chung` có gì

Mỗi câu kèm khoảng 17 đoạn hội thoại ứng viên, chia theo bốn nhóm, mỗi dòng có dạng
`[dấu thời gian · những người nói · mã chunk] «câu» / «câu»`:

| Nhóm | Nghĩa |
|---|---|
| `MỐC THỜI GIAN` | câu hỏi có nhắc ngày tháng, đây là các đoạn đúng ngày đó — **đọc nhóm này trước** |
| `NGƯỜI` | mọi người được nhắc trong câu hỏi đều có mặt trong đoạn này |
| `BM25` | trùng nhiều từ khoá với câu hỏi |
| `ĐÃ VÀO CONTEXT` | đoạn mà hệ thống từng đưa vào context khi trả lời câu này |

Bằng chứng này chỉ để bạn đỡ mò. **Không đủ thì cứ tra thêm corpus**, ví dụ tìm từ khoá trong toàn bộ chunk:

```bash
.venv/bin/python -c "import json,re,sys; d=json.load(open('LiHua-World-qwen-modal/kv_store_text_chunks.json',encoding='utf-8')); [print(re.search(r'Time:\s*(\S+)',v['content']).group(1), '|', l.strip()[:160]) for v in d.values() for l in v['content'].split('\n') if 'raspberry' in l.lower()]"
```

Đổi `raspberry` thành từ bạn muốn tìm.

## 4. Không mở ba thứ này cho tới khi rà xong

| File | Vì sao |
|---|---|
| `logs/qwen637_*.csv`, `logs/stage_d/*.csv` | chứa câu trả lời của hệ thống và phán quyết của giám khảo |
| `logs/null_audit/verify_labels.txt`, `taxonomy.txt` | chứa đúng những câu mình đã nghi là nhãn sai |
| `docs/KET_QUA_HIEN_TAI.md`, mục nhãn Null trong `DE_XUAT_CAI_THIEN_NULL.md` | cũng nêu tên các câu đó |

Biết trước máy trả lời gì, hoặc biết trước tôi nghi câu nào, thì cả phiếu mất giá trị.

## 5. Luật gán nhãn

Với mỗi câu hỏi, tự hỏi: **đọc corpus có trả lời được câu này không?**

| Nhãn | Khi nào |
|---|---|
| `KHONG_CO` | corpus không có thông tin để trả lời — nhãn Null là đúng |
| `CO_DU` | corpus **có** câu trả lời rõ ràng — nhãn Null sai |
| `CO_MOT_PHAN` | corpus trả lời được một phần, hoặc trả lời được nhưng phải suy luận, hoặc bạn thấy tranh cãi được |

**Một quy tắc đã chốt trước, xin đọc kỹ.** Nhiều câu hỏi Null được tạo bằng cách **đổi một chi tiết** của một sự kiện có thật: hỏi
sai ngày, sai dịp, hoặc đổi một từ (ví dụ hỏi về *bánh mì* trong khi corpus nói về *bánh ngọt*). Khi gặp loại này:

- `nhan` = **`KHONG_CO`** — vì đúng câu hỏi đó thì corpus không trả lời được;
- `doi_mot_chi_tiet` = **`CO`** — để đánh dấu.

Chỉ chọn `CO_DU` khi corpus trả lời đúng **chính** câu hỏi đang hỏi.

Hai cờ này tách nhau ra để lúc phân tích còn thử được cả hai cách hiểu. Đừng gộp.

### Ví dụ minh hoạ — tình huống bịa, không lấy từ corpus

> **Sửa 18/09/2026.** Bản trước dùng bốn câu **có thật trong phiếu** làm ví dụ và kèm luôn nhãn nên vô tình chỉ đáp án cho bốn
> dòng L005, L023, L031, L054. Lỗi là của người viết hướng dẫn (Hùng). Bốn dòng đó đã được đánh dấu nhiễm trong đăng ký trước và
> báo cáo riêng. Bảng dưới đây dựng bằng nhân vật và sự việc **không** có trong corpus, chỉ để minh hoạ luật.

| Câu hỏi (bịa) | Corpus (bịa) có gì | `nhan` | `doi_mot_chi_tiet` |
|---|---|---|---|
| "Chị Lan đặt bao nhiêu mét dây điện cho xưởng?" | có tin nhắn ghi đúng số mét | `CO_DU` | `KHONG` |
| "Chị Lan uống gì trong buổi họp sáng thứ Ba?" | không đoạn nào nói buổi họp đó có đồ uống | `KHONG_CO` | `KHONG` |
| "Chị Lan khen loại **trà** mới nào?" | corpus chỉ nói chị khen loại **cà phê** mới | `KHONG_CO` | `CO` |
| "Anh Bình dặn gì **lúc bàn giao xưởng**?" | có lời dặn thật, nhưng nằm ở cuộc gọi tối hôm trước | `CO_MOT_PHAN` | `CO` |

## 6. Rà xong thì làm gì

```bash
.venv/bin/python reproduce/null_audit/score_label_audit.py | tee logs/null_audit/d3_label_audit/ket_qua.txt
```

Script in ra: bao nhiêu câu `CO_DU`, và nếu bỏ các câu đó thì điểm nhóm Null của **mọi cấu hình** thay đổi thế nào.

Rồi commit lên nhánh riêng và push:

```bash
git checkout -b tv2/d3-ra-nhan
```

```bash
git add logs/null_audit/d3_label_audit/sheet_A.csv logs/null_audit/d3_label_audit/ket_qua.txt
```

```bash
git commit -m "Đ3: rà tay 65 nhãn Null"
```

```bash
git push -u origin tv2/d3-ra-nhan
```

Xong báo Hùng một câu, đừng tự merge vào `dev`.

## 7. Quy tắc

- **Không sửa file nào khác.** Không chạy QA, không gọi API, không đụng `LiHua-World-qwen-modal/`.
- Câu nào phân vân thì cứ chọn `CO_MOT_PHAN` và ghi lý do vào `ghi_chu` — đừng cố ép về hai đầu.
- Dòng nào hỏng thì ghi vào `ghi_chu`, **đừng xoá dòng**.
- Kết quả **chỉ dùng cho phân tích độ nhạy và Limitations**, áp cùng lúc cho mọi cấu hình. Không dùng để đổi số chính thức, đổi
  cổng, hay đổi kết luận chọn B2.
- Vì chỉ một người rà nên không có κ. Bài sẽ ghi rõ đây là **cách đọc của một người**.
