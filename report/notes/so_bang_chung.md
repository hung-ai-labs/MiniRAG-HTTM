# Sổ bằng chứng

Số liệu từng macro (giá trị, file nguồn, commit) do script sinh: [`../generated/evidence.csv`](../generated/evidence.csv).
Chạy lại: `.venv/Scripts/python.exe report/scripts/make_numbers.py`. Script dừng nếu số tính lại khác
`logs/stage_d/stage_d_report.json`, hoặc nếu một hằng số trích từ báo cáo không có nguyên văn trong file nguồn.

Bảng dưới là **mức bằng chứng** của các khẳng định trong tóm tắt, giới thiệu và kết luận. Mọi câu trong bài phải dùng đúng
"câu được phép" của dòng tương ứng.

Điều kiện chung (trừ khi ghi khác): LiHua-World, 435 câu ngoài dev, Qwen2.5-3B (vLLM), MiniLM-L6 384d, giám khảo
`gemini-flash-lite-latest` lượt chấm 1, rubric gốc, A1@4000, cùng chỉ mục `LiHua-World-qwen-modal`. Tập 435 không dùng để chọn biến thể.

| # | Khẳng định | Hiệu số [KTC 95%] | Kiểm định | Nguồn | Mức | Câu được phép viết |
|---|---|---|---|---|---|---|
| 1 | Bỏ đồ thị khỏi RRF(G,V,K) tăng acc (H3) | `\diffHC` [`\ciLoHC`; `\ciHiHC`] | hoán vị gộp 3×3 lượt, Holm/3, đăng ký trước | `logs/stage_d/` | **B** — B2 mang lệch đăng ký ở cổng thời gian (tầng B) | "tăng … [KTC], đạt mọi tiêu chí đã đăng ký, với điều kiện một lệch đăng ký đã khai báo ở cổng thời gian" |
| 2 | Thêm BM25 vào RRF(G,V) tăng acc (H1) | `\diffHA` [`\ciLoHA`; `\ciHiHA`] | như trên | `logs/stage_d/` | **A** | "cải thiện … có ý nghĩa thống kê (p_Holm)" |
| 3 | Thêm BM25 vào vectơ thuần (H2) | `\diffHB` [`\ciLoHB`; `\ciHiHB`] | như trên; **trượt E4** (Null net −3,33 < −3) | `logs/stage_d/` | **B** — BORDERLINE | "cải thiện accuracy, với điều kiện trượt cổng an toàn của nhóm Null"; **không** viết "BM25 cộng thêm giá trị so với vectơ thuần" như đã chứng minh |
| 4 | RRF(V,K) hơn MiniRAG tái lập (X3) | `\diffXC` [`\ciLoXC`; `\ciHiXC`] | hoán vị, Holm/4, **không** đăng ký trước; MiniRAG 1 lượt sinh | `logs/qwen637_fix_judged.csv`, `logs/stage_d/b2_*` | **A-kp, có điều kiện** | "cao hơn … (phân tích khám phá; MiniRAG một lượt sinh; đã thử 23 cấu hình)" |
| 5 | Vectơ thuần hơn RRF(G,V) (X4) | `\diffXD` [`\ciLoXD`; `\ciHiXD`] | hoán vị 3×3, Holm/4, khám phá. Phép thử **đã đăng ký** (1 lượt, 635 câu): 80/61, p = 0,13 → D | `logs/qwen637_v3*`, `logs/qwen637_vec*`, `logs/stage_d/vec_*` | **A-kp** (khám phá) mâu thuẫn hướng với kết quả D đã đăng ký | "việc trộn với đồ thị không được chứng minh là tốt hơn vectơ thuần"; **không** viết "ngang nhau" |
| 6 | Không cấu hình nào mà đồ thị trong xếp hạng làm tăng acc | — | tổng hợp 1, 5 | như trên | suy từ 1 + 5 | "trên bộ dữ liệu này, chúng tôi không tìm thấy cấu hình nào mà …" |
| 7 | Nhóm Null giảm (X3, Null) | `\diffXCNull` [`\ciLoXCNull`; `\ciHiXCNull`] | hoán vị theo nhóm, không hiệu chỉnh, n = 45 | như 4 | **C** | "có xu hướng giảm …, chưa xác nhận" |
| 8 | Null: rubric làm rõ xoá khoảng cách giữa các nhánh trộn, không xoá khoảng cách với MiniRAG | bảng `table_null.tex` | không kiểm định (đăng ký Đ6) | `logs/null_audit/d6_clarified/baseline_ket_qua.txt` | **F** (độ nhạy, 1 người hiệu chuẩn) | đặt cạnh số chính thức, không thay |
| 9 | Đồ thị đánh rơi đoạn đáp án (47,3% vào Sources so với 87,0% trong top-30 vectơ) | — | mô phỏng tất định, dev 180 | `logs/simulate_fusion.txt`, `logs/diag_path2chunk_report.txt` | **chẩn đoán** trên tập đã dùng để thiết kế | "chẩn đoán", "dự báo"; không gọi là kết quả xác nhận |
| 10 | Sửa khớp loại đáp án không đổi điểm | Qwen 44/40 p = 0,744 · Gemini 24/29 p = 0,583 | McNemar 1 lượt | `CLAUDE.md` | **D** | "không phân biệt được" |
| 11 | Số của bài MiniRAG gốc | — | — | `CLAUDE.md` | **G** | "tham chiếu"; không tính hiệu số |

## Quy tắc nhóm có vấn đề thống kê (đã báo người dùng)

- `CLAUDE.md` và `ROADMAP.md` cho phép viết "vectơ thuần và trộn RRF **ngang nhau**" (luật (c)) chỉ dựa trên p = 0,13. Thiếu ngưỡng
  tương đương định trước nên câu đúng là "không phân biệt được". Ngoài ra phân tích khám phá 3×3 lượt (X4) nghiêng về vectơ thuần.
  Bài dùng "không được chứng minh là tốt hơn", không dùng "ngang nhau".

## Mâu thuẫn số giữa các tài liệu (đã giải thích)

- MiniRAG trên 435 câu: `docs/CAI_TIEN_VA_BENCHMARK.md` ghi 49,89, `docs/KET_QUA_HIEN_TAI.md` ghi 49,43. Nguyên nhân là
  `reproduce/demo/bang_benchmark.py` lấy đa số qua 3 lượt chấm cho MiniRAG nhưng chỉ có 1 lượt chấm cho B2 (gộp không cân xứng).
  Bài theo quy tắc đã đăng ký: lượt chấm 1 cho mọi nhánh → **49,43**, và hiệu số với B2 là **+24,52**, không phải +24,06.
- Tỉ lệ truy xuất của MiniRAG: `docs/CAI_TIEN_VA_BENCHMARK.md` ghi 46,4% / 41,7% (dựng lại offline, file context không còn trong
  repo), `logs/simulate_fusion.txt` ghi 47,3% / 43,3%. Bài dùng bộ thứ hai vì nó cùng công cụ với các dòng khác của bảng (dòng V3
  trùng khớp ở cả hai file mô phỏng).

## Bảng chuyển mã nội bộ → tên trong bài

| Mã trong repo | Tên trong bài |
|---|---|
| baseline `qwen637_fix` | MiniRAG (tái lập) |
| V3 (`rrf`) | RRF(đồ thị, vectơ) |
| VEC (`vector`) | Vectơ thuần |
| B1 (`rrf_bm25`) | RRF(đồ thị, vectơ, BM25) |
| B2 (`vector_bm25`) | RRF(vectơ, BM25) |
| H1 / H2 / H3 | giữ nguyên tên giả thuyết |
| X1–X4 | phép so khám phá (đặt trong bài) |
| A1@4000 | ngân sách B = 4000 token |
| tầng D | vòng xác nhận trên tập ngoài dev |

## Thuật ngữ Anh – Việt (một khái niệm, một tên)

| English | Trong bài |
|---|---|
| retrieval-augmented generation (RAG) | sinh tăng cường truy xuất (RAG) |
| small language model (SLM) | mô hình ngôn ngữ nhỏ (SLM) |
| chunk | đoạn (văn bản) |
| dense retrieval | truy xuất vectơ |
| reciprocal rank fusion | RRF (trộn xếp hạng nghịch đảo) |
| held-out set | tập ngoài dev |
| pre-registration | đăng ký trước |
| ablation | loại bỏ thành phần |
| LLM-as-judge | giám khảo LLM |
| context budget | ngân sách ngữ cảnh |
