# Kết quả LiHua-World — ablation v2 (Qwen2.5-3B, 7 nhánh × 3 seed)

Lợi ích của B2 (Sources = RRF(vector, BM25)) trên LiHua-World đến từ thành phần nào. Đăng ký trước, thiết kế và luật đọc:
[`docs/research/lihua_world/LIHUA_ABLATION_V2.md`](../../../docs/research/lihua_world/LIHUA_ABLATION_V2.md) (đăng ký
`860f20f`, sửa đổi LA1 `9a448c1`). Mọi file ở đây giữ nguyên byte (`-text` trong `.gitattributes`); mã sha256 trong
[`SHA256SUMS`](SHA256SUMS).

| File | Nội dung |
|---|---|
| [`ANALYSIS.json`](ANALYSIS.json), [`ANALYSIS.md`](ANALYSIS.md) | Đầu ra của `reproduce/research/analyze_lihua_ablation.py`: tỷ lệ theo nhánh × seed × loại câu, L1–L7, Holm, cờ quyết định, Evidence Recall |
| [`per_run/<nhánh>_s<seed>/`](per_run/) | 21 lượt: `per_question.csv` (3 phiếu + đa số mỗi câu), `summary.json`, `judge_manifest.json`, `run_note.json` (đăng ký, commit, index, biến môi trường) |
| [`sessions/`](sessions/) | `judge_s<seed>_SESSION.json` — một phiên chấm mỗi seed: thời điểm, số vòng, phiếu trống, model trả lời |

Dữ liệu thô (`answers.jsonl`, context, `judge.jsonl`) nằm ở `runs/lihua_world/ablation_v2/` (gitignored).

---

## Kết quả

435 câu ngoài dev (Single 347 / Multi 43 / Null 45). Phán quyết đa số của 3 lượt `gemini-3.5-flash-lite`; ± là sd giữa 3 seed
sinh.

| Nhánh | Sources | acc | err | neither | Single | Multi | Null | Evidence Recall (micro / đủ evidence) |
|---|---|---:|---:|---:|---:|---:|---:|---|
| L-C0 | xếp hạng đồ thị gốc | 48,89 ± 0,35 | 28,28 | 22,68 | 48,70 | 27,91 | 70,37 | 40,3 / 36,8 |
| **L-B2** | RRF(vector, BM25) | **73,64 ± 1,50** | 19,16 | 6,98 | 80,21 | 37,98 | 57,04 | 69,4 / 64,9 |
| L-VEC | vector | 65,83 ± 1,76 | 22,07 | 11,95 | 70,41 | 37,21 | 57,78 | 58,7 / 52,2 |
| L-BM25 | BM25 | 75,02 ± 0,48 | 19,08 | 5,60 | 82,04 | 35,66 | 58,52 | 70,2 / 68,0 |
| L-B1 | RRF(đồ thị, vector, BM25) | 66,90 ± 1,44 | 21,99 | 10,95 | 71,85 | 37,21 | 57,04 | 63,5 / 60,3 |
| L-NOENT | như B2, bỏ bảng Entities | 75,09 ± 0,58 | 20,23 | 4,52 | 82,23 | 39,53 | 54,07 | 69,4 / 64,9 |
| L-NOGRAPH | như B2, không parser / đồ thị / thoát sớm | 74,40 ± 0,93 | 21,46 | 3,99 | 81,84 | 34,88 | 54,82 | 69,4 / 65,0 |

err, neither, theo loại câu và Evidence Recall là trung bình 3 seed. Evidence Recall tính trên 388 câu có evidence ánh xạ được
(bỏ Null, `lh-0101`, `lh-0206`).

### Các phép so (ghép cặp theo câu, từng seed)

Δ = acc(b) − acc(a); lên / xuống = số câu đổi sang / khỏi `accurate`; p là McNemar chính xác; L2–L6 kèm p Holm trong seed.

| ID | b − a | Seed 101 | Seed 202 | Seed 303 | Theo luật đã đăng ký |
|---|---|---|---|---|---|
| **L1** | B2 − C0 | +25,05 (139/30) p 6·10⁻¹⁸, CI [19,8; 30,3] | +23,21 (129/28) p 1·10⁻¹⁶, CI [17,9; 28,5] | +25,97 (140/27) p 1·10⁻¹⁹, CI [20,7; 31,3] | **Xác nhận** |
| L2 | B2 − VEC | +7,35 (62/30), Holm 0,006 | +4,82 (56/35), Holm 0,142 | +11,26 (67/18), Holm 4·10⁻⁷ | cùng chiều dương, **chưa đạt** (seed 202) |
| L3 | B2 − BM25 | −0,92 (39/43), Holm 0,74 | −3,22 (30/44), Holm 0,28 | 0,00 (40/40), Holm 1 | trái chiều — chưa có bằng chứng |
| L4 | B2 − B1 | +5,05 (59/37), Holm 0,126 | +6,43 (61/33), Holm 0,025 | +8,73 (61/23), Holm 2·10⁻⁴ | cùng chiều dương, **chưa đạt** (seed 101) |
| L5 | B2 − NOENT | −2,07 (22/31), Holm 0,54 | −2,99 (19/32), Holm 0,28 | +0,69 (28/25), Holm 1 | trái chiều — chưa có bằng chứng |
| L6 | NOENT − NOGRAPH | +2,07 (15/6), Holm 0,24 | −0,23 (8/9), Holm 1 | +0,23 (9/8), Holm 1 | trái chiều — chưa có bằng chứng |

**Đọc theo luật:**
- **L1 — xác nhận.** B2 hơn C0 khoảng 23–26 điểm ở cả 3 seed. Chênh lệch lớn hơn nhiều so với MultiHop (+9,6). Đi kèm, `neither` giảm từ 22,7
  xuống 7,0 và `err` giảm từ 28,3 xuống 19,2 (ít lỗi hơn có ý nghĩa ở cả 3 seed, p ≤ 0,005).
- **Không thành phần nào đạt mức "có đóng góp"** (cùng chiều và p Holm < 0,05 ở cả 3 seed).
  - L2 (thêm BM25 vào vector) và L4 (bỏ xếp hạng đồ thị khỏi Sources) cùng chiều dương ở cả 3 seed và lặp lại chiều của
    stage D (+8,12 / +6,59). Nhưng mỗi phép so trượt ở một seed, nên chỉ được viết "cùng chiều, chưa đạt tiêu chí".
    B2 **không kém hơn** VEC và B1 (cận dưới CI > −3 ở cả 3 seed).
  - L3: BM25 một mình ngang B2 (75,02 so với 73,64). **Chưa có bằng chứng kênh vector góp phần**, và cũng không khẳng định được
    là B2 không kém BM25 (cận dưới CI −7,1 ở seed 202).
  - L5, L6: chưa có bằng chứng bảng Entities hay phần đồ thị còn lại (parser từ khoá, cổng thoát sớm) ảnh hưởng tới acc.
    Ba nhánh B2 / NOENT / NOGRAPH có Sources byte-giống nhau nên Evidence Recall gần như bằng nhau.
- **L7 — Null (phụ, n = 45, cỡ mẫu nhỏ):** acc Null của B2 thấp hơn C0 ở cả 3 seed (−6,7 / −11,1 / −22,2). Chỉ seed 303
  có ý nghĩa (1 lên / 11 xuống, p = 0,006). Biến đã đăng ký là `error` trên Null: B2 nhiều lỗi hơn không có ý nghĩa ở seed
  nào (p 0,11 / 1 / 0,45). **Không** được viết "B2 an toàn với Null".
- **Mô tả, không phải kiểm định:** Evidence Recall đi cùng thứ hạng acc — đồ thị gốc đưa đúng 40% chunk evidence vào Sources,
  B2 / BM25 khoảng 70%, vector 59%, B1 64%. Phần lớn mức tăng của B2 trùng với việc đưa được nhiều chunk evidence hơn vào
  Sources. Với bộ dữ liệu này, kênh BM25 tự nó đã truy hồi tốt bằng B2.

**Kiểm độc lập (01/11/2026):** tính lại L1–L6 từ `per_run/*/per_question.csv` bằng một script riêng (đếm cặp, McNemar chính
xác qua `math.comb`, không dùng code phân tích): mọi Δ, lên / xuống và p khớp `ANALYSIS.json` (lệch ≤ 0,01 điểm do làm tròn).

## Điều kiện cần nêu khi trích dẫn

- **Judge:** `gemini-3.5-flash-lite` (phiên bản ghim), prompt V1 của `Step_2_evaluate.py`, hợp đồng nhãn chặt, 3 lượt. 27.401
  phiếu, `response_models` 100% model ghim. Chưa có nhãn người. **Không** đặt cạnh MultiHop như "cùng judge" (MultiHop dùng bí
  danh `gemini-flash-lite-latest`), **không** đặt cạnh stage D như cùng giao thức.
- **Phiếu trống (S4) — 4 / 27.405:** `lh-0026` L-B2 s101 lượt 3; `lh-0029` L-BM25 s202 lượt 2 và 3 (còn 1 phiếu →
  `no_majority`); `lh-0027` L-B1 s303 lượt 2.
- **Thoát sớm:** 1 câu (`lh-0044`, seed 202, 6 nhánh có đồ thị). Từ khoá seed 202 không khớp được node nào, MiniRAG trả lời
  mặc định; L-NOGRAPH trả lời đúng. Đây là cơ chế mà L6 đo, được giữ trong dữ liệu.
- **Index:** `LiHua-World-qwen-modal` (Qwen dựng, trần 1024 khi index; thiếu chunk của bài `doc-62f43652…`), chỉ đọc qua
  bản sao. C0 là baseline đã sửa của nhóm (answer-type fix, A1@4000), **không** phải MiniRAG gốc.
- **Không phải đóng góp của đồ thị:** các nhánh tốt nhất (B2, BM25, NOENT, NOGRAPH) đều không dùng xếp hạng đồ thị trong
  Sources. Không được viết "đồ thị góp phần" hay "trộn giữ lợi thế đồ thị" (cùng kết luận với ablation vector thuần 14/09
  trong `CLAUDE.md`).

## Vận hành

| Mốc | Thời gian (giờ VN) |
|---|---|
| Sinh 3 seed (Qwen qua Modal vLLM, QA 3 pha, 6 worker CPU) | 31/10 17:11 → 01/11 02:04 |
| Phiên chấm seed 101 | 31/10 20:42 → 22:00 (78 phút) |
| Phiên chấm seed 202 | 31/10 23:41 → 01/11 14:44 — quota ngày Gemini cạn từ khoảng 0:30, phiên chờ trong cùng tiến trình tới khi quota đặt lại lúc 14:00 |
| Phiên chấm seed 303 | 01/11 15:27 → 16:48 |

- Không phiên nào bị ngắt, không có phần chấm dở nào phải cất (`archived_partial_unread` rỗng ở cả 3 phiên).
- Seed 303: 4 lần khởi động hỏng lúc 14:46–14:53 ngày 01/11. Tiến trình tách nền bị dừng sau 2–4 giây, trước khi tạo khoá hay
  thư mục `judge/`, nên chưa có phiếu nào. Log trống giữ lại ở `runs/lihua_world/ablation_v2/judge_s303_failed_start_*`.
  Phiên hợp lệ duy nhất là phiên 15:27.
- Máy vào chế độ chờ vài lần khi đang sinh. Thời gian truy hồi của một số câu bị kéo dài (ví dụ 6 câu L-VEC s101 khoảng
  2.640 s), nhưng nội dung không đổi. Đừng dùng `retrieval_s` của đợt này để báo độ trễ.
- Chi phí GPU: chưa có hoá đơn. Số thật xem ở dashboard Modal → Usage.
