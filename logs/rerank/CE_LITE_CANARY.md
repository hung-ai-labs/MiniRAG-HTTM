# CE-lite — canary chạy từ đầu, mốc B2 đông lạnh → **STOP**

> 22/09/2026 · Biến thể `ce1_lite`, N = 25 **đóng cứng trong code**, không chỉnh được từ biến môi trường.
> Chạy **từ đầu** trong `logs/screening/ce1_lite/`: **không** kế thừa một câu trả lời hay phán quyết nào của CE1.
> Selftest 15/15 ĐẠT trước khi gọi bất kỳ lời sinh nào. Cổng canary giữ nguyên.
> Báo cáo máy sinh: `logs/screening/ce1_lite/canary_report.txt`.

**Quyết định: `STOP`** — trượt cổng độ trễ đã đăng ký trước. Theo luật đã chốt: tắt chế độ thí nghiệm,
**giữ B2 đông lạnh làm hệ thống chính thức**. Không chạy dev 200, không 637, không tầng D. **Không chỉnh N.**

## ⛔ Trước hết: một phép so sánh sai của tôi trong báo cáo CE4

Báo cáo CE4 viết CE-lite đạt *"max 1708 ms, 0 câu vượt 3000"*. Số đó đo bằng **vòng lặp tách rời** — chỉ chạy
reranker, không có phần còn lại của pipeline. Nhưng số của CE1 (`max 3429`) lấy từ `rerank_ms` ghi **trong pipeline**.
**Tôi đã so hai loại đo khác nhau.**

Đo lại công bằng, cả hai **trong pipeline**, cùng cách dựng lại dev 200:

| | p50 | p95 | max | vượt 3000 |
|---|---:|---:|---:|---:|
| CE1 đầy đủ | 1830 ms | 2731 ms | 3429 ms | 5/200 |
| **CE-lite** | **970 ms** | **1725 ms** | **5246 ms** | 1/200 |
| CE-lite / CE1 | 0,53× | 0,63× | **1,53×** | |

CE-lite **giảm một nửa p50 và p95** nhưng **đuôi max xấu hơn CE1**. Đuôi bị chi phối bởi tải máy, không phải khối
lượng của reranker. Kết luận "đạt mốc vận hành" trong CE4 vì thế **sai**, đã đính chính tại chỗ trong
`CE34_KET_QUA.md` (gạch ngang, không viết lại lặng lẽ).

Lượt canary — đo trong pipeline, máy đang chạy cả sinh: **p50 931 · p95 3078 · max 7162 ms**.

## Kết quả QA (100 câu, 1 lượt sinh seed 20260914 × 1 lượt chấm, 99 lời sinh + 99 lời chấm)

| | mốc B2 | CE-lite | |
|---|---:|---:|---|
| acc | 68,00 | **72,00** | Δ +4,00 |
| err | 28,00 | 26,00 | −2 phiếu |
| neither | 4,00 | 2,00 | |

**Ghép cặp so với B2: 13 lên / 9 xuống, net +4, McNemar p = 0,523.** σ(m) = 4,55 với m = 99 câu đổi context.

| Nhóm | n | acc mốc → CE-lite | lên / xuống | CE1 để đối chiếu |
|---|---:|---|---|---|
| Single | 59 | 76,3 → **86,4** | 9 / 3 | 76,3 → 84,7 |
| **Multi** | 21 | 57,1 → **47,6** | 2 / **4** | 57,1 → 47,6 |
| Null | 20 | 55,0 → 55,0 | 2 / 2 | 55,0 → 55,0 |

**Đọc cho đúng:** net +4 với p = 0,523 và σ(m) = 4,55 **không** phải bằng chứng cải thiện. Canary một lượt sinh chỉ
trả lời "không thấy hại rõ".

## Truy hồi và context

| | mốc B2 | CE-lite |
|---|---:|---:|
| chunk đáp án giữ được | 84,1% | **88,8%** |
| câu đủ bằng chứng (80 câu có evidence) | 78,8% | **86,2%** |
| token context trung vị | 3862 | 3943 (+2,1%) |
| số chunk Sources trung vị (câu Null) | 10,5 | 7,5 |
| context đổi | — | 99/100 câu |

## Ba câu hỏi nhóm yêu cầu theo dõi

### 1. Mức tụt Multi của CE1 có còn không? **CÒN, y hệt.**

acc Multi: B2 **12/21** → CE1 **10/21** → CE-lite **10/21**. Cùng mức tụt, dù không hẳn cùng câu: CE1 và CE-lite cho
cùng phán quyết ở **15/21** câu Multi.

| mốc → CE-lite | bằng chứng | CE1 cho câu đó |
|---|---|---|
| error → accurate | đủ → đủ | accurate |
| **accurate → error** | đủ → đủ | error |
| **accurate → error** | đủ → đủ | **accurate** |
| error → accurate | đủ → đủ | error |
| **accurate → error** | đủ → đủ | error |
| **accurate → error** | thiếu → thiếu | **accurate** |

Ba trong bốn câu tụt **đã có đủ bằng chứng ở cả hai bên**; câu thứ tư thiếu bằng chứng ở cả hai bên. Lại đúng mẫu đã
thấy ở CE1: **thứ tự trình bày tác động lên bước sinh ở cùng bằng chứng**, không phải lỗi giữ bằng chứng. Cắt bớt tập
xếp lại **không** làm nhẹ hiện tượng này.

### 2. Null phẳng hay tốt lên? **Phẳng về acc, nhích nhẹ ở err.**

acc **11/20 → 11/20** · err **9 → 8** · neither **0 → 1**. Chuyển dịch: `error→accurate` 2, `accurate→error` 1,
`accurate→neither` 1, còn lại giữ nguyên. Sự kiện phân biệt trong Sources trung vị **10,5 → 7,5**.

**Ba chunk gây nhầm** (luật tiến cứu CE2 — thoái lui chỉ khi bị **đẩy lên** so với B2):

| | B2 | CE1 | CE-lite | Sources CE-lite | |
|---|---:|---:|---:|---|---|
| L002 `20260112_10:00` | 8 | 3 | **3** | có | THOÁI LUI |
| L052 `20260214_16:00` (whey) | 1 | 1 | **1** | có | TRUNG TÍNH |
| L055 `20261113_13:00` | 4 | 16 | **9** | — (rời Sources) | CẢI THIỆN |

**1/3 thoái lui, cổng ≤ 1 → đạt.**

### 3. Hai chunk gần giống thêm ở nhóm Null có thành lỗi QA không? **MỘT trong hai thì có.**

| Câu Null | chunk CE-lite thêm | B2 → CE1 → CE-lite |
|---|---|---|
| *"What song did Yuriko and Wolfgang decide to perform together after watching the drum tutorial?"* | `20260625_19:00` | accurate → accurate → **error** |
| *"What type of feedback did Li Hua provide to Chae regarding the community medical knowledge lecture…"* | `20261221_12:00` | error → error → error |

Câu thứ nhất là **đúng dạng lo ngại đã nêu trước**: CE-lite kéo thêm một chunk khớp đủ thực thể mà CE1 không kéo, và
câu đó chuyển từ `accurate` sang `error` trong khi CE1 giữ `accurate`. Câu thứ hai vốn đã sai từ B2 nên không nói được gì.

n = 1 câu, một lượt sinh — **không** đủ để kết luận nhân quả, nhưng đây đúng là kết cục mà phân tích offline đã cảnh
báo, và nó **không** được coi là trùng hợp cho qua.

## Cổng an toàn

| Cổng | Kết quả | |
|---|---|---|
| Null net ≥ −3 | net 0 | ĐẠT |
| Multi net ≥ −3 | net −2 | ĐẠT |
| số phiếu error tăng ≤ +3 | −2 | ĐẠT |
| token context trung vị ±5% | +2,1% | ĐẠT |
| ≤ 1 thoái lui trong 3 chunk gây nhầm | 1/3 | ĐẠT |
| *(ghi nhận, không quyết)* truy hồi thêm ≤ 50 ms | +1565 ms trung vị | TRƯỢT |
| **phần xếp lại ≤ 3000 ms/câu (cổng 8 của CE1)** | **max 7162 ms** | **TRƯỢT** |
| tổng truy hồi p95 ≤ 2× mốc | 15066 so với trần 19394 | ĐẠT |

Cổng tuần tự: sau 40 câu net +4 (σ 2,85) → chạy tiếp; sau 80 net +5 (σ 4,06) → chạy tiếp; sau 100 net +4 (σ 4,55) →
**STOP** vì một cổng an toàn trượt.

## Kết luận

CE-lite làm đúng phần truy hồi: giữ bằng chứng **78,8% → 86,2%** câu, và giảm **một nửa** p50/p95 của phần xếp lại.
Nhưng nó **trượt đúng cổng đã làm CE1 dừng**, và trượt nặng hơn ở đuôi (max 7162 ms trong canary, 5246 ms khi dựng lại
dev 200 — so với 3429 ms của CE1).

Nguyên nhân đuôi là **tải máy**, không phải khối lượng reranker: p50 và p95 đều giảm đúng như thiết kế. Điều đó có
nghĩa mốc `max ≤ 3000 ms` đo bằng đồng hồ tường trên máy cá nhân **không phân biệt được** "reranker chậm" với "máy bận".
Đó là một quan sát về **phép đo**, và tôi **không** dùng nó để lật quyết định: cổng đã đăng ký trước, nó trượt, nên dừng.

**Không chỉnh N. Không nới cổng. Không đổi thiết bị. Không thử reranker thứ hai. B2 đông lạnh giữ nguyên là hệ thống
chính thức, cờ vẫn tắt mặc định.**

## Giới hạn

- Canary 100 câu, một lượt sinh, một lượt chấm — theo CLAUDE.md §3 đây là cổng sàng lọc rẻ, không phải bằng chứng.
- Multi n = 21, Null n = 20; câu Null "hỏng vì chunk gần giống" là **n = 1**.
- Độ trễ đo bằng đồng hồ tường trên máy cá nhân đang chạy nhiều tiến trình; đuôi không tái lập ổn định giữa các lượt.
- Nhãn "chunk gây nhầm" do một người đọc xác định, chưa ai rà lại.
- Một model, một revision, một chính sách cắt, một thiết bị, một giá trị N.
