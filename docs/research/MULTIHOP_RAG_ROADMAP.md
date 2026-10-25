# MultiHop-RAG — Roadmap tái hiện và kiểm chuyển giao (Qwen2.5-3B)

> Một người làm · nhánh `research/mhr-qwen` · theo khuôn [`ROADMAP.md`](../../ROADMAP.md) của LiHua-World.
> Chi tiết giao thức gốc cho hai người: [`EXECUTION_PLAN_QWEN_NEW_DATASETS.md`](EXECUTION_PLAN_QWEN_NEW_DATASETS.md).
> Dữ liệu và cách dựng: [`dataset/MultiHop-RAG/README.md`](../../dataset/MultiHop-RAG/README.md).

## Ký hiệu

| Ký hiệu | Nghĩa |
|---|---|
| 💻 | Offline, miễn phí |
| 🟣 | Tốn GPU Modal (Qwen) |
| 🔵 | Tốn quota Gemini (chỉ chấm) |
| ⏸ | Phải được duyệt trước khi chạy |
| ✅ / 🔄 / ⬜ | Xong / đang làm / chưa bắt đầu |

---

## Mục tiêu

LiHua-World cho kết quả chính là **B2 = RRF(vector, BM25)** cho Sources: acc **73,95 ± 2,21** trên 435 câu ngoài dev,
kèm hai giới hạn — Null khẳng định sai nhiều hơn, và thay xếp hạng Sources của đồ thị bằng vector không làm giảm acc.

Đợt này trả lời: (1) pipeline MiniRAG + Qwen2.5-3B cho kết quả bao nhiêu trên MultiHop-RAG, đối chiếu bài báo;
(2) phát hiện của LiHua có **lặp lại** trên corpus tin tức không. Mọi dự đoán và quy tắc thống kê được **đăng ký trước**
(mục dưới), không tinh chỉnh theo kết quả. Kết quả âm là kết quả hợp lệ.

**Quy tắc cố định.** Qwen2.5-3B (Modal vLLM) làm cả index lẫn QA; Gemini **chỉ chấm**. Không xoá/ghi đè index khi chưa hỏi.

**Tham chiếu bài báo** (`miniRAG1.pdf`, Table 1, Qwen2.5-3B, GPT-4o chấm): MiniRAG trên MultiHop-RAG
**50,94 ± 4,58 / 35,49 ± 3,87** (acc / err). Số 48,55 / 33,10 trong `README.md` là phiên bản bài báo khác — không dùng.

---

## Cách ly — không ảnh hưởng LiHua-World và luồng 2Wiki

| Thứ cần bảo vệ | Cách giữ |
|---|---|
| Index LiHua (`LiHua-World-*`) | Index MultiHop chỉ ở `indexes/multihop_rag-*`; `index_run.py` từ chối mọi đường dẫn khác và mọi thư mục đã tồn tại khi chạy mới. `qa_run.py` chỉ chạy trên bản sao index |
| Kết quả LiHua đã đóng băng | Không ghi vào `logs/`; đầu ra ở `runs/multihop_rag/`. Không sửa `Step_2_evaluate.py`, `baseline.yaml`, `logs/devset.csv` |
| Code dùng chung | Đợt này **không sửa** `minirag/`. Code mới là file mới trong `reproduce/research/`. Ghi metadata request bằng cách bọc client trong tiến trình (`llm_trace.py`), không sửa backend |
| Luồng 2Wiki | Không đụng `dataset/2WikiMultiHopQA/`. Người làm 2Wiki chạy GPU riêng → endpoint không dùng chung. MultiHop dùng **một** deployment duy nhất (workspace Modal của người làm MultiHop) cho toàn bộ đợt; đổi deployment giữa chừng là thay đổi điều kiện thí nghiệm (`endpoint_sha256` trong manifest phải giữ nguyên) |
| Nhánh git | `research/mhr-qwen` tách từ `dev`, merge theo mốc |

Kiểm sau mỗi mốc: `git diff dev -- minirag/ logs/ baseline.yaml reproduce/Step_*.py dataset/LiHua-World dataset/2WikiMultiHopQA`
rỗng, và `python -m unittest discover tests/research` xanh.

---

## Cấu hình — đặt tên đúng phạm vi

Nền chung `GROUP_BASE`: `MINIRAG_ANSWER_TYPE_FIX=1 MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT=`, A1@4000, mode `mini`.
Mọi cấu hình dùng công tắc **đã có** — không viết thêm cơ chế truy hồi.

| ID | Cấu hình | Là gì — và **không** phải là gì |
|---|---|---|
| C0 | `GROUP_BASE` | Baseline **đã sửa của nhóm** (vá answer-type, cắt Sources A1@4000). **Không** phải MiniRAG gốc của bài báo |
| C1 | C0 + `MINIRAG_CHUNK_FUSION=vector_bm25` | **B2**: Sources = RRF(vector, BM25). Entities, parser từ khoá, đường thoát sớm khi đồ thị rỗng **vẫn như C0** |
| C2 | C0 + `MINIRAG_CHUNK_FUSION=vector` | Chỉ thay **xếp hạng Sources** bằng vector. Entities và đường thoát sớm vẫn phụ thuộc đồ thị → C2 ≥ C0 **không** chứng minh "đồ thị vô ích" |
| C3 | `--mode naive` | Mốc tham khảo không dùng đồ thị; khác C0 ở nhiều điểm cùng lúc → chỉ mô tả |

Ngoài phạm vi: −I / −Rchunk / −Redge (bài báo không mô tả cách hiện thực; V-01 chưa giải).

---

## Câu hỏi nghiên cứu và phép thử — đăng ký trước

> **Trạng thái: ĐÃ ĐÓNG BĂNG (M0.6)** bằng commit "Pre-register the MultiHop-RAG transfer study", trước mọi lượt sinh thật
> của C0–C3 (kể cả smoke). Từ commit đó mục này không được sửa; mọi run ghi hash commit đó vào manifest. Thay đổi về sau
> chỉ được thêm ở cuối file dưới dạng "sửa đổi có ghi ngày", kèm lý do, và phải nói rõ đã xem kết quả nào trước khi sửa.

**Thông số chạy cố định cho mọi run QA (C0–C3, dev và test):**

| Thông số | Giá trị |
|---|---|
| Index | một index duy nhất `indexes/multihop_rag-qwen-full609` cho mọi cấu hình |
| Model sinh | `minirag-slm` (Qwen2.5-3B-Instruct, Modal vLLM), `MINIRAG_MAX_TOKENS=1024`, `serving.json` của M0.7 |
| Song song | `qa_run.py --concurrency 4 --llm-max-async 4`, giống nhau ở mọi cấu hình |
| Seed sinh (`MINIRAG_SLM_SEED`) | dev: 101 · test: 101 / 202 / 303 |
| Log truy hồi | `MINIRAG_CONTEXT_LOG` bật ở mọi run (cho Evidence Recall) |
| Judge | `judge_run.py`, `gemini-flash-lite-latest`, 3 lượt, seed 13, `--invalid-tries 3` |
| Thứ tự chấm | các cấu hình được so với nhau trên **cùng seed sinh** được chấm **liền nhau trong cùng một phiên**; ghi thời điểm chấm |
| Thoát sớm | câu trả lời đúng bằng `PROMPTS["fail_response"]` được chấm như mọi câu, **và** đếm riêng theo cấu hình và loại câu (`early_exit` trong `summary.json`) |

Judge giữ bí danh `gemini-flash-lite-latest` (chọn 26/10/2026). `response.model` chỉ trả lại tên bí danh, nên nếu Google đổi
model đứng sau bí danh giữa chừng thì không phát hiện được. Quy tắc "chấm liền nhau" giới hạn rủi ro này trong từng phép so;
rủi ro còn lại ghi vào Limitations.

**Đơn vị so sánh.** Mỗi câu, mỗi lượt sinh: chấm **3 lượt** judge (`judge_run.py`) → **phán quyết đa số**
(cùng quy tắc `reproduce/summarize_v3_replicates.py`). Ba nhãn khác nhau (1–1–1) → `no_majority`.

**Hợp đồng nhãn của judge.** Phản hồi phải là **đúng một** trong `accurate` / `error` / `neither` (bỏ qua hoa/thường,
khoảng trắng, nháy, dấu sao, dấu câu bao quanh). Mọi thứ khác — kể cả `"inaccurate"` — là phản hồi không hợp lệ: hỏi lại,
hết lượt → `parse_failed`. Không ánh xạ sang nhãn nào. Lỗi API hết lượt → `judge_failed`.

**Biến chính:** `accurate` so với không-`accurate` (`error`, `neither`, `no_majority` đều là không đúng). McNemar chính xác
trên các cặp lệch, báo `b lên / c xuống, p`. **Biến phụ:** `error` so với không-`error`, McNemar. `neither`, `no_majority`
chỉ báo mô tả. `parse_failed` / `judge_failed` **không** vào thống kê: chấm lại tới khi hết, nếu không lượt đó không hoàn tất.

**Ba lượt sinh (test).** McNemar riêng từng lượt; tiêu chí xác nhận: **cả 3 lượt cùng chiều và p < 0,05 ở từng lượt**.
Kèm hiệu số acc ghép cặp với **khoảng tin cậy 95% bootstrap ghép cặp theo câu** (lấy mẫu lại câu, giữ cặp C0/C1 của câu),
**tính riêng cho từng lượt sinh**, 10.000 lần lặp, seed 13.

**Hai cách tổng hợp điểm — báo cả hai, ghi rõ là hai chỉ số khác nhau:**

1. **Phán quyết đa số.** Mỗi câu, mỗi lượt sinh, một nhãn đa số của 3 lượt judge. Dùng cho **McNemar** và **hiệu số acc
   ghép cặp**. Không dùng để đặt cạnh bài báo.
2. **Mean ± sd giữa ba lượt judge.** Trong **từng lượt sinh**: acc/err của mỗi lượt judge, rồi mean ± sd của 3 giá trị.
   Báo **riêng cho từng lượt sinh**, để đối chiếu bài báo và các bảng LiHua. sd này là **nhiễu judge**; **sd giữa ba lượt
   sinh** (trên acc đa số của từng lượt sinh) báo ở cột riêng, không gộp dưới một dấu ±.

**Cách viết kết luận.**
- Không có ý nghĩa thống kê **không** chứng minh hiệu ứng bằng không. Dev: "chưa có bằng chứng … ở lượt thăm dò".
  Test, không đạt tiêu chí: "chưa xác nhận được …".
- Chỉ viết "không kém hơn" khi cận dưới khoảng tin cậy 95% của hiệu số > **−3 điểm** ở cả 3 lượt sinh.

| ID | Câu hỏi | Phép so | Vai trò | Dự đoán từ LiHua |
|---|---|---|---|---|
| RQ1 | Pipeline C0 + Qwen cho acc/err bao nhiêu? | C0 trên test, đặt cạnh bài báo | Mô tả — **tham chiếu, không đối chứng** (khác judge, khác baseline) | — |
| RQ2 | B2 có hơn C0 không? | C1 vs C0 trên **test** | **Khẳng định — phép thử chính** | có |
| RQ5 | B2 có làm err của Null tăng không? | C1 vs C0, biến phụ `error`, **chỉ 254 câu Null của test** | Khẳng định — phép thử phụ | có |
| RQ3 | BM25 có góp phần trong B2 không? | C1 vs C2 trên **dev** | **Thăm dò — chỉ có bằng chứng dev, không xác nhận trên test** | có |
| RQ4 | Thay xếp hạng Sources của đồ thị bằng vector có làm giảm acc không? | C2 vs C0 trên **dev** | Thăm dò; kết luận chỉ về xếp hạng Sources | không giảm |

47 câu Null của dev chỉ báo mô tả, không gộp với Null của test. RQ2 là phép thử chính duy nhất; RQ5 là phép thử phụ, không
hiệu chỉnh đa phép thử nhưng ghi rõ vai trò.

---

## Phase 0 — Chuẩn bị

M0.1–M0.6 không cần key. Làm đúng thứ tự.

| # | Task | Loại | Đầu ra | ✓ |
|---|---|---|---|---|
| M0.1 | Chuẩn hoá dữ liệu: `prepare_multihop_rag.py` | 💻 | `dataset/MultiHop-RAG/processed/` (609 bài, 2.556 câu) | ✅ |
| M0.2 | Đóng băng dev 400 / test theo `query_id`: `make_mhr_split.py`, phân tầng 4 loại, seed 13 | 💻 | `dataset/MultiHop-RAG/splits/` — dev 134/128/91/47, test 722/688/492/254 | ✅ |
| M0.3 | Judge chặt: `judge_run.py` (prompt nguyên văn của `Step_2_evaluate.py`, hợp đồng nhãn, `parse_failed`/`judge_failed`, phản hồi thô, khoá `query_id`, đa số + mean ± sd) | 💻 | script + 8 test offline | ✅ |
| M0.4 | Đếm chunk thật: `count_mhr_chunks.py` | 💻 | `processed/chunk_stats.json` — **1.656 chunk**, ≈ 3.312 lời gọi index | ✅ |
| M0.5 | `index_run.py` + `llm_trace.py`: chặn Gemini, chặn thư mục ngoài `indexes/multihop_rag-*`, log từng request, resume theo lô, kiểm toàn vẹn | 💻 | script + 8 test offline (gồm ngắt-rồi-resume trên MiniRAG thật với LLM giả) | ✅ |
| M0.6 | **Đăng ký trước + commit**: đóng băng mục trên, commit trước mọi lượt sinh thật | ⏸ | commit "Pre-register the MultiHop-RAG transfer study" | ✅ |
| M0.7 | Key + revision: `MINIRAG_SLM_KEY`, gói `modal`, 1 lời gọi thử, ghim HF revision / vLLM / sampling (V-04) | 🟣 ⏸ | [`serving_qwen_modal.json`](../../reproduce/research/serving_qwen_modal.json) (revision `aa8e7253…`, bf16, 32k, sampling của `generation_config`); `slm_smoke.py` 26/10: vLLM 0.11.0, phục vụ `Qwen/Qwen2.5-3B-Instruct` + `minirag-slm`, `response.model` = `Qwen/Qwen2.5-3B-Instruct`, khởi động lạnh 53 s — 3/3 kiểm đạt | ✅ |

**Phát hiện ở Phase 0 (ghi vào Limitations / failure taxonomy):**
- Bài ngắn nhất 1.113 token, vượt bước nhảy 1.100 của bộ chunk → **cả 609 bài đều ≥ 2 chunk**, **1.047 chunk (63%) không có
  header nguồn/ngày**. 73 chunk đuôi ≤ 100 token chỉ lặp phần chồng lấn.
- Dev và test dùng chung corpus: **1.604 / 1.902** câu test có evidence chung ít nhất một bài với dev; **638** có tập evidence
  trùng hệt một câu dev.
- **Lỗi resume của MiniRAG** (bắt được bằng test ngắt-rồi-resume): doc status được ghi ngay, còn chunk/vector chỉ ghi ở cuối
  `ainsert` → bị ngắt giữa chừng thì bài ở trạng thái "processed" nhưng không có chunk, và đồ thị trỏ tới chunk không tồn tại.
  `index_run.py` xử lý bằng `reconcile_checkpoint`. **Index Qwen của LiHua đã dính lỗi này**: `doc-62f43652…bb873`
  (bài chat 26/04, 6.229 ký tự, 2 chunk) không có chunk nào trong `kv_store_text_chunks.json`/`vdb_chunks.json`, 2 chunk được
  đồ thị trích dẫn không tồn tại — bài này không bao giờ vào Sources ở mọi lượt LiHua-Qwen. Chưa sửa (cách ly); nhóm quyết.

## Phase 1 — Tái hiện & phát hiện lỗi

| # | Task | Loại | Đầu ra | ✓ |
|---|---|---|---|---|
| M1.1 | Pilot index 30 bài (seed 13): `index_run.py --subset pilot --workingdir indexes/multihop_rag-qwen-pilot30` | 🟣 ⏸ | lời gọi/chunk thật, % `finish_reason=length` ở `MINIRAG_MAX_TOKENS=1024` (V-05), dự toán index đầy đủ | ✅ |
| M1.2 | Index 609 bài → `indexes/multihop_rag-qwen-full609/`; checksum, backup, chỉ đọc | 🟣 ⏸ | index `completed`, 6/6 kiểm đạt, file chỉ đọc; manifest + sha256 từng file: [`artifacts/multihop_rag-qwen-full609.index_manifest.json`](artifacts/multihop_rag-qwen-full609.index_manifest.json). **Backup ngoài máy: chưa** (chưa có `<BACKUP_ROOT>`) | ✅ |
| M1.3 | Ánh xạ evidence → chunk (`fact` → chunk qua `minirag_doc_id`): `map_mhr_evidence.py` | 💻 | `processed/gold_chunks.jsonl` — 6.084/6.084 fact nằm trọn trong chunk, 139 fact nằm ở 2 chunk (vùng chồng lấn), 0 chunk thiếu trong index | ✅ |
| M1.4 | Smoke 20 câu dev × C0, C1; đọc tay 20 phán quyết (Yes/No, "Insufficient information.", từ chối) | 🟣 🔵 | judge và parser đúng trên dataset mới; 0 `parse_failed` sót | ⬜ |
| M1.5 | C0 trên dev 400: 1 lượt sinh × 3 lượt chấm, bật `MINIRAG_CONTEXT_LOG` | 🟣 🔵 | `baseline_mhr.yaml` đóng băng + kết quả theo loại câu | ⬜ |
| M1.6 | Evidence Recall của Sources (context log + M1.3) | 💻 | recall theo loại câu | ⬜ |
| M1.7 | Failure taxonomy trên câu sai/neither của C0 | 💻 | phân phối lỗi + ví dụ thật | ⬜ |

**Kết quả M1.1 (26/10/2026) — trần token khi index nâng từ 1024 lên 4096.** Hai pilot cùng 30 bài, cùng mọi thông số
trừ `MINIRAG_MAX_TOKENS` (chỉ áp cho **index**; QA giữ 1024 như bản đăng ký):

| Pilot | Bị cắt (`length`) trích xuất / gleaning | Relationship trung vị mỗi đầu ra (trích xuất / gleaning) | Cạnh | Node cô lập | Bản ghi trùng | Lời gọi Qwen | Thời gian |
|---|---|---|---:|---:|---:|---:|---:|
| `pilot30` (1024) | 32/71 · 47/70 | 5 · 1,5 | 308 | 505/847 (60%) | 2,6% | 141/141 Qwen, 0 lỗi | ≈ 9 phút + 1 lần resume |
| `pilot30-cap4096` | **0/69 · 3/69** | **8 · 6** | **607** | **309/924 (33%)** | 9,0% | 138/138 Qwen, 0 lỗi | 13,5 phút |

Ở 1024, phần bị cắt là danh sách thật (ít trùng), và vì định dạng đầu ra liệt kê entity trước relationship nên phần mất là
relationship: 28/47 đầu ra gleaning bị cắt không có relationship nào. Đồ thị thưa ở 1024 là do **trần hạ tầng**, không phải
do SLM (CLAUDE.md §1 đã cảnh báo). Ở 4096, vài đầu ra lặp lại danh sách tới trần (5/138 đầu ra chiếm ~80% bản ghi trùng):
entity trùng được gộp theo tên và mô tả trùng bị loại, chỉ **trọng số của vài cạnh bị cộng dồn** — hiệu ứng đã biết, ghi
vào Limitations. Index Qwen của LiHua dùng 1024 → so sánh cấu trúc đồ thị giữa hai dataset phải ghi khác biệt này.
Resume trên dữ liệu thật (pilot 1024 dừng vì lỗi in Unicode của Windows; chạy lại với `PYTHONUTF8=1 --resume`) đã dọn 8 bài
của lô dở và qua đủ 6 kiểm toàn vẹn.

**Cấu hình index đầy đủ (M1.2):** `MINIRAG_MAX_TOKENS=4096 PYTHONUTF8=1 index_run.py --subset full --llm-max-async 32
--batch-docs 32`. Song song 32 (giới hạn `@modal.concurrent` của endpoint) chỉ để giảm thời gian GPU — Modal tính tiền theo
thời gian container chạy; nội dung yêu cầu gửi đi không đổi.

**Kết quả M1.2 (26/10/2026).** Một lần chạy, không resume, 162 phút (≈ 715 token sinh/giây, gấp ~3 lần pilot ở song song 8).

| Mục | Giá trị |
|---|---|
| Tài liệu / chunk | 609 / 1.656 — khớp dự kiến |
| Node / cạnh | 18.561 / 14.849; node cô lập 6.524 (35%) |
| Lời gọi | 3.312 thành công, **100% `Qwen/Qwen2.5-3B-Instruct`**; 1 `APIConnectionError` lúc khởi động lạnh, tự thử lại |
| Chạm trần 4096 | trích xuất 129/1.656 · gleaning 195/1.656 (9,8%). **149/324 là vòng lặp** (< 50% bản ghi duy nhất); ~175 đầu ra (5,3%) là danh sách dài thật bị cắt, vẫn giữ trung vị 30 bản ghi duy nhất |
| Bản ghi trùng | 15,7% tổng; đầu ra tự dừng chỉ 4,3% — gần như toàn bộ phần trùng nằm trong các vòng lặp |
| Chunk không sinh entity | 5 (3 chunk đuôi 25–39 token, 2 chunk thường) |
| Token sinh | 5,35 triệu |

Nâng trần thêm chỉ tốn GPU cho vòng lặp → giữ 4096. Vòng lặp làm cộng dồn trọng số một số cạnh (Limitations).

**Cổng ra Phase 1:** baseline đóng băng + bảng lỗi. Luôn báo **theo loại câu**: 52% đáp án là Yes/No (comparison 96%,
temporal 90%) → ~50% acc ở hai loại này đạt được bằng đoán.

## Phase 2 — Thăm dò chuyển giao trên dev

| # | Task | Loại | Đầu ra | ✓ |
|---|---|---|---|---|
| M2.1 | Kiểm mọi run mang đúng hash đăng ký M0.6 | 💻 | ghi vào roadmap | ⬜ |
| M2.2 | C1, C2, C3 trên dev 400: 1 lượt sinh × 3 lượt chấm, cùng index | 🟣 🔵 | 3 bộ kết quả | ⬜ |
| M2.3 | Phân tích theo quy tắc đăng ký: RQ3, RQ4, xem trước RQ2; Evidence Recall từng cấu hình | 💻 | `b lên / c xuống, p` + khoảng tin cậy | ⬜ |
| M2.4 | Cấu hình vào test: **C0 và C1** — đã chốt, không đổi theo dev | 💻 | ghi vào roadmap | ⬜ |

Không chỉnh tham số theo dev. C1 không hơn C0 có ý nghĩa trên dev → "chưa có bằng chứng chuyển giao ở lượt thăm dò", vẫn
chạy test như đã chốt.

## Phase 3 — Xác nhận trên test & báo cáo

| # | Task | Loại | Đầu ra | ✓ |
|---|---|---|---|---|
| M3.1 | Dự toán GPU + Gemini từ số đo thật; kiểm quota thật; dừng nếu vượt trần | 💻 ⏸ | dự toán | ⬜ |
| M3.2 | C0, C1 trên test 2.156 câu (`make_mhr_split.py --emit-test`): 3 lượt sinh (seed 101/202/303) × 3 lượt chấm | 🟣 🔵 | kết quả chính | ⬜ |
| M3.3 | Thống kê: RQ2 (chính), RQ5 (phụ), RQ1 (mô tả); sd sinh và sd judge báo riêng | 💻 | bảng kết quả | ⬜ |
| M3.4 | `docs/research/MULTIHOP_RAG_REPORT.md`: RQ1–RQ5 đúng vai trò, theo loại câu, so với LiHua, Limitations | 💻 | báo cáo | ⬜ |

**Limitations ghi sẵn:** judge Gemini thay GPT-4o, qua bí danh trôi `gemini-flash-lite-latest`; C0 là baseline đã sửa; RQ3/RQ4 chỉ có bằng chứng dev một lượt sinh;
corpus dùng chung giữa dev và test; 63% chunk không có header; định dạng metadata là lựa chọn của nhóm; `Step_2_evaluate.py`
của LiHua còn lỗi parser (khớp chuỗi con, rơi về `neither`) — số LiHua chưa chấm lại; index LiHua-Qwen thiếu chunk của 1 bài.

---

## Chi phí (ước lượng — thay bằng số đo ở M1.1, M1.5)

| Bước | Qwen (Modal) | Gemini (chấm) |
|---|---:|---:|
| Index | ≈ 3.312 lời gọi (1.656 chunk × 2) | — |
| Smoke: 2 cấu hình × 20 câu | 80 | 120 |
| Dev: 4 cấu hình × 400 câu | ≈ 3.200 | 4.800 |
| Test: 2 cấu hình × 3 lượt sinh × 2.156 | ≈ 25.872 | **38.808** |

Chưa tính retry. Chấm test ≈ 25 giờ là **mức lý tưởng** ở 26 lời gọi/phút, chưa gồm thời gian chờ quota hồi; "miễn phí"
chỉ đúng nếu quota thực tế đáp ứng (M3.1 kiểm trước). Trần chung của đợt: dưới 1 triệu VND. Judge `gemini-flash-lite-latest`
như LiHua (CLAUDE.md §1) — khác đề xuất Gemini Flash ở EXECUTION_PLAN B4.

---

## Lệnh

```sh
# Phase 0 — kiểm lại dữ liệu đóng băng (offline)
python reproduce/research/prepare_multihop_rag.py --check
python reproduce/research/count_mhr_chunks.py --check
python reproduce/research/make_mhr_split.py --check
python -m unittest discover tests/research

# M1.1 — pilot index (⏸, tốn GPU; cần MINIRAG_SLM_URL + MINIRAG_SLM_KEY)
PYTHONUTF8=1 MINIRAG_MAX_TOKENS=4096 python reproduce/research/index_run.py --subset pilot --workingdir indexes/multihop_rag-qwen-pilot30-cap4096
python reproduce/research/index_run.py --subset pilot --workingdir indexes/multihop_rag-qwen-pilot30 --resume
python reproduce/research/index_run.py --subset pilot --workingdir indexes/multihop_rag-qwen-pilot30 --verify

# M1.5 — QA rồi chấm (⏸)
python reproduce/research/qa_run.py --questions dataset/MultiHop-RAG/splits/dev400.csv \
    --workingdir indexes/multihop_rag-qwen-full609 --run-dir runs/multihop_rag/c0_dev400_g1
python reproduce/research/judge_run.py --questions dataset/MultiHop-RAG/splits/dev400.csv \
    --answers runs/multihop_rag/c0_dev400_g1/answers.csv --run-dir runs/multihop_rag/c0_dev400_g1/judge
```
