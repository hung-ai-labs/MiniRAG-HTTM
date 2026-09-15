# Kết quả hiện tại so với baseline

> Cập nhật 15/09/2026. Số lấy từ `logs/compare_*.txt`, `logs/v3_replicates_summary.txt` và `logs/screening/`.
> Quy tắc đọc ở [`CLAUDE.md`](../CLAUDE.md) §3: ghép từng câu, đếm câu lên / xuống, chạy McNemar; không dùng ngưỡng điểm.
> Lịch sử và bằng chứng đầy đủ nằm trong [`ROADMAP.md`](../ROADMAP.md).

## Đọc nhanh

- **Baseline cho mọi cải tiến truy hồi:** Qwen2.5-3B, 637 câu, đã vá answer-type
  (`logs/qwen637_fix_judged.csv`) — **acc 51,02 · err 27,66 · neither 21,31**.
- **Cải tiến có ý nghĩa và lặp lại được:** V3 = trộn RRF(đồ thị, vector) — **acc 60,72 ± 1,26 · err 25,28 · neither 14,00**
  (trung bình 3 lượt sinh). Cả ba lượt đều hơn baseline, p ≤ 7,4·10⁻⁵. Mặc định vẫn tắt.
- **Nhóm Null đi ngược:** acc 70,26 → 61,54, err 17,44 → 25,30. Cùng chiều ở cả 3 lượt nhưng từng lượt chưa có ý nghĩa
  (p = 0,09–0,18). Các hướng sửa A3, V5a–V5e đều phủ định — không mở lại hướng verifier / từ chối.
- **Vector thuần ngang V3** (80 lên / 61 xuống, p = 0,13): đồ thị **chưa chứng minh được đóng góp**.
- **BM25 (B1, B2) đang ở tầng sàng lọc** — chưa có số trên 637 câu (mục 5).

## 1. Bảng chính — Qwen2.5-3B, 637 câu, 3 lượt chấm Gemini

635 câu phân biệt (2 câu hỏi trùng). Mọi dòng dùng cắt Sources A1@4000 token. McNemar so với baseline, trên phán quyết đa số.

| Cấu hình | acc | err | neither | acc/(acc+err) | Single (506) | Multi (64) | Null (65) | So với baseline: lên / xuống |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **Baseline** — đã vá answer-type | **51,02 ± 0,42** | 27,66 | 21,31 | 64,84 | 51,19 | 30,21 | 70,26 | — |
| Chưa vá answer-type | 50,60 ± 0,09 | 27,72 | 21,68 | 64,61 | 50,33 | 35,42 | 67,69 | 40 / 44, p = 0,744 |
| V1 · sửa lỗi `path2chunk` | 50,81 ± 0,64 | 26,35 | 22,83 | 65,85 | 51,19 | 31,77 | 66,67 | 76 / 78, p = 0,936 |
| V2 · cắt theo vách điểm | 45,41 ± 0,18 | 23,52 | 31,08 | 65,88 | 43,94 | 23,96 | 77,95 | 64 / 100, **p = 0,006** ⛔ |
| V3 · trộn RRF — lượt 1 | 61,94 ± 0,45 | 23,78 | 14,28 | 72,26 | 64,36 | 43,75 | 61,03 | 117 / 49, p = 1,3·10⁻⁷ |
| V3 · lượt 2 | 59,42 ± 0,18 | 26,46 | 14,12 | 69,19 | 62,65 | 32,29 | 61,03 | 110 / 58, p = 7,4·10⁻⁵ |
| V3 · lượt 3 | 60,79 ± 0,27 | 25,62 | 13,60 | 70,35 | 64,43 | 30,21 | 62,56 | 110 / 49, p = 1,5·10⁻⁶ |
| **V3 · trung bình 3 lượt sinh** | **60,72 ± 1,26** | **25,28** | **14,00** | **70,60** | 63,81 | 35,42 | 61,54 | cả 3 lượt p ≤ 7,4·10⁻⁵ |
| V4 · trộn RRF @2000 token | 52,28 ± 0,16 | 27,19 | 20,52 | 65,79 | 53,36 | 27,08 | 68,72 | 80 / 75, p = 0,748 — so với V3: 37 / 100, p = 7,0·10⁻⁸ ⛔ |
| Vector thuần (ablation V3) | 65,20 ± 0,42 | 25,04 | 9,76 | 72,25 | 68,25 | 43,75 | 62,56 | 152 / 65, p = 3,3·10⁻⁹ — so với V3: 80 / 61, p = 0,13 |
| *Bài báo — Qwen2.5-3B (GPT chấm)* | *48,75* | *26,02* | *25,23* | *65,20* | | | | tham chiếu, không phải đối chứng |

**Dấu ±.** Dòng "V3 · trung bình" là sd giữa 3 lượt **sinh**. Mọi dòng khác mới có một lượt sinh, ± chỉ là nhiễu **giám khảo**
(3 lượt chấm cùng một file). Nhiễu sinh lớn hơn nhiều: hai lượt V3 cùng cấu hình lệch nhau tới 2,52 điểm.

### Chênh lệch so với baseline (điểm %)

| Cấu hình | Δ acc | Δ err | Δ neither | Δ Single | Δ Multi | Δ Null acc | Δ Null err |
|---|---:|---:|---:|---:|---:|---:|---:|
| V3 · trung bình 3 lượt | **+9,69** | −2,38 | −7,31 | +12,63 | +5,21 | **−8,72** | **+7,86** |
| Vector thuần | +14,18 | −2,62 | −11,55 | +17,06 | +13,54 | −7,70 | +13,33 |
| V4 · RRF @2000 | +1,26 | −0,47 | −0,79 | +2,17 | −3,13 | −1,54 | +5,12 |

Vector thuần mới có **một** lượt sinh; nó cao hơn trung bình V3 4,48 điểm nhưng phép so đăng ký trước cho ra "ngang nhau".
Không được viết "vector thuần tốt hơn V3" khi chưa lặp lượt. Multi của V3 không lặp lại được (43,75 / 32,29 / 30,21) —
không được viết "cải thiện Multi-hop".

## 2. Nhóm Null (65 câu) — acc / err / neither

| Cấu hình | acc | err | neither | So với baseline: lên / xuống |
|---|---:|---:|---:|---|
| **Baseline** | **70,26** | **17,44** | 12,31 | — |
| V1 · sửa `path2chunk` | 66,67 | 23,08 | 10,26 | 3 / 6, p = 0,508 |
| V2 · cắt theo vách | 77,95 | 11,28 | 10,77 | 7 / 4, p = 0,549 |
| V3 · lượt 1 | 61,03 | 27,69 | 11,28 | 3 / 10, p = 0,092 |
| V3 · lượt 2 | 61,03 | 23,59 | 15,38 | 5 / 12, p = 0,14 |
| V3 · lượt 3 | 62,56 | 24,62 | 12,82 | 4 / 10, p = 0,18 |
| **V3 · trung bình** | **61,54** | **25,30** | 13,16 | cùng chiều cả 3 lượt |
| V4 · RRF @2000 | 68,72 | 22,56 | 8,72 | 6 / 8, p = 0,791 |
| Vector thuần | 62,56 | 30,77 | 6,67 | 6 / 13, p = 0,167 |

**Đọc bảng này thế nào.** Null tụt ở mọi cấu hình đưa thêm chunk vector vào context (V3, vector thuần), không riêng việc trộn:
có thêm văn bản liên quan thì Qwen ít chịu nói "không biết" hơn (neither giảm) và bịa nhiều hơn (err tăng). V2 là cấu hình
duy nhất Null tăng, vì nó bớt bằng chứng nên Qwen từ chối nhiều hơn — nhưng acc tổng tụt 5,6 điểm.

## 3. Phép thử sạch — 435 câu ngoài dev

Dev 200 là tập con của 637 và mọi quy tắc đã được nhìn trên dev, nên 435 câu còn lại là phép thử không bị rò.

| Cấu hình | acc | err | neither | So với baseline: lên / xuống |
|---|---:|---:|---:|---|
| **Baseline** | **49,43** | 28,43 | 22,15 | — |
| V1 | 51,34 | 23,98 | 24,67 | 54 / 47, p = 0,551 |
| V2 | 45,82 | 23,83 | 30,34 | 46 / 63, p = 0,125 |
| V3 · lượt 1 / 2 / 3 | 62,99 / 58,85 / 60,46 | 22,38 / 25,59 / 25,44 | 14,64 / 15,56 / 14,10 | 85 / 28 · 78 / 39 · 79 / 32, mỗi lượt p ≤ 4·10⁻⁴ |
| **V3 · trung bình** | **60,77 ± 2,09** | 24,47 | 14,77 | **Δ +11,34** |
| V4 | 54,25 | 25,06 | 20,69 | 58 / 39, p = 0,067 |
| Vector thuần | 65,52 | 24,60 | 9,89 | 107 / 38, p < 0,001 — so với V3 lượt 1: 52 / 40, p = 0,25 |

## 4. Gemini dựng đồ thị và sinh câu trả lời — 637 câu (mốc cũ, 12/09)

Khác đồ thị (Gemini dựng 770 node) và khác model sinh, nên **không so trực tiếp** với bảng Qwen ở trên.

| Cấu hình | acc | err | neither | Single (506) | Multi (66) | Null (65) |
|---|---:|---:|---:|---:|---:|---:|
| Chưa vá answer-type | 61,70 ± 0,31 | 19,57 | 18,73 | 63,64 | 43,43 | 65,13 |
| Đã vá answer-type | 61,38 ± 0,27 | 19,78 | 18,84 | 62,78 | 46,97 | 65,13 |

Vá so với chưa vá: 24 lên / 29 xuống, p = 0,583 — bản vá sửa lỗi thật nhưng không tăng điểm, trên cả Gemini lẫn Qwen.

## 5. Đang sàng lọc — BM25 (chưa phải kết quả chính)

Canary = 100 câu cố định rút từ dev (cả 21 Multi, 20 Null, 59 Single), **một** lượt sinh seed 20260914 × **một** lượt chấm.
Multi và Null gấp đôi tỉ lệ thật, nên số ở đây **không so được** với các bảng trên. Quy trình và cổng: ROADMAP, mục đăng ký
trước BM25.

| Biến thể | acc | err | neither | Single (59) | Multi (21) | Null (20) | So với V3 canary | Quyết định |
|---|---:|---:|---:|---:|---:|---:|---|---|
| V3 đông lạnh (mốc) | 62,00 | 31,00 | 7,00 | 69,5 | 38,1 | 65,0 | — | FROZEN |
| B1 = RRF(đồ thị, vector, BM25) | 66,00 | 29,00 | 5,00 | 79,7 | 38,1 | 55,0 | 10 / 6 trên 97 câu đổi context | lên dev 200 — qua sát nút (net +4 < 1σ = 4,50) |
| B2 = RRF(vector, BM25) | — | — | — | — | — | — | — | canary chưa chạy |

Tầng A (offline, 180 câu dev có evidence, không sinh, không chấm) — tỉ lệ câu có đủ mọi chunk đáp án trong context:
B1 62,8% → 72,2% (20 lên / 3 xuống, p = 0,0005); B2 62,2% → 83,9% (46 lên / 7 xuống, p = 4·10⁻⁸). Đây là dự báo chẩn đoán,
không phải accuracy. Null của B1 trên canary: 0 lên / 2 xuống — cùng chiều vấn đề Null ở mục 2.

## 6. Điều kiện bắt buộc khi trích dẫn

- **So với bài báo là tham chiếu, không phải đối chứng:** khác giám khảo (Gemini thay GPT), khác đồ thị (Qwen dựng 1.556 node,
  đã vá O(N²)), thêm A1@4000 và bản vá answer-type.
- **Một lượt sinh chưa đủ để kết luận về cấu hình** khi net dưới khoảng 18 câu (≈ 2,5 điểm) trên 435 câu — phải lặp lượt
  (CLAUDE.md §3).
- **Báo cả ba cột acc / err / neither.** Hai cấu hình cùng acc có thể hành xử khác hẳn.
- **Lợi ích của V3 gắn với ngân sách 4.000 token** (V4). Không trình bày V3 như cải tiến Efficiency.
- **Mọi công tắc cải tiến mặc định tắt**; bật là quyết định của nhóm.
