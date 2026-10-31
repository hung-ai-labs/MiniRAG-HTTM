# LiHua-World — ablation v2: lợi ích của B2 đến từ đâu (đăng ký trước)

> **Trạng thái: ĐÃ ĐÓNG BĂNG** bằng commit "Pre-register the LiHua-World ablation v2", trước mọi lượt sinh của đợt này
> (kể cả smoke). Không sửa mục "Thiết kế" và "Phép thử" sau commit đó; thay đổi về sau chỉ được thêm ở cuối file dưới dạng
> sửa đổi có ghi ngày, nói rõ đã xem kết quả nào trước khi sửa. Quyết định của người dùng: 31/10/2026.

## Câu hỏi

Trên LiHua-World, B2 (Sources = RRF(vector, BM25)) đã hơn các cấu hình khác ở stage D. Đợt này tách xem lợi ích đó đến từ
thành phần nào — kênh vector, kênh BM25, việc bỏ đồ thị khỏi Sources, bảng Entities, phần đồ thị còn lại khi truy vấn — với
**cả 7 nhánh sinh và chấm lại trong cùng một đợt**, cùng giao thức.

**Stage D (15/09/2026)** không được dùng trong bất kỳ phép so nào ở đây: khác thời điểm và deployment, chấm 1 lượt bằng
`Step_2_evaluate.py` (parser khớp chuỗi con), log context không còn trên máy chạy. Nó chỉ dùng để đối chiếu tính lặp lại: B2–B1
(stage D H3, +6,59) và B2–VEC (H2, +8,12) của đợt v2 có cùng chiều không.

## Thiết kế

**Dữ liệu:** 435 câu ngoài dev — [`dataset/LiHua-World/splits/nondev435.csv`](../../../dataset/LiHua-World/splits/nondev435.csv)
(`query_id = lh-NNNN`, Single 347 / Multi 43 / Null 45; nguồn `reproduce/stage_d/nondev435.csv`, sha256 trong
`nondev435_manifest.json`). Index `LiHua-World-qwen-modal` (Qwen dựng, trần 1024 khi index), chỉ đọc qua bản sao.

**Bảy nhánh** — nền `GROUP_BASE` (`MINIRAG_ANSWER_TYPE_FIX=1 MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT=`, A1@4000):

| Nhánh | Sources | Entities | Đồ thị khi truy vấn / thoát sớm | Công tắc |
|---|---|---|---|---|
| L-C0 | xếp hạng đồ thị gốc | đồ thị | có | — |
| L-B2 | RRF(vector, BM25) | đồ thị | có | `MINIRAG_CHUNK_FUSION=vector_bm25` |
| L-VEC | vector | đồ thị | có | `MINIRAG_CHUNK_FUSION=vector` |
| L-BM25 | BM25 | đồ thị | có | `MINIRAG_CHUNK_FUSION=bm25` |
| L-B1 | RRF(đồ thị, vector, BM25) | đồ thị | có | `MINIRAG_CHUNK_FUSION=rrf_bm25` |
| L-NOENT | như L-B2 (byte-giống) | chỉ header | có | `vector_bm25` + `MINIRAG_DROP_ENTITIES=1` |
| L-NOGRAPH | như L-B2 (byte-giống trên câu L-B2 không thoát sớm) | chỉ header | không parser từ khoá, không đồ thị, không thoát sớm | `MINIRAG_NO_GRAPH=1` |

L-C0 dùng xếp hạng Sources của đồ thị gốc nhưng **không** phải "chỉ đồ thị": `kwd2chunk` nhân điểm ×10 khi chunk đầu đường
nằm trong top vector (`minirag/operate.py`, `kwd2chunk`). L-NOGRAPH không phải "index chưa từng dùng đồ thị".

**Thông số chạy cố định cho mọi nhánh:**

| Thông số | Giá trị |
|---|---|
| Sinh | Qwen/Qwen2.5-3B-Instruct qua Modal vLLM (`reproduce/research/serving_qwen_modal.json`), `MINIRAG_MAX_TOKENS=1024` |
| Seed sinh | 101, 202, 303 |
| Chạy | `reproduce/research/run_phased_dev.sh` (QA 3 pha, `phased_qa.py`); đầu ra từ khoá dùng chung cho mọi nhánh có bước từ khoá cùng seed; L-NOGRAPH không có bước từ khoá; truy hồi `PYTHONHASHSEED=13`; pha C 32 yêu cầu đồng thời |
| Judge | `reproduce/research/judge_run.py`, **`gemini-3.5-flash-lite` (phiên bản ghim)**, prompt V1 của `Step_2_evaluate.py`, 3 lượt, seed 13, hợp đồng nhãn chặt, `--invalid-tries 3`; lượt `parse_failed` sau ≥ 3 vòng resume là phiếu trống (`--abstain-after 3`, như S4 của MultiHop) |
| Thứ tự chấm | 7 nhánh của cùng một seed chấm liền nhau trong một phiên; seed 101 → 202 → 303 |

## Phép thử

Ghép cặp theo câu, **riêng từng seed sinh**. Biến chính: `accurate` vs không-`accurate` trên phán quyết đa số 3 phiếu
(`no_majority` = không đúng). McNemar chính xác (`mcnemar_p`), hiệu số acc với CI 95% bootstrap ghép cặp 10.000 lần seed 13
(`reproduce/research/compare_mhr.py`).

| ID | Phép so | Trả lời | Vai trò | Dự đoán (từ stage D) |
|---|---|---|---|---|
| L1 | L-B2 vs L-C0 | hiệu ứng tổng của B2 | **chính** | B2 hơn |
| L2 | L-B2 vs L-VEC | kênh BM25 | thành phần | B2 hơn |
| L3 | L-B2 vs L-BM25 | kênh vector | thành phần | — |
| L4 | L-B2 vs L-B1 | thêm xếp hạng đồ thị vào Sources | thành phần | B2 hơn |
| L5 | L-B2 vs L-NOENT | bảng Entities | thành phần | — |
| L6 | L-NOENT vs L-NOGRAPH | phần đồ thị còn lại (cổng thoát sớm + parser) | thành phần | — |
| L7 | lỗi trên 45 câu Null: L-B2 vs L-C0 | rủi ro Null | phụ | B2 tăng lỗi |

**Luật đọc:**
- L1 **xác nhận** khi cả 3 seed cùng chiều và p < 0,05 ở từng seed.
- L2–L6 là một họ: trong từng seed, hiệu chỉnh **Holm** trên 5 p của McNemar. Một thành phần "có đóng góp" khi cả 3 seed cùng
  chiều và p Holm < 0,05 ở cả 3 seed. "Không kém hơn" chỉ khi cận dưới CI 95% của hiệu số > −3 điểm ở cả 3 seed.
- Không có ý nghĩa thống kê ≠ hiệu ứng bằng 0: viết "chưa có bằng chứng …".
- L7: biến `error` trên 45 câu Null, McNemar từng seed; báo mô tả kèm cảnh báo cỡ mẫu nhỏ.
- Báo cả hai cách tổng hợp (đa số; mean ± sd 3 lượt judge), sd giữa 3 seed tách riêng; theo Single / Multi / Null.
- **Evidence Recall** (mô tả): tỷ lệ chunk evidence nằm trong Sources đưa vào context, từ `MINIRAG_CONTEXT_LOG` và
  `nondev435_gold_chunks.jsonl` (456/457 dấu thời gian ánh xạ được; Null không có evidence).
- Không đặt số v2 cạnh số stage D như cùng giao thức; không đặt cạnh MultiHop như "cùng judge" (MultiHop dùng bí danh
  `gemini-flash-lite-latest`).

## Giới hạn đã biết trước khi chạy

- Index LiHua-Qwen thiếu chunk của 1 bài (`doc-62f43652…`); 1 dấu thời gian evidence trỏ vào bài đó → không thể truy hồi.
- `lh-0206`: cột Evidence gốc ghi `What` — lỗi dữ liệu, không ánh xạ.
- Index LiHua được dựng với trần sinh 1024 (khác MultiHop 4096) và giữ nguyên để nhất quán với mọi kết quả LiHua.
- Judge mô hình, chưa có nhãn người; rubric Null có mơ hồ đã biết (MultiHop smoke M1.4).

---

## Sửa đổi có ghi ngày

**LA1 — 31/10/2026: quy tắc phiên chấm và cách chạy.** Khai báo trước mọi lượt sinh, kể cả smoke; chưa có kết quả nào.
- *Phiên chấm (như MultiHop):* 7 nhánh của một seed được chấm trong **một phiên** — một tiến trình
  `reproduce/research/judge_session.py` sống suốt phiên. Phiên bị ngắt (tiến trình chết, máy tắt) → phần chấm dở của seed đó
  được đổi tên thành `judge_partial_unread_<thời điểm>`, **không đọc, không dùng**, và cả 7 nhánh của seed được chấm lại từ đầu
  trong một phiên mới. Không có câu trả lời nào bị sinh lại vì lý do này.
- *Chịu lỗi trong một phiên:* quota Gemini cạn không làm phiên kết thúc — bản ghi `judge_failed` được chấm lại trong cùng phiên
  với chờ tăng dần (tối đa 1 giờ mỗi lần, tổng tối đa 36 giờ; quá thì phiên `interrupted`); `parse_failed` được hỏi lại tới 3
  vòng rồi thành phiếu trống (S4). Phiên chạy tách khỏi phiên Claude (PowerShell `Start-Process`); khoá file theo seed.
- *Sinh tách khỏi chấm:* cả 3 seed được sinh trước (`run_phased_dev.sh` với `SKIP_JUDGE=1`), rồi chấm từng seed 101 → 202 → 303.
  Pha B dùng 6 tiến trình (index LiHua 15 MB). Không đổi nội dung yêu cầu, cấu hình hay luật đọc.
- *Smoke:* 20 câu (10 Single / 5 Multi / 5 Null, chọn với seed 13) × 7 nhánh × seed 101 — chỉ kiểm kỹ thuật và đo thông lượng
  judge; số smoke không dùng để kết luận và không gộp vào đợt chính.
