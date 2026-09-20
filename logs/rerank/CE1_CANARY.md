# CE1 — kết quả tầng canary (100 câu cố định), mốc so sánh B2 đông lạnh

> 20/09/2026 · Đăng ký trước: [`CE2_canary.md`](../../reproduce/rerank/preregistration/CE2_canary.md) (commit `c7cf160`,
> viết trước khi chạy). Selftest 17/17 ĐẠT trước khi gọi bất kỳ lời sinh nào.
> Báo cáo máy sinh: `logs/screening/ce1/canary_report.txt`.

**Quyết định của bộ sàng lọc: `CONTINUE TO DEV200`.** Tôi **dừng ở đây chờ duyệt** — không tự chạy dev 200,
không chạm 637 hay tầng D.

## Cấu hình

| | |
|---|---|
| Biến thể | `MINIRAG_CHUNK_FUSION=vector_bm25` + `MINIRAG_RERANK=ce1` |
| Mốc | B2 đông lạnh (`--base b2`) — khác **đúng một biến** |
| Bộ câu | `canary100.csv`, cố định: Single 59 · Multi 21 · Null 20 |
| Lượt | **1 lượt sinh** (seed 20260914) × **1 lượt chấm** |
| Chi phí | 99 lời sinh trên Modal, 99 lời gọi giám khảo (so với 637 × 3: ít hơn 84,5% / 94,8%) |
| Dựng lại báo cáo | 0 lời sinh mới, 0 lời gọi giám khảo mới — quyết định không đổi |

> **Đính chính đăng ký trước.** CE2 mục 3 tôi viết "1 lượt sinh, 3 lượt chấm (như mọi tầng canary trước)". **Sai** —
> tầng canary của bộ sàng lọc này luôn là **1 lượt sinh × 1 lượt chấm**. Đây là tôi mô tả nhầm quy trình sẵn có,
> không phải cổng bị đổi. Hệ quả: canary còn ồn hơn tôi ghi, nên càng phải đọc nó như cổng sàng lọc rẻ.

## Kết quả QA

| | mốc B2 | CE1 | |
|---|---:|---:|---|
| acc | 68,00 | **71,00** | Δ +3,00 |
| err | 28,00 | 27,00 | Δ số phiếu −1 |
| neither | 4,00 | 2,00 | |
| acc điều chỉnh theo tỉ lệ dev | 72,14 | 77,87 | |

**Ghép cặp so với B2: 11 lên / 8 xuống, net +3, McNemar p = 0,648.**

| Nhóm | n | acc mốc → CE1 | lên / xuống |
|---|---:|---|---|
| Single | 59 | 76,3 → **84,7** | 8 / 3 |
| **Multi** | 21 | 57,1 → **47,6** | 2 / **4** |
| Null | 20 | 55,0 → 55,0 | 1 / 1 |

Cổng tuần tự: sau 40 câu m = 39, net +3, σ(m) = 2,85 → chạy tiếp; sau 80 câu net +4, σ = 4,06 → chạy tiếp;
sau 100 câu net +3, σ = 4,55 → **PROMOTE** (luật lô 3 chỉ đòi net ≥ 1 và mọi cổng an toàn đạt).

**Đọc con số này cho đúng.** net +3 với p = 0,648 và σ(m) = 4,55 **không** phải bằng chứng cải thiện. Theo
CLAUDE.md §3, một lượt sinh đơn lẻ mà net dưới ~18 câu thì chưa kết luận được; sàn nhiễu giữa các lượt sinh trên dev
là 1,5 điểm và canary nhỏ hơn dev nên còn ồn hơn. Canary chỉ trả lời **"không thấy hại rõ, được đi tiếp"**.

## Truy hồi và context

| | mốc B2 | CE1 |
|---|---:|---:|
| chunk đáp án giữ được | 84,1% | **87,9%** |
| câu đủ bằng chứng (80 câu có evidence) | 78,8% | **85,0%** |
| token context trung vị | 3862 | 3878 (+0,4%) |
| truy hồi trung vị | 5418 / 5513 ms | 7373 / 6899 ms |
| context đổi so với mốc | — | **99/100 câu** |

Hai cặp số truy hồi là hai lần đo tường (lượt chạy đầu và lượt dựng lại báo cáo); chênh giữa chúng là nhiễu đồng hồ
trên cùng máy, nên **phân vị đo riêng trong `ce_latency.txt` mới là số nên trích**: phần xếp lại p50 1601 ms,
p95 2388 ms trên CPU.

## Nhóm Null — ràng buộc an toàn

acc **11/20 → 11/20** (phẳng) · err **9 → 8** · neither **0 → 1**.

Chuyển dịch: `accurate→accurate` 10 · `error→error` 7 · `error→accurate` 1 · `accurate→error` 1 · `error→neither` 1.
Context đổi ở **20/20** câu.

Vật liệu đầu vào của nhóm Null: sự kiện phân biệt trong Sources trung vị **10,5 → 7,5**; số chunk **10,5 → 7,5**;
token Sources 3608 → 3500. Context Null **hẹp lại**, đúng như dự đoán offline.

**Ba chunk gây nhầm đã biết** (luật tiến cứu CE2 mục 1 — chỉ tính thoái lui nếu bị **đẩy lên** so với B2):

| | hạng B2 → CE1 | Sources | phân loại |
|---|---|---|---|
| L002 (`20260112_10:00`) | 8 → 3 | có → có | **THOÁI LUI** |
| L052 (`20260214_16:00`, whey) | 1 → 1 | có → có | TRUNG TÍNH |
| L055 (`20261113_13:00`) | 4 → 16 | có → **rời đi** | CẢI THIỆN |

**1/3 thoái lui, cổng ≤ 1 → ĐẠT, không còn dư địa.**

## ⚠ Nhóm Multi đi ngược kết quả offline — điểm phải theo dõi

Offline, Multi **giữ bằng chứng tốt hơn** (đủ bằng chứng 15 → 16 trên 21 câu canary). Nhưng acc Multi **giảm**
57,1 → 47,6 (2 lên / 4 xuống). Đọc từng câu đổi phán quyết:

| mốc → CE1 | bằng chứng | số chunk | |
|---|---|---|---|
| error → accurate | đủ → đủ | 13 → 13 | |
| **accurate → error** | **thiếu → đủ** | 21 → 18 | *có thêm bằng chứng mà vẫn sai* |
| **accurate → error** | đủ → đủ | 26 → 23 | |
| **accurate → error** | đủ → đủ | 22 → 20 | |
| **accurate → error** | đủ → đủ | 8 → 9 | |
| error → accurate | đủ → đủ | 20 → 17 | |

**Cả 4 câu tụt đều đã có đủ bằng chứng ở cả hai bên** — một câu thậm chí *được thêm* bằng chứng rồi mới sai. Nên mức
giảm Multi **không** phải lỗi giữ bằng chứng: nó là hiệu ứng của **thứ tự trình bày** lên bước sinh, ở cùng bằng
chứng. Đây là điều kiểm toán offline không đo được, vì offline chỉ đo bằng chứng có trong context hay không.

n = 21 câu, 6 câu đổi phán quyết, một lượt sinh. Cổng "Multi net ≥ −3" đạt (net −2). **Đây là điều phải nhìn kỹ nhất
ở dev 200**, không phải Null.

## Cổng an toàn

| Cổng | Kết quả |
|---|---|
| Null net ≥ −3 | ĐẠT (net 0) |
| Multi net ≥ −3 | ĐẠT (net −2) |
| số phiếu error tăng ≤ +3 | ĐẠT (−1) |
| token context trung vị ±5% | ĐẠT (+0,4%) |
| *(ghi nhận, không quyết)* truy hồi thêm ≤ 50 ms | **TRƯỢT** (+1955 ms trung vị) — đã tuyên bố trước trong CE2 |
| phần xếp lại ≤ 3000 ms/câu (cổng 8 của CE1) | ĐẠT |
| tổng truy hồi p95 ≤ 2× mốc | ĐẠT |
| ≤ 1 ca thoái lui trong 3 chunk gây nhầm | ĐẠT (1/3) |

## Ghi chú vận hành

- Một khoá Gemini trong pool bị từ chối (auth/permission), còn 17 khoá — không ảnh hưởng kết quả, nhưng nên dọn.
- Lượt canary đầu **dừng ngay ở cổng toàn vẹn**: mốc B2 chỉ lưu câu có context khác V3. Đã sửa cách dựng mốc
  (dùng `b2/answers.jsonl` khi hash khớp, ngược lại dùng V3 đông lạnh — khi context trùng thì câu trả lời của B2
  chính là của V3) và thêm assert cho câu không khớp cả hai.
- Báo cáo lượt đầu in nhầm cả từ điển phán quyết vào chỗ tên mốc: tham số `base` bị một biến cục bộ cùng tên ghi đè.
  Đã đổi tham số thành `base_name` và dựng lại báo cáo với **0 lời sinh mới, 0 lời gọi giám khảo mới** (dùng lại
  toàn bộ câu trả lời và phán quyết đã lưu), quyết định không đổi.

## Diễn giải được phép

Mạnh nhất: *"Chế độ xếp lại bằng cross-encoder vượt tầng canary: giữ bằng chứng tốt hơn, Null không xấu đi, và không
thấy hại rõ ở mức sàng lọc."* **Không** được viết bất cứ điều gì về "cải thiện accuracy", "giải quyết ảo giác" hay
"giải quyết Null". B2 vẫn là hệ thống chính thức; cờ vẫn tắt mặc định.
