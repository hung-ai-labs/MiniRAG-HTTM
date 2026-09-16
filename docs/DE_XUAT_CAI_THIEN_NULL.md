# Đề xuất cải thiện nhóm Null

> Cập nhật 16/09/2026, sau khi tầng D chạy xong và nhóm chốt **B2**. Script: `reproduce/null_audit/`; kết quả: `logs/null_audit/`.
> Kết quả tầng D: `logs/stage_d/stage_d_report.txt`. Bối cảnh: [`ROADMAP.md`](../ROADMAP.md) (Limitations của V3 mục 8, kết quả
> tầng D) và [`KET_QUA_HIEN_TAI.md`](KET_QUA_HIEN_TAI.md).
>
> Đây là **đề xuất**. Việc nào muốn chạy phải được nhóm duyệt và **đăng ký trước giao thức** (mẫu ở mục 9; giao thức đã chốt của Đ1–Đ3 nằm trong `reproduce/null_audit/preregistration/`) trước khi đọc dữ liệu.

## 1. Vấn đề còn lại sau khi chốt B2

Tầng D (435 câu ngoài dev × 3 lượt sinh) cho B2 mức tăng lớn nhất, và điểm yếu duy nhất còn lại của nó là nhóm Null:

| Nhánh | acc tổng | Null acc (45 câu) | Null err | Null neither |
|---|---:|---:|---:|---:|
| V3 (mốc) | 60,92 | 62,96 | 24,44 | 12,59 |
| Vector thuần | 65,82 | 65,19 | 27,41 | 7,41 |
| B1 = RRF(đồ thị, vector, BM25) | 67,36 | 62,22 | 25,19 | 12,59 |
| **B2 = RRF(vector, BM25)** | **73,95** | **57,78** | **22,96** | **19,26** |

Ba giả thuyết: **H1** (B1 vs V3) và **H3** (B2 vs B1) đều ROBUST POSITIVE, qua sạch E3–E5. **H2** (B2 vs vector thuần) là
BORDERLINE: hiệu +8,12 điểm, Holm p = 0,00006, dương cả 3 cặp lượt, nhưng **trượt cổng E4** vì Null net trung bình −3,33 câu,
vượt giới hạn −3. Bản thân nhóm Null không giảm có ý nghĩa (−7,41 điểm, p = 0,232), và mức giảm dồn vào một lượt (−4, −7, **+1**).

Cần biết: 5 điểm Null mà B2 mất so với B1 là **hành vi thật của model**, hay là **vùng mờ của thước đo**.

## 2. Chẩn đoán: B2 mất điểm Null ở đâu

Nguồn: `reproduce/null_audit/b2_null_stage_d.py` → `logs/null_audit/b2_null_stage_d.txt` (chạy sau khi phân tích tầng D đã xong;
chỉ mô tả, không thay số chính thức).

**B2 không bịa nhiều hơn.** `err` của nó thấp nhất trong bốn nhánh. Toàn bộ chênh lệch nằm ở `neither`:

| 45 câu Null × 3 lượt = 135 câu-lượt | B1 | B2 |
|---|---|---|
| Từ chối thuần | 41 câu-lượt → 41 `accurate` | **45 → 44 `accurate`**, 1 `neither` |
| Từ chối rồi suy đoán | 26 → 17 / 2 / 7 | 19 → 11 / 1 / 7 |
| Khẳng định | 68 → 26 `accurate` / **32 `error`** / 10 `neither` | 71 → 23 / **30** / **18 `neither`** |

B2 **từ chối thuần nhiều hơn** B1 và **sai ít hơn**. Điểm mất chạy vào nhóm `neither` của câu khẳng định.

**Vì sao.** Context của B2 có nhiều văn bản liên quan hơn, nên Qwen viết câu trả lời pha trộn: kể sự kiện gần giống trước, rồi mới
nói chi tiết được hỏi không có trong dữ liệu. Cùng câu hỏi, cùng seed 101:

- **B1:** "There isn't direct nutritional data provided for the new line of high-protein breads versus traditional white bread…"
  → `accurate`
- **B2:** "There isn't direct nutritional data provided… **but we can infer** some nutritional values based on…" → `neither`

Đáp án vàng của câu Null là "Insufficient information". Câu của B2 **có nói đúng điều đó**, chỉ là nói kèm bối cảnh.

**Đo mức độ.** Trong các câu bị chấm `neither`, đếm xem câu trả lời có nói rõ "không tìm thấy thông tin" ở bất kỳ đâu không:

| Nhánh | câu-lượt `neither` | có nói rõ | Null acc chính thức | Null acc nếu tính những câu đó là `accurate` |
|---|---:|---:|---:|---:|
| V3 | 17 | 11 (65%) | 63,0 | 71,1 |
| Vector thuần | 10 | 6 (60%) | 65,2 | 69,6 |
| B1 | 17 | 10 (59%) | 62,2 | 69,6 |
| **B2** | **26** | **15 (58%)** | **57,8** | **68,9** |

Theo cách đọc rộng, bốn nhánh nằm trong khoảng 2,2 điểm của nhau, và **chênh Null giữa B2 và vector thuần rơi từ 7,4 xuống 0,7
điểm** — tức cổng E4 trượt nằm gọn trong vùng mờ này.

**Đây là cận trên lạc quan, không phải số đã sửa:** phân loại bằng regex, và 11 câu `neither` còn lại của B2 đúng là khẳng định
sai thật. Muốn biết chắc phải có người rà — đề xuất Đ1.

**Một cách giải thích đã bị loại.** Đ2 (chấm lại 3 lượt) cho thấy mức giảm Null của B2 **không** phải do một lượt chấm duy nhất:
chấm kỹ hơn thì Null acc của B2 còn xuống 55,6 và Null net của H2 xuống −4,67. Vậy câu hỏi còn lại thuần tuý là **rubric**: câu
"không có thông tin, kèm bối cảnh" nên tính là gì. Xem mục 4, Đ1 và kết quả Đ2.

## 3. Nhãn của nhóm Null

Đọc chunk gốc (`logs/null_audit/verify_labels.txt`): **1 câu nhãn sai rõ ràng, 2 câu đáng tranh luận**.

| Câu hỏi (rút gọn) | Mức | Chunk | Bằng chứng và điểm còn tranh luận |
|---|---|---|---|
| Kích thước cửa sổ trước khi lắp rèm | **nhãn sai rõ ràng** | `20260928_10:00` | "The window is 150 cm wide and 120 cm high", đo để may rèm |
| Vị của bánh mì mới Li Hua thích ở sự kiện kỷ niệm của tiệm bánh | đáng tranh luận | `20260418_15:00` | "I really enjoyed the new pastries, especially that raspberry tart". Câu hỏi nói *bread*, corpus nói *pastries* |
| Phản hồi của Yuriko về demo website **trong buổi gặp** sáng thứ Năm ở Central Perk | đáng tranh luận | `20260309_10:00`, `20260312_16:00` | Buổi gặp thứ Năm 9 giờ có thật (12/03/2026 là thứ Năm), nhưng phản hồi nằm trong **tin nhắn 16:00 cùng ngày**, không phải tại buổi gặp |

Câu cửa sổ baseline không bị chấm sai, nhưng **mọi lượt cải tiến đều bị chấm sai**: truy hồi tốt hơn tìm ra đáp án thật và bị phạt.

**Giả thuyết cần kiểm.** Hai câu đáng tranh luận, và nhiều câu Null bị trả lời sai, trông như được tạo bằng cách **đổi một chi
tiết** của một sự kiện có thật (bread / pastries; tại buổi gặp / tin nhắn chiều; ngày 19/09 / lời khuyên tháng 2). Nếu đúng vậy thì
chúng là câu Null *đúng thiết kế*, và đó cũng chính là kiểu câu model đang hỏng.

**Độ nhạy của Null err trên 637 câu** (phán quyết đa số 3 lượt chấm; chỉ kiểm thước đo, **không thay số chính thức**):

| | Chính thức | Bỏ 1 câu rõ ràng | Bỏ cả 3 câu | Bỏ 3 câu + coi mọi câu rào đón bị chấm `error` là `neither` |
|---|---:|---:|---:|---:|
| Baseline | 16,9 | 17,2 | 14,5 | 11,3 |
| V3, trung bình 3 lượt | 24,6 | 23,4 | 21,5 | 17,7 |
| Vector thuần | 29,2 | 28,1 | 25,8 | 25,8 |
| **Chênh V3 − baseline** | **7,7** | **6,2** | **7,0** | **6,4** |

Nhãn và rào đón chỉ thu hẹp chênh 0,7–1,5 điểm, nên **không giải thích được phần lớn mức giảm của V3**. Với B2 thì khác: phần lớn
mức giảm nằm ở ranh giới `accurate` / `neither` (mục 2).

## 4. Đề xuất, theo thứ tự nên làm

### Đ1 — Người chấm lại nhóm Null, phân tầng theo kiểu câu trả lời · ưu tiên cao nhất

**Vì sao.** Đây là việc quyết định con số Null của B2 có nghĩa hay không. Rubric có ba nhãn: `accurate` = truyền đạt đáp án vàng,
`error` = khẳng định trái đáp án vàng mà không thừa nhận không chắc, `neither` = nói không biết, từ chối, hoặc lạc đề. Với câu Null,
"không có thông tin" **vừa là đáp án vàng vừa là "nói không biết"** — rubric không nói câu pha trộn phải chấm thế nào. Số liệu cho
thấy chồng lấn này không ảnh hưởng lời từ chối thuần (97–100% phiếu `accurate`), mà dồn hết vào câu pha trộn.

**Cách làm.**
1. Rút 80–100 câu trả lời cho câu Null, phân tầng theo **kiểu câu trả lời** (từ chối thuần / từ chối rồi suy đoán / khẳng định có
   rào đón / khẳng định không rào đón) × cấu hình (V3, vector thuần, B1, B2), ưu tiên lấy đủ các câu B2 bị `neither`.
2. **Chốt trước** quy tắc cho câu pha trộn. Hai cách đọc phải nêu rõ ngay trong giao thức:
   - *đọc chặt*: chỉ tính `accurate` khi câu trả lời không khẳng định gì thêm;
   - *đọc rộng*: tính `accurate` nếu câu trả lời có nói rõ chi tiết được hỏi không có trong dữ liệu, dù có kể thêm bối cảnh.
3. Hai người chấm **độc lập**, **mù cấu hình và mù phán quyết Gemini**. Lập bảng nhầm lẫn người × Gemini, tính Cohen's κ.
4. Ghi `logs/null_audit/d1_judge_audit/` (phiếu và báo cáo).

**Dùng kết quả thế nào.** Báo cả hai cách đọc cho **mọi cấu hình cùng lúc**, dạng phân tích độ nhạy. Không đổi số chính thức, không
đụng cổng E4 của tầng D.

**Công:** khoảng 2–3 giờ mỗi người.

### Đ2 — Chấm lại nhóm Null 3 lượt, làm phân tích độ nhạy

**Vì sao.** Tầng D đăng ký trước là **một** lượt chấm cho mỗi lượt sinh. Mà chỗ B2 mất điểm lại đúng là vùng giám khảo chấm kém ổn
định nhất, nên một lượt chấm là nguồn nhiễu đáng kể. Trên 637 câu, 3 lượt chấm cho sd chỉ 0,3 điểm — rẻ và đáng làm.

**Cách làm.** Chấm lại 45 câu Null × 8 lượt sinh của tầng D thêm 2 lượt nữa (khoảng 700 lời gọi, Gemini free tier), rồi báo Null
theo phán quyết đa số 3 lượt, **song song** với số chính thức một lượt.

**Ràng buộc bắt buộc.** Khai báo trước rằng đây là **độ nhạy**, không thay số chính thức và **không dùng để xét lại cổng E4**.

**Kết quả Đ2 (chạy 16/09, `logs/null_audit/d2_rejudge/ket_qua.txt`).** Chấm thêm 2 lượt cho 45 câu Null × 8 lượt sinh của tầng D
(lượt vector thuần chính thức đã có sẵn 3 lượt chấm), rồi lấy phán quyết đa số 3 lượt:

| Nhánh | Null acc 1 lượt | Null acc 3 lượt | err 1 → 3 | neither 1 → 3 |
|---|---:|---:|---|---|
| B1 | 62,2 | 60,7 | 25,2 → 26,7 | 12,6 → 12,6 |
| **B2** | **57,8** | **55,6** | 23,0 → 22,2 | 19,3 → 22,2 |
| Vector thuần | 65,2 | 65,9 | 27,4 → 26,7 | 7,4 → 7,4 |

| Null net từng cặp lượt | 1 lượt chấm | 3 lượt chấm |
|---|---|---|
| H2 = B2 với vector thuần | −4, −7, +1 · **−3,33** | −5, −8, −1 · **−4,67** |
| H3 = B2 với B1 | 0, −4, −2 · **−2,00** | −1, −4, −2 · **−2,33** |

**Kết luận của Đ2: mức giảm Null của B2 KHÔNG phải nhiễu giám khảo.** Chấm kỹ hơn thì nó còn hơi nặng thêm, và cổng E4 của H2
càng xa ngưỡng. Chỉ 4 câu-lượt có 3 phiếu chia đều (bị tính là `neither` theo luật đã khoá), nên hiệu ứng đó không đáng kể.
Số chính thức của tầng D **không đổi**; cổng E4 **không** xét lại.

Việc này thu hẹp câu hỏi còn lại: phần "58% câu `neither` có nói rõ không tìm thấy" là chuyện **rubric**, không phải chuyện nhiễu
— và chỉ Đ1 mới trả lời được.


**Công:** khoảng 30 phút máy.

### Đ3 — Rà tay toàn bộ 65 nhãn Null (K1 cũ)

**Vì sao.** Ba câu đáng ngờ mới chỉ tìm được trong số câu *bị chấm sai*. Câu Null thực ra có đáp án mà model từ chối thì vẫn được
chấm `accurate`, tức cộng điểm oan cho cấu hình ít chịu trả lời.

**Cách làm.**
1. Phiếu cho mỗi câu: 10 chunk khớp nhất theo BM25, 10 chunk theo vector, 2 câu khớp nhất trong mỗi chunk. Mở rộng từ
   `reproduce/null_audit/taxonomy.py`.
2. Hai người đọc độc lập, **không thấy câu trả lời hay phán quyết của cấu hình nào**. Nhãn: `KHÔNG CÓ` / `CÓ ĐỦ` /
   `CÓ MỘT PHẦN hoặc MƠ HỒ`, kèm chunk id và trích dẫn. **Chốt trước** cách gán câu hỏi đổi một chi tiết so với corpus: mặc định
   `KHÔNG CÓ` kèm cờ `ĐỔI MỘT CHI TIẾT`, để bảng độ nhạy tách được hai cách hiểu.
3. Cohen's κ; câu bất đồng do người thứ ba quyết. Ghi `logs/null_audit/label_audit_null.csv`.

**Công:** khoảng 3–4 giờ mỗi người.

### Đ4 — Xác nhận cổng Null của H2 bằng 3 seed mới · chỉ khi nhóm muốn nâng H2 lên ROBUST POSITIVE

**Vì sao.** H2 trượt E4 đúng 0,33 câu, và mức giảm dồn vào một lượt (−4, −7, +1). Với 45 câu và một lượt chấm, đây có thể là nhiễu
lượt sinh.

**Cách làm.** Thêm 3 seed cho B2 và vector thuần, **đăng ký trước** rằng quyết định dựa trên Null net trung bình của cả 6 lượt và
ngưỡng vẫn là −3. Khoảng 4,5 giờ GPU, không tốn API trả phí.

**Điều cấm.** Không được đổi ngưỡng, không được chỉ chạy thêm seed cho B2 mà bỏ vector thuần, và không được dừng giữa chừng khi
thấy số có lợi.

### Đ5 — Các kiểm tra phụ

| Id | Việc | Cách làm | Công |
|---|---|---|---|
| K2 | Rà mẫu đáp án vàng của câu có đáp án | 60 câu có seed (40 Single, 20 Multi), đọc chunk theo Evidence, gán `ĐÚNG` / `SAI` / `THIẾU` / `MƠ HỒ` | 3 giờ |
| K3 | Kiểm nhãn Single / Multi | dùng số chunk vàng trong `logs/diag_path2chunk.jsonl`, đọc tay các trường hợp lệch | 1 giờ |
| K4 | Ghi nhận vấn đề dữ liệu đã biết | 637 dòng / 635 câu phân biệt (đã xử lý bằng trọng số 1/2); mọi câu Null dùng chung một đáp án vàng | — |
| G2 | Giám khảo dễ dãi với chi tiết sai | 60 câu `accurate` của V3 và B2 trên dev; pilot V5e thấy 13/40 | 3 giờ |
| G3 | Giám khảo thứ hai | chấm lại một mẫu cố định bằng model khác — **gọi API trả phí, phải hỏi nhóm** ([`CLAUDE.md`](../CLAUDE.md) §1) | tuỳ mẫu |

## 5. Các hướng sửa Null đã đánh giá

| Hướng | Kết quả | Trạng thái |
|---|---|---|
| Cổng từ chối theo độ tương đồng truy hồi (A3) | AUC ≤ 0,648; mọi ngưỡng đều làm giảm acc | ⛔ đóng |
| Kiểm dấu vết câu trả lời, quan hệ đồ thị, đặc trưng MiniLM (V5a–V5c) | AUC khoảng 0,5; kiểm quan hệ chặn nhầm ≥ 63% câu đúng | ⛔ đóng |
| NLI nhỏ HHEM (V5d) | chặn nhầm 47,6% câu đúng | ⛔ đóng |
| Qwen tự kiểm chứng sau khi sinh (V5e) | chặn nhầm 92,5% câu đúng; AUC 0,448 | ⛔ đóng |
| Cổng từ chối theo độ phủ tiền đề (15/09) | AUC 0,85, nhưng net oracle = 0 ở mọi ngưỡng | ⛔ không làm |
| Cắt context khi độ phủ tiền đề thấp (15/09) | net lạc quan −2 đến +1 câu trên dev 200 (B2) | ⛔ không làm |
| Sửa prompt kiểu "hãy nói không biết" hoặc "trả lời ngắn gọn" | cải tiến giả bị cấm ([`CLAUDE.md`](../CLAUDE.md) §1b); chỉ được ghi như quan sát | ⛔ không làm |
| Fine-tune generator để biết từ chối | chưa duyệt; rủi ro rò nhãn từ bộ đánh giá | ⏸ chưa làm |
| Biểu diễn cấp sự kiện (ai, khi nào, trong cuộc trò chuyện nào) để kiểm tiền đề | giả thuyết, chưa có bằng chứng hiệu quả; cần đổi cách index; đồ thị hiện tại vô hướng, không có loại quan hệ (V5b) | 🔭 chỉ ghi Future work |

**Vì sao chưa có cách sửa nào khả thi bằng truy hồi.** Câu Null có độ phủ tiền đề thấp thì model đã tự từ chối đúng. Câu Null model
trả lời sai lại có tiền đề **gần đúng gần như trọn vẹn**: đúng người, đúng loại sự kiện, chỉ sai một chi tiết như ngày hay dịp. Mọi
tín hiệu đo độ khớp hay độ phủ đều thấy những câu này giống câu có đáp án.

## 6. Điều không được làm

- **Không nới cổng E4 sau khi đã thấy kết quả.** Luật đọc của tầng D đã khoá: Null trượt E4 → ghi vào Limitations.
- **Không mở lại hướng verifier / cổng từ chối.** Năm hướng đã thử đều phủ định.
- **Không dùng kết quả các kiểm tra ở đây để chọn biến thể**, chỉnh cổng, hay đổi số chính thức. Chỉ dùng cho độ nhạy và Limitations,
  và phải áp cùng lúc cho mọi cấu hình.
- **Không thiết kế cơ chế trên 435 câu ngoài dev.** Thiết kế chỉ trên dev.
- **Người gán nhãn luôn mù cấu hình và mù phán quyết** của giám khảo.

## 7. Thứ tự và công

| # | Việc | Công | Gọi API trả phí | Phụ thuộc |
|---|---|---|---|---|
| 1 | **Đ1** — người chấm lại câu Null theo kiểu câu trả lời | 2–3 giờ × 2 người | không | — |
| 2 | **Đ2** — chấm lại nhóm Null 3 lượt, độ nhạy | 30 phút máy | không (Gemini free tier) | khai báo trước |
| 3 | **Đ3** — rà tay 65 nhãn Null | 3–4 giờ × 2 người | không | — |
| 4 | **Đ4** — xác nhận cổng Null của H2 | 4,5 giờ GPU | không | nhóm duyệt |
| 5 | **Đ5** — K2, K3, G2, G3 | 1–3 giờ mỗi việc | G3 **có** | — |

Nếu chỉ làm được hai việc: **Đ1 rồi Đ2**. Hai việc này quyết định con số Null của B2 trong bài có tin được hay không.

**Cách viết vào bài (dự thảo):** *"Cấu hình tốt nhất (B2) tăng accuracy tổng 13,0 điểm so với mốc, nhưng nhóm Null giảm 5,2 điểm.
Phân tích lỗi cho thấy mức giảm này không phải do bịa thêm — tỉ lệ `error` của nhóm Null ở B2 là thấp nhất trong mọi cấu hình — mà do
câu trả lời chuyển sang dạng pha trộn: nêu sự kiện gần giống rồi mới nói rằng chi tiết được hỏi không có trong dữ liệu. 58% số câu bị
chấm `neither` có nói rõ điều đó; nếu tính chúng là đúng, chênh lệch Null giữa B2 và ablation vector thuần rơi từ 7,4 xuống 0,7 điểm.
Kiểm toán nhãn tìm thấy một câu Null có đáp án rõ ràng trong corpus và hai câu có nhãn đáng tranh luận."*

## 8. Trạng thái triển khai (16/09/2026)

Giao thức của Đ1, Đ2, Đ3 đã được **đăng ký trước** và commit trong `reproduce/null_audit/preregistration/` trước khi đọc bất kỳ
nhãn nào. Phiếu và script đã sẵn sàng; phần còn lại là việc của người chấm.

| Việc | Đã có trong repo | Người phải làm gì |
|---|---|---|
| **Đ1** | `preregistration/D1_nguoi_cham_lai_null.md`; phiếu 100 dòng đã mù `logs/null_audit/d1_judge_audit/sheet_A.csv` và `sheet_B.csv`; `make_judge_audit_sheet.py`, `score_judge_audit.py` | hai người điền `phan_quyet`, `noi_ro_khong_co`, `khang_dinh_them` — **không mở** `key_KHONG_MO_TRUOC.csv` — rồi chạy `score_judge_audit.py` |
| **Đ2** | `preregistration/D2_cham_lai_null_3_luot.md`; `rejudge_null_stage_d.py` | **xong 16/09** — mức giảm Null không phải nhiễu giám khảo (mục 4); `logs/null_audit/d2_rejudge/ket_qua.txt` |
| **Đ3** | `preregistration/D3_ra_nhan_65_null.md`; phiếu 65 câu kèm 10 chunk BM25 và chunk đã vào Sources, `logs/null_audit/d3_label_audit/sheet_{A,B}.csv`; `make_label_audit_sheet.py`, `score_label_audit.py` | hai người điền `nhan`, `doi_mot_chi_tiet`, `chunk_id`, `trich_dan`, rồi chạy `score_label_audit.py` |
| **Đ4** | chưa chạy | cần nhóm duyệt: 6 lượt QA (B2 và vector thuần × 3 seed mới), khoảng 9 giờ GPU, giữ nguyên ngưỡng −3 |

Mẫu phiếu dùng chung một bộ phân loại câu trả lời trong `reproduce/null_audit/answer_kind.py`, để phiếu, bảng thống kê và báo cáo
nói cùng một ngôn ngữ.

## 9. Mẫu đăng ký trước giao thức

```
Việc: Đ1 / Đ2 / Đ3 / Đ4 / K2 / K3 / G2 / G3
Ngày chốt:
Mẫu (danh sách câu, hoặc cách rút + seed):
Người gán nhãn (≥ 2) và cách làm mù:
Nhãn và định nghĩa từng nhãn (nêu rõ cách xử lý câu trả lời pha trộn):
Cách tính (κ, tỉ lệ, khoảng tin cậy):
Cách dùng kết quả (chỉ độ nhạy / Limitations — không đổi số chính thức, không đụng cổng tầng D):
File kết quả:
```
