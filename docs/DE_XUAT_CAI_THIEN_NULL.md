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
1. Rút **40 câu trả lời** (sửa đăng ký 16/09 sau khi có kết quả Đ2, chốt trước khi ai chấm dòng nào): mỗi nhánh 10 câu, phân
   tầng theo **phán quyết của Gemini** — 6 `neither` là lớp đang tranh chấp, cộng 2 `accurate` và 2 `error` làm **đối chứng hai
   chiều**, để còn đo được cả trường hợp Gemini chấm đúng mà người thấy sai. Lệnh: `make_judge_audit_sheet.py --focused`.
   Vì mẫu cố ý lệch, chỉ được báo tỉ lệ **có điều kiện** p(người chấm đúng | Gemini chấm X), không báo κ tổng như thể đại diện.
2. **Chốt trước** quy tắc cho câu pha trộn. Hai cách đọc phải nêu rõ ngay trong giao thức:
   - *đọc chặt*: chỉ tính `accurate` khi câu trả lời không khẳng định gì thêm;
   - *đọc rộng*: tính `accurate` nếu câu trả lời có nói rõ chi tiết được hỏi không có trong dữ liệu, dù có kể thêm bối cảnh.
3. Hai người chấm **độc lập**, **mù cấu hình và mù phán quyết Gemini**. Lập bảng nhầm lẫn người × Gemini, tính Cohen's κ.
4. Ghi `logs/null_audit/d1_judge_audit/` (phiếu và báo cáo).

**Dùng kết quả thế nào.** Báo cả hai cách đọc cho **mọi cấu hình cùng lúc**, dạng phân tích độ nhạy. Không đổi số chính thức, không
đụng cổng E4 của tầng D.

**Công:** khoảng **1 giờ mỗi người** (40 dòng).

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

**Cách làm.** Phiếu `logs/null_audit/d3_label_audit/sheet_A.csv`, 65 câu, mỗi câu khoảng 17 chunk ứng viên ghép từ bốn nguồn:
mốc thời gian nhắc trong câu hỏi, người được nhắc trong câu hỏi, BM25 top-10, và chunk đã từng vào Sources. Người rà **không thấy
câu trả lời hay phán quyết của cấu hình nào**, gán `KHONG_CO` / `CO_DU` / `CO_MOT_PHAN` kèm `chunk_id` và trích dẫn. **Chốt
trước:** câu hỏi đổi một chi tiết so với corpus vẫn là `KHONG_CO`, kèm cờ `doi_mot_chi_tiet`, để bảng độ nhạy tách được hai cách
hiểu. Chấm điểm bằng `score_label_audit.py`.

**Giao cho:** thành viên 2 (Anh Tài) — [hướng dẫn](phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md). Một người rà, nên không có κ; đã ghi
vào bản sửa đăng ký.

**Công:** khoảng 3 giờ.

**Kết quả (Anh Tài rà tay, nộp 17/09, merge vào `dev` 18/09; `logs/null_audit/d3_label_audit/ket_qua.txt`).** 65/65 câu:
`KHONG_CO` 39 · `CO_MOT_PHAN` 22 · `CO_DU` 4 · `doi_mot_chi_tiet = CO` 12 câu. Bỏ 4 câu `CO_DU` thì Null acc mọi nhánh nhích lên
2–4 điểm và **thứ hạng không đổi**; bỏ thêm `CO_MOT_PHAN` (n=27 ở tầng D) thì B2 vẫn thấp nhất. Chênh B2 với B1 là −4,4 điểm khi
giữ hết, −3,8 khi bỏ `CO_DU`, −7,4 khi bỏ cả hai. **Nhãn không giải thích được khoảng cách Null của B2** — câu trả lời nằm ở rubric
(Đ6).

**⚠ 4 dòng nhiễm.** Bản hướng dẫn tôi phát cho người rà lấy đúng 4 câu trong phiếu (`L005`, `L023`, `L031`, `L054`) làm "ví dụ
không nằm trong phiếu" và nêu luôn nhãn mong đợi; cả 4 dòng người rà điền trùng khớp gợi ý, nên không tính là phán đoán độc lập.
Lỗi của người viết hướng dẫn. Đã ghi vào đăng ký trước, đã sửa ví dụ trong cả hai bản hướng dẫn, và `score_label_audit.py` in thêm
một cột đã bỏ 4 dòng đó — bỏ rồi kết luận **không đổi** (B2 72,0 · B1 78,7 · vector thuần 82,7). Mọi chỗ trích dẫn Đ3 phải kèm cột này.

### Đ4 — Xác nhận cổng Null của H2 bằng 3 seed mới · ⛔ NHÓM QUYẾT ĐỊNH KHÔNG CHẠY (16/09/2026)

**Vì sao.** H2 trượt E4 đúng 0,33 câu, và mức giảm dồn vào một lượt (−4, −7, +1). Với 45 câu và một lượt chấm, đây có thể là nhiễu
lượt sinh.

**Cách làm.** Thêm 3 seed cho B2 và vector thuần, **đăng ký trước** rằng quyết định dựa trên Null net trung bình của cả 6 lượt và
ngưỡng vẫn là −3. Khoảng 4,5 giờ GPU, không tốn API trả phí.

**Điều cấm.** Không được đổi ngưỡng, không được chỉ chạy thêm seed cho B2 mà bỏ vector thuần, và không được dừng giữa chừng khi
thấy số có lợi.

**Cập nhật 16/09 sau khi có Đ2 — khuyến nghị: KHÔNG chạy Đ4.** Lý do Đ4 tồn tại là nghi mức trượt cổng Null đến từ một lượt sinh
xấu (Null net 1 lượt chấm: −4, −7, **+1**). Chấm 3 lượt thì lượt dương duy nhất đó thành **−1**, và trung bình đi từ −3,33 xuống
−4,67 — tức xa ngưỡng hơn, không xích lại. Thêm 3 seed nhiều khả năng chỉ xác nhận H2 vẫn BORDERLINE, mà tốn khoảng 9 giờ GPU và
credit Modal. Ngoài ra, việc chạy thêm seed chỉ cho đúng phép so vừa trượt cổng — dù có đăng ký trước — vẫn dễ bị phản biện là
"chạy tới khi đạt". Nếu sau này vẫn muốn làm, điều kiện nên là: Đ1 cho thấy cách đọc rubric đổi chiều kết luận, hoặc nhóm cần H2
làm kết quả chính chứ không phải H3.

### Đ5 — Các kiểm tra phụ

| Id | Việc | Cách làm | Công |
|---|---|---|---|
| K2 | Rà mẫu đáp án vàng của câu có đáp án | 60 câu có seed (40 Single, 20 Multi), đọc chunk theo Evidence, gán `ĐÚNG` / `SAI` / `THIẾU` / `MƠ HỒ` | 3 giờ |
| K3 | Kiểm nhãn Single / Multi | dùng số chunk vàng trong `logs/diag_path2chunk.jsonl`, đọc tay các trường hợp lệch | 1 giờ |
| K4 | Ghi nhận vấn đề dữ liệu đã biết | 637 dòng / 635 câu phân biệt (đã xử lý bằng trọng số 1/2); mọi câu Null dùng chung một đáp án vàng | — |
| G2 | Giám khảo dễ dãi với chi tiết sai | 60 câu `accurate` của V3 và B2 trên dev; pilot V5e thấy 13/40 | 3 giờ |
| G3 | Giám khảo thứ hai | chấm lại một mẫu cố định bằng model khác — **gọi API trả phí, phải hỏi nhóm** ([`CLAUDE.md`](../CLAUDE.md) §1) | tuỳ mẫu |

### Đ6 — Chấm lại toàn bộ nhóm Null bằng rubric làm rõ · ✅ XONG 18/09/2026 (độ nhạy)

**Vì sao.** Đ1 chỉ là 40 câu và con số cho toàn bộ chỉ là **phép chiếu**. Đ6 đo trực tiếp: thêm vào prompt giám khảo đúng một đoạn
nói rõ cách chấm câu trả lời pha trộn khi đáp án vàng là "Insufficient information", kiểm đoạn đó với người, rồi chấm lại mọi câu
Null của cả bốn nhánh.

**Cách làm** (đăng ký trước `reproduce/null_audit/preregistration/D6_cham_lai_null_rubric_lam_ro.md`, khoá prompt bằng sha256):
1. **Cổng kiểm** trên 40 dòng Đ1 — **QUA**: khớp người 38/40 (rubric gốc 15/40), 23/24 dòng tranh chấp, bắt được 7/7 câu người
   chấm `SAI`. `logs/null_audit/d6_clarified/gate_ket_qua.txt`.
2. **Chấm toàn bộ:** 45 câu Null ngoài dev × 4 nhánh × 3 lượt sinh = 540 câu trả lời × 3 lượt chấm = 1.620 phiếu, đủ cả, 0 lượt
   hỏng, 529/540 câu ba lượt trùng nhau. `logs/null_audit/d6_clarified/full_ket_qua.txt`.

**Kết quả.**

| Nhánh | Rubric gốc (chính thức) acc / err / neither | Rubric làm rõ acc / err / neither |
|---|---:|---:|
| V3 | 63,0 / 24,4 / 12,6 | 74,8 / 25,2 / 0,0 |
| Vector thuần | 65,2 / 27,4 / 7,4 | 74,1 / 25,9 / 0,0 |
| B1 | 62,2 / 25,2 / 12,6 | 73,3 / 26,7 / 0,0 |
| **B2** | **57,8** / 23,0 / 19,3 | **74,1** / 25,9 / 0,0 |

| Null net, trung bình 3 cặp lượt | Rubric gốc | Rubric làm rõ |
|---|---:|---:|
| H1 = B1 với V3 | −0,33 | −0,67 |
| H2 = B2 với vector thuần | **−3,33** | **+0,00** |
| H3 = B2 với B1 | −2,00 | +0,33 |

**Đọc thế nào.**
- **Khoảng cách Null của B2 so với các nhánh RRF khác là do rubric, không phải do hệ thống** (so với baseline gốc thì không — xem đoạn bổ sung bên dưới). Khi rubric nói rõ cách chấm câu pha trộn, bốn nhánh nằm trong 1,5
  điểm (dưới 2 câu mỗi lượt) — không có thứ hạng. B2 vẫn không bịa nhiều hơn: 26 câu-lượt `neither` của B2 chuyển thành 23
  `accurate` và 3 `error`.
- Rubric làm rõ gần như bỏ hẳn nhãn `neither` cho câu Null (1/1.620 phiếu), nên cột `neither` của hai rubric **không so được** —
  so acc và err.
- Lời từ chối thuần không bị chấm `error` lần nào (175/175 `accurate`): rubric không biến "không biết" thành sai.
- **Phép chiếu Đ1 cao hơn thực đo 2,8–4,3 điểm**, và thứ hạng chiếu (B2 cao nhất) không giữ. Phép chiếu lấy p(đúng | Gemini chấm
  `error`) = 12% từ 8 dòng của một người; thực đo chỉ 7%, cộng thêm 8/335 câu `accurate` đổi sang `error`. Bài học: con số chiếu từ
  mẫu nhỏ không thay được phép đo.

**Bổ sung 18/09 — chấm lại cả baseline (sửa đăng ký, push trước khi gọi).** Baseline MiniRAG gốc theo rubric làm rõ: **86,7 / 13,3 / 0,0** (rubric gốc 71,1 / 15,6 / 13,3). Rubric làm rõ xoá khoảng cách **giữa các nhánh RRF**, nhưng **không** xoá khoảng cách với baseline: B2 74,1 so với 86,7, Null net B2 − baseline trung bình **−5,67 câu mỗi lượt** (rubric gốc −6,00). Phần chênh này là của hệ thống: err nhóm Null của baseline 13,3 so với 25–27 ở mọi nhánh RRF. Đưa chunk vector vào context làm Qwen khẳng định sai trên câu Null nhiều hơn. `logs/null_audit/d6_clarified/baseline_ket_qua.txt`.

**Dùng kết quả thế nào — ĐỘ NHẠY.** Không thay số chính thức tầng D, **không** xét lại E4 hay phân loại H1–H3 (H2 vẫn BORDERLINE),
không dùng để chọn biến thể. Trong bài luôn đặt số của hai rubric cạnh nhau.

**Giới hạn.** Rubric được hiệu chuẩn trên nhãn của **một** người (40 dòng, cũng nằm trong 540 câu đã chấm); cùng một giám khảo
Gemini; 45 câu mỗi nhánh nên không kiểm định ý nghĩa.

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
| 1 | **Đ1** — người chấm lại 40 câu Null, dồn vào lớp `neither` | 1 giờ, **giao thành viên 1** | không | [hướng dẫn](phan-cong/CHAM_LAI_NHOM_NULL.md) |
| 2 | **Đ2** — chấm lại nhóm Null 3 lượt, độ nhạy | 30 phút máy | không (Gemini free tier) | khai báo trước |
| 3 | **Đ3** — rà tay 65 nhãn Null | 3 giờ, **giao Anh Tài** | không | [hướng dẫn](phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md) |
| ⛔ | ~~**Đ4** — xác nhận cổng Null của H2~~ | — | — | **bỏ 16/09**, lý do ở mục 4 |
| 5 | **Đ5** — K2, K3, G2, G3 | 1–3 giờ mỗi việc | G3 **có** | — |
| 6 | **Đ6** — chấm lại toàn bộ Null bằng rubric làm rõ | 30 phút máy | không (Gemini free tier) | Đ1 (nhãn người làm cổng) |

**Cập nhật 18/09:** Đ2 xong (16/09), Đ1 xong (17/09, Djicz), Đ6 xong (18/09). Đ3 xong (17/09, Anh Tài) và đã merge 18/09, kèm khai báo 4 dòng nhiễm do bản hướng dẫn. Đ4 bỏ.

**Cách viết vào bài (dự thảo, cập nhật 18/09 sau Đ6):** *"Cấu hình tốt nhất (B2) tăng accuracy tổng so với mốc, nhưng nhóm Null
theo rubric gốc giảm (57,8 so với 65,2 của vector thuần trên 45 câu ngoài dev). Mức giảm không phải do bịa thêm — tỉ lệ `error` nhóm
Null của B2 thấp nhất — mà do câu trả lời pha trộn: nêu sự kiện gần giống rồi nói chi tiết được hỏi không có trong dữ liệu, loại câu
mà rubric gốc không quy định. Một người chấm 40 câu thấy 22/24 câu bị chấm `neither` là đúng. Chấm lại toàn bộ nhóm Null bằng một
rubric nói rõ quy tắc này (khớp người 38/40, rubric gốc 15/40), bốn cấu hình nằm trong 1,5 điểm (73,3–74,8) và chênh Null giữa B2 và
vector thuần là 0. Chúng tôi báo số chính thức theo rubric gốc và đặt kết quả này cạnh đó như phân tích độ nhạy."*

## 8. Trạng thái triển khai (cập nhật 18/09/2026)

Giao thức của Đ1, Đ2, Đ3 đã được **đăng ký trước** và commit trong `reproduce/null_audit/preregistration/` trước khi đọc bất kỳ
nhãn nào. Phiếu và script đã sẵn sàng; phần còn lại là việc của người chấm.

| Việc | Đã có trong repo | Người phải làm gì |
|---|---|---|
| **Đ1** | `preregistration/D1_nguoi_cham_lai_null.md` (kèm hai bản sửa 16/09: 40 dòng, một người chấm); `make_judge_audit_sheet.py`, `score_judge_audit.py` | **xong 17/09** (Djicz) — 22/24 câu Gemini chấm `neither` được người chấm đúng (92%, KTC 74–98%); `logs/null_audit/d1_judge_audit/ket_qua.txt` |
| **Đ2** | `preregistration/D2_cham_lai_null_3_luot.md`; `rejudge_null_stage_d.py` | **xong 16/09** — mức giảm Null không phải nhiễu giám khảo (mục 4); `logs/null_audit/d2_rejudge/ket_qua.txt` |
| **Đ3** | `preregistration/D3_ra_nhan_65_null.md` (kèm bản sửa 16/09); phiếu 65 câu, mỗi câu ~17 chunk từ 4 nguồn, `logs/null_audit/d3_label_audit/sheet_A.csv`; `make_label_audit_sheet.py`, `score_label_audit.py` | **xong 17/09** (Anh Tài, rà tay), merge 18/09 — `CO_DU` 4 · `CO_MOT_PHAN` 22; nhãn không giải thích được khoảng cách Null của B2; ⚠ 4 dòng nhiễm do hướng dẫn, đã khai báo |
| **Đ6** | `preregistration/D6_cham_lai_null_rubric_lam_ro.md`; `rejudge_null_clarified.py`, `run_d6_full.sh` | **xong 18/09** — cổng QUA 38/40; Null bốn nhánh 73,3–74,8, Null net H2 +0,00 (mục 4) |
| **Đ4** | ⛔ **bỏ** (16/09) | không chạy: sau Đ2, lượt Null net dương duy nhất thành −1 và trung bình xa ngưỡng hơn. H2 giữ nguyên BORDERLINE |

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
