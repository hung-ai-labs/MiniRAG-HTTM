# Kết quả nghiên cứu MultiHop-RAG — Qwen2.5-3B (MiniRAG + B2)

Thư mục gom **kết quả đã xong** của đợt MultiHop-RAG. Kế hoạch, đăng ký trước và các sửa đổi:
[`docs/research/multihop_rag/MULTIHOP_RAG_ROADMAP.md`](../../docs/research/multihop_rag/MULTIHOP_RAG_ROADMAP.md) (đăng ký `7013291`, sửa đổi S1–S4).
Mọi file ở đây được giữ nguyên byte (`-text` trong `.gitattributes`) để các mã sha256 kiểm lại được.

| Thư mục | Nội dung | Nguồn |
|---|---|---|
| [`phase3_test/`](phase3_test/) | **Phase 3 — xác nhận trên test nội bộ 2.156 câu**, C0 vs C1, 3 seed sinh × 3 lượt chấm. Báo cáo: [`MULTIHOP_RAG_REPORT.md`](phase3_test/MULTIHOP_RAG_REPORT.md) | Codex, nhánh `codex/mhr-phase3-acceleration` commit `b640765`; chép nguyên trạng từ `x20-x20/outputs/phase3_test`, 21/21 sha256 khớp `ANALYSIS_COMPLETED.json` |
| [`dev400/`](dev400/) | Phase 1–2 — dev 400 câu, C0–C3, một seed (101): `summary.json`, `per_question.csv`, `run_note.json` mỗi cấu hình và các phép so `compare_mhr.py` | nhánh `research/mhr-qwen`, `runs/multihop_rag/dev400/` |

Index, dữ liệu và baseline: [`docs/research/multihop_rag/baseline_mhr.yaml`](../../docs/research/multihop_rag/baseline_mhr.yaml),
[`docs/research/multihop_rag/artifacts/multihop_rag-qwen-full609.index_manifest.json`](../../docs/research/multihop_rag/artifacts/multihop_rag-qwen-full609.index_manifest.json),
[`dataset/MultiHop-RAG/`](../../dataset/MultiHop-RAG/).

---

## Kết quả chính — Phase 3 (test 2.156 câu, 254 câu Null)

| Seed | C0 acc / err / neither | C1 (B2) acc / err / neither | Δ acc | lên / xuống | p (McNemar) | CI 95% bootstrap |
|---|---|---|---:|---|---:|---|
| 101 | 57,98 / 29,17 / 12,62 | 67,35 / 26,21 / 6,40 | **+9,37** | 456 / 254 | 3,1·10⁻¹⁴ | [7,05; 11,73] |
| 202 | 57,75 / 31,22 / 10,90 | 67,25 / 28,15 / 4,31 | **+9,51** | 439 / 234 | 2,3·10⁻¹⁵ | [7,19; 11,83] |
| 303 | 58,40 / 29,55 / 11,97 | 68,27 / 26,02 / 5,47 | **+9,88** | 436 / 223 | 8,0·10⁻¹⁷ | [7,56; 12,15] |
| **TB ± sd giữa seed** | **58,04 ± 0,33** | **67,63 ± 0,56** | **+9,59** | | | |

Phán quyết đa số của 3 lượt Gemini; nhiễu judge (sd giữa 3 lượt chấm) 0,08–0,47 điểm, báo riêng trong báo cáo.

**Theo tiêu chí đã đăng ký:**
- **RQ2 — ĐÃ XÁC NHẬN:** B2 hơn baseline của nhóm ở **cả 3 seed**, cùng chiều, p < 0,05 từng seed, CI nằm hẳn phía dương.
- **RQ5 — CHƯA XÁC NHẬN, có rủi ro:** lỗi ở câu Null tăng có ý nghĩa ở seed 303 (25,98 → 35,04; 51 / 28; p = 0,013), không có
  ý nghĩa ở seed 101 (p = 1) và 202 (p = 0,72). Không đạt tiêu chí 3/3 seed — **không** được viết "B2 an toàn với Null".
- **Evidence Recall của Sources** (câu có evidence, 1.902): fact recall micro C0 16,3–17,2% → **C1 41,0%**; đủ toàn bộ evidence
  3,2–3,6% → 13,5%. C1 không đổi giữa seed vì vector + BM25 chỉ dựa trên câu hỏi.
- **Theo loại câu:** tăng lớn nhất ở inference (≈ 72 → 87–90); comparison +9, temporal +5 đến +9; Null ≈ không đổi về acc.
  C0 ở comparison/temporal chỉ ≈ 49–53%, gần mức đoán Yes/No.
- **Đối chiếu bài báo (tham chiếu, không đối chứng — RQ1):** C0 58,04 / 29,98 so với MiniRAG–Qwen trong bài báo 50,94 / 35,49
  (GPT-4o chấm, cấu hình gốc).

**Kiểm độc lập (31/10/2026):** tính lại từ `phase3_test/test_per_question.csv` bằng `mcnemar_p` của dự án — tập câu khớp đúng
`dataset/MultiHop-RAG/splits/test_internal.ids` (2.156), đa số tính lại từ 3 lượt khớp 100%, mọi lượt có nhãn hợp lệ, hiệu
số / cặp lên-xuống / p của cả 3 seed và Null khớp báo cáo.

## Kết quả dev 400 (Phase 1–2, một seed — chỉ thăm dò)

| Cấu hình | acc | err | neither |
|---|---:|---:|---:|
| C0 baseline nhóm | 55,25 | 29,00 | 15,25 |
| C1 B2 | 67,75 | 27,00 | 5,00 |
| C2 Sources chỉ vector | 64,25 | 25,25 | 10,50 |
| C3 naive (không đồ thị) | 64,75 | 25,25 | 9,50 |

C1 vs C2 (RQ3): +3,50, p = 0,18 — chưa có bằng chứng BM25 góp phần. C2 vs C0 (RQ4): +9,00, p = 0,003 — thay xếp hạng Sources
của đồ thị bằng vector không làm giảm acc. **Hai phép so này chỉ có trên dev, không được xác nhận trên test** (Phase 3 chỉ
so C0/C1 — quyết định phạm vi 30/10/2026: ưu tiên ablation LiHua, chưa mở thêm ablation MultiHop).

## Đánh giá và sửa đổi cần nêu khi trích dẫn

- **Judge:** `gemini-flash-lite-latest` (bí danh có thể đổi model phía sau), prompt V1 của `Step_2_evaluate.py`, hợp đồng nhãn
  chặt; chưa có nhãn người để hiệu chuẩn, rubric Null còn mơ hồ (smoke M1.4).
  Kế hoạch chuyển sang judge Luna (28/10) **đã huỷ 31/10/2026** — không số nào ở đây dùng Luna.
- **Phase 3 — sửa đổi A1:** 3/38.808 lượt (C1, seed 101, `mhr-1114`, lượt 1–3) không ra nhãn hợp lệ với V1; được chấm lại bằng
  cùng model/rubric/input với **JSON schema** (người dùng duyệt 30/10), cả 3 ra `error`. V1 nguyên gốc: 38.805/38.808; bản có
  A1: 38.808/38.808. Kiểm độ nhạy: với cả 4 khả năng đa số của câu này, kết luận seed 101 không đổi (Δ ∈ [9,37; 9,42]).
- **Dev — sửa đổi S4:** 4/4.800 lượt không ra nhãn sau 9 lần hỏi được tính là phiếu trống.
- **Cách chạy (S1, S2):** QA tách 3 pha (từ khoá → truy hồi CPU → sinh), đầu ra từ khoá dùng chung giữa các cấu hình cùng seed;
  Phase 3 dùng chung thêm phần đồ thị cho C0/C1 (kiểm khớp 800/800 context trên dev). Không đổi nội dung yêu cầu.
- **Index:** trần sinh 4096 token khi index (pilot: 1024 cắt mất relationship), vá O(N²), Qwen qua vLLM; C0 là baseline đã
  sửa của nhóm, **không** phải MiniRAG gốc. C_orig (MiniRAG gốc ở bước hỏi đáp, S3) **chưa chạy**.
- **Dữ liệu:** dev và test chung corpus (84% câu test có evidence trùng ít nhất một bài với dev); 63% chunk không có header
  nguồn/ngày.

## Vận hành và chi phí

- Lời gọi (Phase 3): sinh 12.939 (3 lỗi); từ khoá 6.789 (321 lỗi); judge 49.289 (9.609 lỗi — chủ yếu quota/khoá, được thử
  lại; không lỗi nào thành nhãn).
- Thời gian Qwen phía client: **3,39 giờ** (trần 8 giờ); từ lúc mở Phase 3 đến phiếu cuối: 67,9 giờ lịch (gồm CPU, chờ quota,
  gián đoạn 28–29/10, đã khôi phục từ checkpoint).
- Chi phí: **chưa có hoá đơn thật.** Ước tính trần *trước khi chạy* với giả định bảo thủ (tỷ giá 40.000, hệ số CPU/RAM 1,5, dự
  phòng 350.000 VND cho phần trước): 944.864 / 1.000.000 VND. Theo đơn giá A10G (0,000306 USD/s) chỉ riêng 3,39 giờ GPU của
  Phase 3 ≈ 3,7 USD. Số thật: dashboard Modal → Usage.

## Việc còn mở

1. C_orig (S3) — số "MiniRAG gốc" để đặt cạnh bài báo.
2. Ablation MultiHop (RQ3/RQ4 trên test) — đang hoãn theo quyết định 30/10.
3. Failure taxonomy (M1.7) cho comparison/temporal.
4. Hợp nhất nhánh: code Phase 3 ở `codex/mhr-phase3-acceleration` (gốc `ccacc14`); S4 và kết quả dev ở `research/mhr-qwen`.
5. Backup index và journal thô (raw run nằm trong workspace Codex: `C:\Users\nguye\Documents\Codex\2026-10-26\x20-x20\work`,
   bản chép một phần ở `x20-x20/` trong repo, chưa commit).
