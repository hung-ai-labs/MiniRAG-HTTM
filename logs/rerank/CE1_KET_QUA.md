# CE1 — kết quả offline: cross-encoder tiền huấn luyện xếp lại ứng viên B2

> 20/09/2026 · Đăng ký trước: [`reproduce/rerank/preregistration/CE1_cross_encoder_pretrained.md`](../../reproduce/rerank/preregistration/CE1_cross_encoder_pretrained.md)
> (commit `7fe9325`, **trước** khi chấm bất kỳ cặp nào). Chỉ offline: 0 lời gọi sinh, 0 lời gọi giám khảo, `minirag/` không đổi.
> Evidence và đáp án vàng chỉ dùng để đánh giá.

## Phase 0 — B2 xác nhận lại

`context_sha256` của bản dựng lại offline trùng **198/198** với B2 đông lạnh (`logs/screening/b2/answers.jsonl`); dựng lại
A1 từ `ranked_ids` khớp `chunk_ids` **200/200**. Ứng viên trung vị 48/câu. Dev: Single 159 · Multi 21 · Null 20.

## Phase 1 — model (ghim trước khi thấy kết quả)

`cross-encoder/ms-marco-MiniLM-L6-v2` @ `233902d25c440f23af6f7d6e94d2946bac0bee0a` · BERT 6 lớp, 22,7 M tham số ·
BertTokenizer, max 512 · MaxP (cửa sổ `512−len(q)−3`, bước = cửa sổ/2, lấy max) · CPU float32, lô 32 · điểm logit thô,
hoà điểm giữ thứ tự RRF · xếp lại **đúng** tập ứng viên B2.

**Chi phí thật:** 18.723 cửa sổ, 302 s = **1.511 ms/câu** trên CPU (62 cửa sổ/s). Không thêm lời gọi LLM nào.

**Kiểm toàn vẹn:** tập ứng viên không đổi 200/200 · không câu nào vượt 4.000 token.

## Phase 3 — 20 ca độ sâu xếp hạng

**A 11 · B 6 · C 0 · D 3** (A = vào được context · B = lên hạng nhưng chưa vào · C = không đổi · D = tệ đi).

Ví dụ hạng chunk đáp án: 14→2, 15→2, 10→1, 22→3, 17→2, 9→2, 14→2, 24→5, 11→5 (nhóm A);
37→26, 13→7, 47→13, 48→33 (nhóm B); 11→13, 20→22, 22→26 (nhóm D).

921 chunk không phải đáp án trong 20 ca: 459 bị đẩy xuống, 423 được kéo lên.
FirstP (cắt thẳng, số đối chiếu cố định, không đổi quyết định): A = 7.

## Phase 5 — toàn dev

| | B2 → CE | |
|---|---|---|
| đủ chunk đáp án (180 câu) | 151 → **162** · 16 lên / 5 xuống · net **+11** | p = 0,027 |
| — Single | 136 → 146 · 14 lên / 4 xuống | net +10 |
| — Multi | 15 → 16 · 2 lên / 1 xuống | net +1 |
| đáp án nguyên văn trong Sources (94 câu) | 82 → **87** · 8 lên / 3 xuống · net +5 | p = 0,23 |
| hạng chunk đáp án đầu tiên | trung vị 1 → 1 · **p90 10 → 5** | |
| token Sources trung vị | 3.602 → 3.600 (−0,1%) · max 3.999 | |
| số chunk trong Sources trung vị | **8 → 6** | |
| context đổi | 196/200 câu | |
| recall ứng viên | không đổi theo định nghĩa (xếp lại cùng tập) | |

**5 câu đang tốt mất bằng chứng** (chi tiết trong `ce_eval.txt`): 2 câu chunk đáp án dài 1.200 token bị tụt nhẹ
(hạng 2→6, 3→4) trong Sources chỉ có 3 chunk; 3 câu Sources co lại (8→4, 19→16, 8→5 chunk) làm chunk đáp án ở hạng
4–10 rơi ra ngoài.

## Phase 4 — an toàn Null (20 câu)

| | |
|---|---|
| sự kiện phân biệt (`Time:`) trong Sources, trung vị | 10,5 → **7,5 (−29%)** |
| context đổi | 20/20 câu · 67 chunk mới vào · 93 chunk rời đi |
| câu Null có chunk **mới vào** khớp đủ thực thể câu hỏi | **4/20** (tín hiệu tất định tốt nhất: 15–16/20) |
| số chunk Sources trung vị | 10,5 → 7,5 |

**Ba chunk gây nhầm đã xác định (kiểm toán Null 15/09):**

| | hạng B2 → CE | trong Sources |
|---|---|---|
| L002 (`20260112_10:00`) | 8 → **3** (lên) | có → có |
| L052 (`20260214_16:00`, lời khuyên whey) | **1 → 1** (không đổi) | có → có |
| L055 (`20261113_13:00`) | 4 → **16** (xuống) | có → **rời đi** |

## Phân định: HỖ TRỢ hay chỉ LIÊN QUAN mạnh hơn?

**Kiểm giả thiết thay thế — có phải model chỉ thích chunk dài?** Pearson(độ dài, điểm CE) = **+0,099**. Nhưng chunk mới
vào Sources dài hơn chunk rời đi (trung vị 298 so với 209 token), và trong các chunk **không phải đáp án**, chunk dài
được kéo lên hơn chunk ngắn ở mọi dải hạng. **Có thiên lệch độ dài nhẹ** — phải khống chế nó trước khi kết luận.

**Khống chế cả hạng xuất phát lẫn độ dài** (mức lên hạng trung bình; chênh > 0 = model tách được chunk đáp án khỏi
chunk *cùng độ dài, cùng hạng xuất phát*):

| độ dài | hạng xuất phát | đáp án | không đáp án | chênh |
|---|---|---|---|---|
| < 400 | 1–5 | −0,5 (n=81) | −8,0 (n=455) | **+7,5** |
| < 400 | 6–15 | +2,6 (n=10) | −11,5 (n=1086) | **+14,1** |
| < 400 | 16–30 | +8,7 (n=3) | −5,9 (n=1706) | +14,6 |
| 400–799 | 1–5 | −0,1 (n=25) | −6,0 (n=110) | **+5,9** |
| 400–799 | 6–15 | +4,3 (n=7) | −5,3 (n=311) | **+9,6** |
| ≥ 800 | 1–5 | +0,4 (n=60) | −2,8 (n=269) | **+3,2** |
| ≥ 800 | 6–15 | +7,5 (n=10) | −3,0 (n=576) | **+10,5** |

Chênh dương ở **mọi ô**. Mức tăng của chunk đáp án **không** giải thích được bằng độ dài hay hạng xuất phát.

**Precision@k:**

| | B2 → CE |
|---|---|
| chunk đáp án trong top-3 (câu có evidence) | 0,715 → 0,856 (**+20%**) |
| chunk đáp án trong top-5 | 0,812 → 0,875 (+8%) |
| chunk **khớp đủ thực thể** trong top-3 (câu **Null**) | 0,233 → 0,283 (**+21%**) |
| chunk khớp đủ thực thể trong top-5 (câu Null) | 0,200 → 0,260 (**+30%**) |

**Kết luận phân định — hai mặt, phải nói cả hai:**
1. Trên **câu trả lời được**, model hành xử **giống tín hiệu hỗ trợ**: ở cùng độ dài và cùng hạng xuất phát, nó đẩy
   chunk đáp án lên hơn chunk không phải đáp án 3–15 bậc. Các tín hiệu tất định đã bị loại **không** làm được việc này.
2. Trên **câu Null**, nơi không có chunk đáp án, nó vẫn **đẩy chunk khớp chủ đề lên** (+21–30% ở top-3/5). Ở tầng xếp
   hạng, đây vẫn mang dấu của tín hiệu **liên quan mạnh hơn**.

Điều cứu cổng an toàn Null là **cơ chế khác**: context co lại (10,5 → 7,5 chunk, sự kiện phân biệt −29%), nên dù các
chunk khớp chủ đề lên hạng, số **mảnh khác nhau** để ghép thành sự kiện sai **giảm**. Đây là suy luận offline về vật
liệu đầu vào, **không** phải bằng chứng model sinh ít ảo giác hơn — chỉ QA mới trả lời được.

## Đối chiếu với luật dừng đã chốt

| # | Cổng | Kết quả | |
|---|---|---|---|
| 1 | nhóm A ≥ 10 / 20 | **11** | ĐẠT (ngưỡng "ứng viên đáng tin") |
| 2 | net giữ đủ bằng chứng > 0 | **+11** (16/5), p = 0,027 | ĐẠT |
| 3 | Multi net ≥ −1 (cả hai thước đo) | +1 và +1 | ĐẠT |
| 4 | Null: sự kiện ≤ +25% **và** ≤ 7/20 câu có chunk mới khớp đủ thực thể | **−29%** và **4/20** | ĐẠT |
| 5 | không đẩy có hệ thống chunk gây nhầm đã biết | 1 lên (L002), 1 không đổi (L052), 1 xuống và rời Sources (L055) | ĐẠT — **kèm cảnh báo, xem dưới** |
| 6 | cùng trần 4.000, token trung vị ±5% | −0,1%, max 3.999 | ĐẠT |
| 7 | không thêm lời gọi LLM | 0 | ĐẠT |
| 8 | ≤ 3 s/câu trên CPU | 1,511 s | ĐẠT |

**Cảnh báo về cổng 5.** Câu chữ đã chốt là *"không ca nào chunk gây nhầm lên hạng 1; không quá 1 ca nó tăng hạng"*.
Đọc theo nghĩa "**bị đẩy lên** hạng 1" thì đạt: L052 vốn **đã** ở hạng 1 trong B2, CE không đổi. Đọc theo nghĩa
"**kết thúc ở** hạng 1" thì trượt. Tôi viết câu này mơ hồ khi đăng ký trước và **không tự giải nghĩa theo hướng có
lợi** — ghi cả hai cách đọc để nhóm quyết. Dù đọc cách nào, CE cũng **không làm L052 xấu hơn B2**, và đã loại hẳn L055
khỏi Sources — khác hẳn S2/S7 tất định, vốn *đẩy* L052 lên hạng 1 từ chỗ thấp hơn.

## Diễn giải được phép

Mạnh nhất được viết: **"Một mô hình học tương tác câu hỏi–chunk cải thiện thứ tự bằng chứng bên trong đúng tập ứng viên
B2 và đúng ngân sách token hiện có."**

⛔ Không được viết "đã giải quyết ảo giác", "đã giải quyết Null", hay bất kỳ phát biểu nào về accuracy. Toàn bộ bảng
trên là **mức giữ bằng chứng offline**, không phải accuracy QA. Trần lý thuyết đo được trước đó là +8,2 điểm dev nếu
giữ trọn 25 câu bị cắt; ở đây giữ thêm 11 câu, nhưng mất 5 câu khác — chưa có phép đo nào nói mức này chuyển thành bao
nhiêu điểm acc.

## Giới hạn

- Dev 200, một tập, 20 ca độ sâu và 20 câu Null — mẫu nhỏ ở đúng chỗ quan trọng nhất.
- Chưa chạy sinh hay giám khảo. Không được suy ra accuracy.
- Nhãn "chunk gây nhầm" (L002/L055/L052) do một người đọc (Claude) xác định trong kiểm toán 15/09, chưa ai rà lại.
- Độ phủ thực thể là proxy tự động, không phải phán quyết ngữ nghĩa.
- Thiên lệch độ dài nhẹ có thật; đã khống chế trong bảng phân định nhưng ô n nhỏ (n = 3–10 ở vài dải).
- Chỉ một model, một revision, một chính sách cắt. Theo đăng ký trước: **không** tự động thử reranker thứ hai.
- Lỗi môi trường: `from_pretrained` nạp safetensors qua mmap làm tiến trình chết SIGBUS với torch 2.14.0 +
  transformers 5.16.1 trên máy này; cách nạp ghim đọc state dict vào RAM. Máy khác có thể không cần.
