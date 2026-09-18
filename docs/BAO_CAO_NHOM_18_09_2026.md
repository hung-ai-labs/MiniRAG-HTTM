# Báo cáo tổng hợp cho nhóm — 18/09/2026

> Chốt trạng thái sau tầng D và chuỗi kiểm nhóm Null. Số chi tiết: [`KET_QUA_HIEN_TAI.md`](KET_QUA_HIEN_TAI.md).
> Lịch sử thí nghiệm và đăng ký trước: [`../ROADMAP.md`](../ROADMAP.md). Quy tắc bắt buộc: [`../CLAUDE.md`](../CLAUDE.md).

## 1. Đọc nhanh

- **Chốt cấu hình B2 = RRF(vector, BM25)** (16/09). Trên 435 câu ngoài dev, trung bình 3 lượt sinh: acc **73,95** so với B1 67,36,
  vector thuần 65,82, V3 60,92.
- **H2 vẫn là BORDERLINE** vì vướng cổng Null E4. Đây là sai lệch so với đăng ký trước, nhóm đã khai báo, **không nới cổng**.
- Điểm yếu duy nhất của B2 là nhóm Null (57,8 so với 65,2 của vector thuần theo rubric gốc). Bốn việc kiểm đã truy ra nguyên nhân:
  **cách chấm, không phải hệ thống**.
- **Đ6 (18/09)** chấm lại toàn bộ nhóm Null bằng rubric nói rõ cách xử lý câu trả lời pha trộn: bốn cấu hình nằm trong 1,5 điểm
  (73,3–74,8) và chênh Null giữa B2 với vector thuần về 0. Đây là **phân tích độ nhạy**, không thay số chính thức.
- **Hai việc của thành viên đều cho kết quả phủ định:** E1 hợp nhất thực thể (Tài) không cải thiện truy hồi bằng chứng; P1 cắt tỉa
  đường đi (Huy Đức) nhanh hơn 82% nhưng thiếu 0,5 điểm so với cổng chất lượng, P2 không dịch chuyển chỉ số nào. Cả hai đã merge,
  không đổi hành vi mặc định của hệ thống.
- Có một lỗi quy trình phải khai báo trong bài: bản hướng dẫn việc Đ3 lỡ nêu sẵn nhãn của 4 câu trong phiếu. Đã ghi nhận, đã sửa,
  kết luận không đổi.

## 2. Tầng D — cơ sở để chốt B2

435 câu ngoài dev × 3 lượt sinh (seed 101/202/303), 1 lượt chấm mỗi lượt sinh, kiểm định hoán vị đổi dấu + hiệu chỉnh Holm.
Báo cáo gốc: `logs/stage_d/stage_d_report.txt`.

| Nhánh | acc (3 lượt) | err | neither | acc/(acc+err) | Single (347) | Multi (43) | Null (45) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V3 = RRF(đồ thị, vector) | 60,92 ± 2,18 | 24,37 | 14,71 | 71,43 | 64,27 | 31,78 | 62,96 |
| Vector thuần | 65,82 ± 0,48 | 24,06 | 10,11 | 73,24 | 69,93 | 33,33 | 65,19 |
| B1 = RRF(đồ thị, vector, BM25) | 67,36 ± 1,22 | 22,76 | 9,89 | 74,75 | 71,57 | 38,76 | 62,22 |
| **B2 = RRF(vector, BM25)** | **73,95 ± 2,21** | **19,54** | 6,51 | **79,09** | **80,79** | 35,66 | 57,78 |

| | So sánh | Hiệu | Holm p | E3 | E4 (Null) | E5 | Phân loại |
|---|---|---:|---:|---|---|---|---|
| H1 | B1 với V3 | +6,51 | 0,00008 | ĐẠT | ĐẠT (net −0,33) | ĐẠT | **ROBUST POSITIVE** |
| H2 | B2 với vector thuần | +8,12 | 0,00006 | ĐẠT | **TRƯỢT** (net −3,33 < −3) | ĐẠT | **BORDERLINE** |
| H3 | B2 với B1 | +6,59 | 0,00017 | ĐẠT | ĐẠT (net −2,00) | ĐẠT | **ROBUST POSITIVE** |

**Vì sao B2 hơn B1 dù B1 có thêm đồ thị.** Xếp hạng của đồ thị chiếm 1/3 số phiếu trong RRF nhưng danh sách nhiễu. Ở tầng A,
recall@30 của B1 là 97,6% so với 96,1% của B2, nhưng chunk chứa đáp án **còn sống sau bước cắt A1@4000** chỉ 75,4% ở B1 so với
86,0% ở B2. B2 vẫn duyệt đồ thị và vẫn giữ bảng thực thể 65 token trong context — chỉ khác ở cách xếp hạng chunk.

## 3. Nhóm Null — chuỗi bốn việc kiểm

**Vấn đề.** Với câu Null, đáp án vàng là "Insufficient information". Rubric gốc có ba nhãn nhưng **không quy định** câu trả lời pha
trộn: nêu sự kiện gần giống rồi mới nói chi tiết được hỏi không có trong dữ liệu. B2 sinh ra loại câu này nhiều nhất.

| Việc | Ai làm | Kết luận |
|---|---|---|
| **Đ2** — chấm lại 3 lượt bằng rubric gốc | máy, 16/09 | **Không phải nhiễu giám khảo.** Chấm kỹ hơn thì B2 còn xuống 55,6 |
| **Đ1** — người chấm 40 câu | Djicz, 17/09 | 22/24 câu giám khảo chấm `neither` thì **người chấm là đúng** (92%, KTC 74–98%) |
| **Đ3** — rà tay 65 nhãn Null | Tài, 17/09 | `KHONG_CO` 39 · `CO_MOT_PHAN` 22 · `CO_DU` 4. **Nhãn không giải thích được** khoảng cách Null của B2 |
| **Đ6** — chấm lại toàn bộ bằng rubric làm rõ | máy, 18/09 | Khoảng cách **là do rubric**. Bốn nhánh hoà nhau |
| ~~Đ4~~ — thêm 3 seed cho H2 | — | **bỏ** 16/09: sau Đ2 gần như chỉ xác nhận BORDERLINE, tốn ~9 giờ GPU, dễ bị phản biện "chạy tới khi đạt" |

### Đ6 — kết quả

Prompt giám khảo = prompt gốc **cộng đúng một đoạn** nói rõ: với đáp án vàng "Insufficient information", câu trả lời nói rõ chi tiết
được hỏi không có trong dữ liệu thì chấm `accurate` dù có kể thêm bối cảnh; chỉ chấm `error` khi nó khẳng định chi tiết còn thiếu
như một sự thật. Prompt khoá bằng sha256, đăng ký trước khi gọi lệnh đầu tiên.

Trước khi chấm toàn bộ, rubric phải qua **cổng kiểm** với nhãn người: khớp 38/40 (rubric gốc chỉ khớp 15/40), 23/24 dòng tranh chấp,
và bắt được 7/7 câu người chấm là sai — điều kiện cuối để chắc rubric không biến thành "cái gì cũng đúng".

Sau đó chấm 45 câu Null × 4 nhánh × 3 lượt sinh × 3 lượt chấm = **1.620 phiếu**, đủ cả, 529/540 câu ba lượt trùng nhau.

| Nhánh | Null acc / err / neither — rubric gốc | rubric làm rõ |
|---|---:|---:|
| V3 | 63,0 / 24,4 / 12,6 | 74,8 / 25,2 / 0,0 |
| Vector thuần | 65,2 / 27,4 / 7,4 | 74,1 / 25,9 / 0,0 |
| B1 | 62,2 / 25,2 / 12,6 | 73,3 / 26,7 / 0,0 |
| **B2** | **57,8** / 23,0 / 19,3 | **74,1** / 25,9 / 0,0 |

| Null net, trung bình 3 cặp lượt | rubric gốc | rubric làm rõ |
|---|---:|---:|
| H1 = B1 với V3 | −0,33 | −0,67 |
| H2 = B2 với vector thuần | **−3,33** | **+0,00** |
| H3 = B2 với B1 | −2,00 | +0,33 |

**Đọc thế nào.** B2 không bịa nhiều hơn — tỉ lệ `error` nhóm Null của nó thấp nhất trong bốn nhánh ngay từ rubric gốc. 26 câu-lượt
`neither` của B2 chuyển thành 23 `accurate` và 3 `error`. Lời từ chối thuần không bị chấm sai lần nào (175/175 `accurate`), nên
rubric mới không hề dễ dãi. Rubric làm rõ gần như bỏ hẳn nhãn `neither` cho câu Null (1/1.620 phiếu), vì vậy **chỉ so cột acc và
err giữa hai rubric**, không so cột `neither`.

## 4. Điều phải ghi khi viết bài

**Bắt buộc.**
1. Số chính thức là số của **rubric gốc**. Số của Đ6 đặt **cạnh bên** như phân tích độ nhạy, luôn đi đôi.
2. **H2 giữ nguyên BORDERLINE.** Đ6 không được dùng để xét lại cổng E4 hay phân loại H1–H3 — đăng ký trước đã khoá điều này.
3. Việc chốt B2 là **sai lệch so với đăng ký trước, đã khai báo**, kèm ba ràng buộc: H2 vẫn BORDERLINE, không nới E4, Null của B2
   vào Limitations.
4. **Rubric của Đ6 được hiệu chuẩn trên nhãn của một người** (40 dòng), và 40 dòng đó cũng nằm trong 540 câu được chấm ở bước 3 —
   là hiệu chuẩn, không phải kiểm độc lập. Giám khảo vẫn là Gemini cho mọi nhánh.
5. **Đ1 và Đ3 đều chỉ có một người rà**, không tính được κ. Ghi rõ "cách đọc của một người".
6. **Nhiễm ở Đ3:** bản hướng dẫn phát cho người rà lấy 4 câu có thật trong phiếu (`L005`, `L023`, `L031`, `L054`) làm ví dụ và nêu
   luôn nhãn mong đợi. Lỗi của người viết hướng dẫn. Bốn dòng đó không tính là phán đoán độc lập; `score_label_audit.py` in thêm
   cột đã bỏ chúng — **bỏ rồi kết luận không đổi** (B2 72,0 · B1 78,7 · vector thuần 82,7).
7. 45 câu Null mỗi nhánh **không đủ để kiểm định ý nghĩa**. Chỉ báo chiều và mức, không báo p cho riêng nhóm Null.

**Không được viết.**
- "Đ6 chứng minh H2 đạt cổng" — sai, Đ6 là độ nhạy.
- "BM25 cộng thêm giá trị so với vector thuần" như thể đã chứng minh — H2 vẫn BORDERLINE.
- "Trộn giữ lợi thế của đồ thị" hay "đồ thị đóng góp vào mức tăng" — ablation vector thuần tái hiện gần hết mức tăng của V3.
- "Cải thiện Multi-hop" — Multi không lặp lại được qua các lượt sinh.
- "B2 thắng cả ở nhóm Null" — theo rubric làm rõ B2 chỉ **hoà**, không dẫn đầu.

**Hướng đã đóng, đừng mở lại:** verifier / cơ chế từ chối (A3, V5a–V5e đều phủ định); tinh chỉnh tham số đơn thuần
([`../CLAUDE.md`](../CLAUDE.md) §1b).

## 5. E1 — hợp nhất thực thể trùng tên: kết quả phủ định

Tài chạy xong 18/09, đã merge (`logs/entity_resolution/DELIVERY_NOTE.md`). Đo offline trên 180 câu dev có evidence, **không** chạy
sinh hay chấm, cùng một chính sách embedding quan hệ cho cả hai nhánh.

**Hỏi:** gộp thực thể trùng tên có giúp giữ đủ chunk bằng chứng cho nhiều câu hơn không? **Đáp: không.**

| Cổng đã đăng ký trước | Ngưỡng | Kết quả | Kết luận |
|---|---|---|---|
| Chỉ đồ thị — `graph_top30` | net ≥ +9 và p < 0,01 | net **−1** (2 lên / 3 xuống), p = 1,0 | **TRƯỢT** |
| RRF — `final_chunks` | net ≥ 0 | net **0** (2 lên / 2 xuống), p = 1,0 | đạt ở mức tối thiểu |

Cổng RRF đạt chỉ vì ngưỡng là "không xấu đi" — không có cải thiện nào.

**Cấu trúc đồ thị thì đẹp lên đúng như dự đoán:** node 1.556 → 1.538, cạnh 1.509 → 1.463, node cô lập 717 → 709, nhóm trùng tên sau
chuẩn hoá 21 → 3 (đúng 3 nhóm cố ý giữ lại). Nhưng truy hồi bằng chứng không nhúc nhích. Validity 68/68 check bắt buộc PASS.

**Cách dùng trong bài:** đây là **kết quả phủ định có giá trị** — làm sạch đồ thị không tự động cải thiện truy hồi, khớp với phát
hiện lớn hơn là đồ thị không đóng góp vào mức tăng (ablation vector thuần). Đừng trình bày như thất bại của thành viên.

**Lưu ý kho:** hai bản sao index của cặp control/treatment (`logs/entity_resolution/pair/`) không đưa vào git vì nặng ~30 MB và
dựng lại được; index `LiHua-World-qwen-entres/`, toàn bộ script và báo cáo vẫn nằm trong repo.

## 6. P1 / P2 — cắt tỉa và chấm lại đường đi: nhanh hơn nhiều, nhưng trượt cổng

Huy Đức nộp 17/09, đã merge. Hai công tắc, **mặc định tắt**: `MINIRAG_PATH_PRUNE` (P1) và `MINIRAG_PATH_SCORE` (P2). Lượt kiểm
chứng với công tắc tắt cho lại **đúng** số của bước 0, nên merge không đổi hành vi hệ thống. Đo offline trên 180 câu dev có
evidence (`logs/path/`).

| | Bước 0 (mốc) | P1 — cắt tỉa | P2 — chấm điểm có trọng số |
|---|---:|---:|---:|
| Thời gian truy hồi, trung vị | 4.109 ms | **715 ms (−82,6%)** | 3.106 ms |
| Số đường 2-hop, trung vị | 19.994 | **3.880 (−80,6%)** | 19.994 |
| Chunk đáp án trong top-30 đồ thị | 62,3% | 58,9% | 62,3% |
| Chunk đáp án còn sau cắt A1@4000 | 46,4% | 44,9% | 46,4% |
| Câu giữ đủ mọi chunk đáp án | 41,7% (75/180) | 40,6% (73/180) | 41,7% (75/180) |

**P1 — trượt cổng, nhưng là kết quả Efficiency đáng báo.** Cổng đã đăng ký trước gồm hai vế: thời gian giảm ≥ 30% (**đạt rất rộng**)
**và** chunk đáp án sau A1@4000 không giảm quá 1,0 điểm, tức ≥ 45,4% — thực đo 44,9%, **thiếu 0,5 điểm**. Multi không mất câu nào.
Nên phát biểu đúng là: *cắt 80% số đường và 82% thời gian thì mất khoảng 1,5 điểm chunk đáp án và 2 câu trong 180* — đánh đổi rõ
ràng, không phải cải thiện chất lượng.

**P2 — không dịch chuyển chỉ số nào.** Cả ba chỉ số chất lượng và cả số câu đủ đáp án (75) **trùng khít** bước 0. Trước khi ai viết
P2 vào bài, phải kiểm một việc: điểm mới có thực sự tác động tới thứ hạng cuối không, hay bị bước sau ghi đè — trùng khít đến từng
con số thường là dấu hiệu công tắc không ăn, chứ không phải hai công thức khác nhau ra cùng kết quả.

### Đo end-to-end với công tắc bật (18/09, dev 200 câu, V3, seed sinh 101)

Ba lượt QA trên Qwen2.5-3B qua Modal, chấm Gemini 1 lượt — giống giao thức tầng D. Mốc là ba lượt V3 chính thức cắt về đúng 200 câu
dev. Kết quả: `logs/path_qa/ket_qua.txt`.

| Cấu hình | Tất cả (200) | Single (159) | Multi (21) | Null (20) |
|---|---|---|---|---|
| V3 lượt 1 | 60,0 / 26,5 / 13,5 | 62,3 / 22,6 / 15,1 | 42,9 / 47,6 / 9,5 | 60,0 / 35,0 / 5,0 |
| V3 lượt 2 | 61,0 / 28,0 / 11,0 | 63,5 / 25,8 / 10,7 | 42,9 / 47,6 / 9,5 | 60,0 / 25,0 / 15,0 |
| V3 lượt 3 | 61,5 / 25,5 / 13,0 | 64,2 / 22,6 / 13,2 | 38,1 / 47,6 / 14,3 | 65,0 / 25,0 / 10,0 |
| V3 + P1 | 60,5 / 27,5 / 12,0 | 61,6 / 23,9 / 14,5 | 42,9 / 52,4 / 4,8 | 70,0 / 30,0 / 0,0 |
| V3 + P2 | 61,0 / 31,0 / 8,0 | 63,5 / 27,0 / 9,4 | 38,1 / 57,1 / 4,8 | 65,0 / 35,0 / 0,0 |
| V3 + cả hai | 59,0 / 27,5 / 13,5 | 60,4 / 23,9 / 15,7 | 42,9 / 52,4 / 4,8 | 65,0 / 30,0 / 5,0 |

*(acc / err / neither)*

**Không lượt nào đổi điểm.** McNemar so với từng lượt V3: net dao động −5 đến +2, p nhỏ nhất 0,307 — không đâu gần ý nghĩa thống kê.
Riêng ba lượt V3 cùng cấu hình đã chênh nhau 1,5 điểm ở tổng và 5,0 ở Null, nên mọi chênh lệch trong bảng đều nằm dưới sàn nhiễu.
Số câu đổi phán quyết mỗi cặp là 25–41 trong 200 — churn của bước sinh, không phải tín hiệu.

**Hai điều đáng chú ý trong hành vi.**
- **P1 xác nhận lợi ích tốc độ ngay trong lượt QA thật:** đường 2-hop trung vị 19.678 → 3.926, thời gian truy hồi trung vị
  5.239 ms → 1.035 ms (−80%). Đo trên cùng 200 câu, cùng máy, cùng endpoint.
- **Cả P1 lẫn P2 đều đẩy `neither` xuống và `err` lên** (Null `neither` về 0 ở cả hai). Hệ thống nói "không biết" ít hơn và khẳng
  định nhiều hơn, tổng điểm giữ nguyên. Đây là đổi hành vi, không phải cải thiện.

**Đính chính nhận định hôm qua về P2.** Tôi đã nghi công tắc P2 không ăn vì mọi chỉ số offline trùng khít. So context đã ghi:
P2 **có** tác dụng, nhưng chỉ đổi context ở **32/200 câu (16%)**; phần lớn câu cho ra đúng danh sách chunk cũ. Chỉ số offline không
bắt được vì nó đo tỉ lệ giữ chunk đáp án theo tổng, không đo thứ tự. Vậy P2 là cơ chế **yếu**, không phải cơ chế hỏng.

**Hai điều phải sửa trước khi trích dẫn P1.**
1. **Cơ chế thực cài khác mô tả đã đăng ký.** Đăng ký ghi "bỏ đường đi qua hub bậc > 100 nếu không chứa node thuộc
   `maybe_answer_list`"; code thực tế (`minirag/path_rerank.py`) là **giới hạn 60 đường mỗi thực thể khởi đầu, ưu tiên đường ngắn**,
   không hề dùng bậc hub. Phải viết đúng cái đã cài, hoặc cài đúng cái đã đăng ký rồi đo lại.
2. **Con số thời gian nhiễu.** Cùng một cấu hình đo hai lần cho 4.109 ms và 3.938 ms, còn P2 làm đúng khối lượng như bước 0 lại ra
   3.106 ms. Số đáng tin là **số đường** (19.994 → 3.880) vì nó tất định; muốn công bố mức giảm thời gian thì phải lặp nhiều lượt.

## 7. Ai đang làm gì

| Người | Việc | Nhánh | Trạng thái |
|---|---|---|---|
| Hùng | Sàng lọc BM25, tầng D, chuỗi kiểm Null | `dev` | Tầng D xong, Đ6 xong |
| Djicz | Đ1 — chấm tay 40 câu Null | `tv1/d1-cham-null` | **xong**, đã merge |
| Tài | Đ3 — rà 65 nhãn Null | `tv2/d3-ra-nhan` | **xong**, đã merge 18/09 |
| Huy Đức | Cắt tỉa và chấm lại đường đi (P1, P2) | `tv1/path-pruning` | **xong 17/09**, đã merge — đo end-to-end 18/09: nhanh hơn 80%, điểm không đổi |
| Tài | Hợp nhất thực thể trùng tên (E1) | `tv2/entity-resolution` | **xong 18/09** — kết quả phủ định, đã merge |

**Việc tiếp theo chưa ai nhận:** Đ5 gồm K2 (rà mẫu đáp án vàng của câu có đáp án, 3 giờ), K3 (kiểm nhãn Single/Multi, 1 giờ),
G2 (giám khảo dễ dãi với chi tiết sai, 3 giờ). G3 (giám khảo thứ hai) **gọi API trả phí — phải hỏi nhóm trước**.

**Nhắc chung.** Index `LiHua-World-qwen-modal/` không ai ghi vào. Mọi công tắc cải tiến mặc định tắt. Chạy QA 200 / 435 / 637 câu
phải được nhóm duyệt và mỗi lượt chỉ một người chạy.

## 8. Tra ở đâu

| Cần gì | File |
|---|---|
| Bảng kết quả đầy đủ | [`KET_QUA_HIEN_TAI.md`](KET_QUA_HIEN_TAI.md) |
| Chẩn đoán Null và toàn bộ đề xuất Đ1–Đ6 | [`DE_XUAT_CAI_THIEN_NULL.md`](DE_XUAT_CAI_THIEN_NULL.md) |
| Đăng ký trước từng việc kiểm | `../reproduce/null_audit/preregistration/` |
| Kết quả thô Đ6 | `../logs/null_audit/d6_clarified/full_ket_qua.txt` |
| Kết quả thô Đ1, Đ2, Đ3 | `../logs/null_audit/{d1_judge_audit,d2_rejudge,d3_label_audit}/ket_qua.txt` |
| Báo cáo tầng D | `../logs/stage_d/stage_d_report.txt` |

Chạy lại phần chấm điểm Đ3 (không gọi API):

```bash
.venv/bin/python reproduce/null_audit/score_label_audit.py
```
