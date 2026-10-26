# Protocol chung — đợt Qwen2.5-3B trên MultiHop-RAG và 2WikiMultiHopQA (S-01)

> **Trạng thái: ĐỀ XUẤT v1 của Người 1 (MultiHop-RAG), chờ Người 2 (2Wiki) review và ký.** Soạn 26/10/2026 trên nhánh
> `research/mhr-qwen`. Mọi giá trị dưới đây đã **chạy thật** trên MultiHop-RAG (pilot, index 609 bài, smoke, dev 400) trừ
> chỗ ghi "chưa chốt". Chỗ nào **khác** [`EXECUTION_PLAN_QWEN_NEW_DATASETS.md`](EXECUTION_PLAN_QWEN_NEW_DATASETS.md) đều ghi
> lý do. Kế hoạch riêng của MultiHop: [`MULTIHOP_RAG_ROADMAP.md`](MULTIHOP_RAG_ROADMAP.md) (đăng ký trước + sửa đổi S1–S3).

**Ký:** Người 1 ☐ ngày … · Người 2 ☐ ngày …

---

## 1. Model và phục vụ

| Mục | Giá trị | Bằng chứng |
|---|---|---|
| Model | `Qwen/Qwen2.5-3B-Instruct`, revision **`aa8e72537993ba99e69dfaafa59ed015b17504d1`** | HF `main` không đổi từ 25/09/2024 — trước mọi deployment của nhóm |
| Phục vụ | vLLM **0.11.0**, A10G, **bf16**, `max_model_len` **32768**, `reproduce/modal_slm.py` | `slm_smoke.py` đọc `/version`, `/v1/models` |
| Sampling | mặc định của server = `generation_config.json` của revision trên: **temperature 0.7, top_p 0.8, top_k 20, repetition_penalty 1.05** | vLLM `--generation-config auto`; không quan sát được từ client → ghi là suy ra |
| Seed | `MINIRAG_SLM_SEED` gửi theo request; lượt khẳng định dùng **101 / 202 / 303** | vLLM không bảo đảm tất định khi batch — seed chỉ giảm, không xoá nhiễu |
| Trần sinh | **index: `MINIRAG_MAX_TOKENS=4096`**, **QA: 1024** | xem §3 (khác EXECUTION_PLAN B1) |
| Cấu hình đã ghim | [`reproduce/research/serving_qwen_modal.json`](../../reproduce/research/serving_qwen_modal.json) | dùng cho `qa_run.py --serving-config` |

**Endpoint: mỗi người một deployment riêng** (Người 2 chạy GPU riêng). Mỗi đợt nghiên cứu dùng **một** deployment từ đầu đến
cuối; run ghi `endpoint_sha256` (băm URL, không lưu URL/khoá). Trước mỗi lượt tốn tiền:

```sh
python reproduce/research/slm_smoke.py --out runs/<dataset>/_serving/smoke.json   # 3/3 kiểm phải đạt
```

Khoá: `MINIRAG_SLM_URL`, `MINIRAG_SLM_KEY` trong `.env` (gitignored), không bao giờ ghi vào log hay commit.
`response.model` của vLLM trả **tên model thật** → mọi runner ghi nó cho từng request và **từ chối** nếu thấy Gemini.

## 2. Judge

| Mục | Giá trị |
|---|---|
| Model | **`gemini-flash-lite-latest`** — giống LiHua. **Khác EXECUTION_PLAN B4/V-06 (Gemini Flash).** Chọn 26/10/2026 |
| Prompt | `JUDGE_PROMPT` của `reproduce/Step_2_evaluate.py`, **nguyên văn** |
| Runner | `reproduce/research/judge_run.py` (không dùng `Step_2_evaluate.py` cho dataset mới) |
| Hợp đồng nhãn | phản hồi phải là **đúng một** trong `accurate` / `error` / `neither` (bỏ qua hoa/thường, khoảng trắng, nháy, `*`, dấu câu bao quanh). Còn lại — kể cả `"inaccurate"` — là không hợp lệ: hỏi lại, hết 3 lần → **`parse_failed`**. Lỗi API hết 6 lần → **`judge_failed`**. Không bao giờ tự gán nhãn |
| Lượt | **3 lượt**, xáo thứ tự `random.Random(13 + pass)`; khoá bản ghi theo `query_id` |
| Tổng hợp | (1) **phán quyết đa số** mỗi câu (`no_majority` nếu 1–1–1) → cho McNemar; (2) **mean ± sd giữa 3 lượt** → đặt cạnh bài báo. Báo cả hai, không trộn |
| Thứ tự chấm | các cấu hình được so trên cùng seed chấm **liền nhau trong một phiên**; ghi thời điểm |
| Thoát sớm | câu trả lời = `PROMPTS["fail_response"]` được chấm như thường **và** đếm riêng (`early_exit`) |

**Vì sao Flash-Lite thay Flash.** (a) cùng judge với LiHua; (b) quota free tier rộng hơn cho ~40k lời gọi của đợt test.
**Rủi ro đã biết:** `-latest` là bí danh trôi và `response.model` chỉ trả tên bí danh — đổi model phía sau không phát hiện được
→ luật "chấm liền nhau". **Nếu 2Wiki muốn Flash:** được, nhưng khi đó số của hai dataset không đặt cùng bảng judge, và phải
chốt ID trước run đầu. Danh sách ID khả dụng (đọc 26/10): `gemini-flash-latest`, `gemini-flash-lite-latest`,
`gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, …

**Đã biết về rubric (smoke MultiHop, đọc tay 20 phán quyết):** lời từ chối đúng cho câu không trả lời được đôi khi bị chấm
`neither` thay vì `accurate` (1/4 ca). Rubric giữ nguyên (đã đăng ký); biến `error` không bị ảnh hưởng.

## 3. Index

| Mục | Giá trị |
|---|---|
| Runner | `reproduce/research/index_run.py` |
| Chunk / gleaning / embedding | 1200 / 100 token (`tiktoken gpt-4o-mini`), gleaning 1, `sentence-transformers/all-MiniLM-L6-v2` 384d local — mặc định MiniRAG |
| Trần sinh khi index | **4096** — **khác EXECUTION_PLAN** (1024). Pilot MultiHop 30 bài: ở 1024, **56%** đầu ra trích xuất bị cắt, phần mất là relationship → 60% node cô lập; ở 4096 còn 2%, cạnh gấp đôi. ~5% đầu ra ở 4096 là vòng lặp lặp danh sách (chỉ cộng dồn trọng số vài cạnh) |
| Thư mục | `indexes/<dataset>-qwen-<corpus>/` (gitignored); index xong: file **chỉ đọc**, manifest có sha256 từng file được chép vào `docs/research/artifacts/` |
| Song song | `--llm-max-async 32 --batch-docs 32` (index 609 bài: 162 phút, ~715 token sinh/giây) |
| Bắt buộc trên Windows | `PYTHONUTF8=1` (MiniRAG in ký tự Unicode làm chết tiến trình khi stdout ghi ra file) |

**Lỗi resume của MiniRAG (phải biết khi tự viết runner):** doc status ghi ngay, còn chunk/vector chỉ ghi ở cuối `ainsert` →
bị ngắt thì bài thành "processed" mà không có chunk, đồ thị trỏ tới chunk không tồn tại. `index_run.py` xử lý bằng
`reconcile_checkpoint` và kiểm 6 liên kết doc–chunk–vector–graph khi xong. Index Qwen của LiHua đã dính lỗi này ở 1 bài.

## 4. QA — 3 pha

**Runner:** `reproduce/research/phased_qa.py` (sửa đổi S2). Truy hồi trên đồ thị lớn tốn ~20–60 s CPU/câu trong một luồng
Python; chạy liền một tiến trình thì GPU trả tiền ngồi chờ. Tách pha:

| Pha | Việc | Tài nguyên |
|---|---|---|
| A `keywords` | prompt từ khoá đúng như `minirag_query` (TYPE_POOL sắp xếp), qua cùng `llm_model_func`, ghi vào cache `MINIRAG_KW_CACHE` | GPU, vài phút / 400 câu |
| B `contexts` | `rag.aquery(only_need_context=True)` với `MINIRAG_KW_CACHE_ONLY=1`, LLM bị thay bằng hàm báo lỗi, `PYTHONHASHSEED=13`, N tiến trình | **chỉ CPU** (~1,5 GB RAM / tiến trình) |
| C `answers` | lời gọi trả lời dựng lại nguyên văn (`rag_response` / `naive_rag_response`, cùng hậu xử lý), 32 song song | GPU, ~7 phút / 400 câu |

`tests/research/test_phased_qa.py` chứng minh trên index MiniRAG thật (LLM giả): 3 pha gửi **cùng các lời gọi LLM** và trả
**cùng câu trả lời** như `rag.aquery` (mini và naive). Đầu ra từ khoá **dùng chung** giữa các cấu hình `mini` cùng seed.

Chuỗi đầy đủ: `reproduce/research/run_phased_dev.sh <questions.csv> <out> <seed> C0 C1 C2 C3` (A một lần, B→C từng cấu
hình, rồi chấm liền nhau; mọi bước resume được).

**Cấu hình** (nền `GROUP_BASE`: `MINIRAG_ANSWER_TYPE_FIX=1 MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT=`, A1@4000):

| ID | Thêm | Ghi chú |
|---|---|---|
| C0 | — | baseline đã sửa của nhóm (≡ GROUP_BASE) |
| C1 | `MINIRAG_CHUNK_FUSION=vector_bm25` | B2 (≡ B2_FULL) |
| C2 | `MINIRAG_CHUNK_FUSION=vector` | ≡ B2_NO_BM25 |
| C3 | mode `naive` | không đồ thị, chỉ mô tả |
| C_orig | `MINIRAG_ANSWER_TYPE_FIX=0 MINIRAG_TRUNCATE_SOURCES=0` | MiniRAG gốc ở bước hỏi đáp trên index đã vá; chỉ mô tả |

B2_NO_VECTOR, B2_NO_ENT, HYBRID_NO_GRAPH (EXECUTION_PLAN S-07) **chưa hiện thực** và nằm ngoài phạm vi MultiHop; MR_MINUS_* vẫn
chặn bởi V-01.

## 5. Dữ liệu và tách tập

- `dataset/<name>/raw/` (gốc) → `processed/` (sinh bằng script, ghim sha256, `-text` trong `.gitattributes`) → `splits/`
  (danh sách `query_id`, `split_manifest.json`). Mẫu: `prepare_multihop_rag.py`, `make_mhr_split.py`, `count_mhr_chunks.py`.
- Ở `processed/`: `docs.jsonl` (`doc_id`, `minirag_doc_id` = ID MiniRAG gán, `text` = chuỗi đưa vào index), `queries.jsonl`
  (không có đáp án), `gold.jsonl`, `questions.csv` (`Question, Gold Answer, Type, query_id` — đầu vào chung của mọi runner).
- Test nội bộ chỉ có danh sách ID; file câu hỏi của test tạo khi mở test (`--emit-test`).

## 6. Thống kê (như bản đăng ký MultiHop)

Biến chính `accurate` vs không-`accurate` theo phán quyết đa số; McNemar chính xác (`mcnemar_p` trong
`reproduce/screening/screen_variant.py`), báo `b lên / c xuống, p`; biến phụ `error`. Bootstrap ghép cặp theo câu, riêng từng
lượt sinh, 10.000 lần, seed 13. Lượt khẳng định: 3 lượt sinh, xác nhận khi cả 3 cùng chiều và p < 0,05. "Không kém hơn" chỉ
khi cận dưới CI 95% > −3 điểm. Không có ý nghĩa ≠ hiệu ứng bằng 0. **`metrics.py` (S-06, phần Người 2) chưa viết** — đầu
vào đề xuất: hai file `per_question.csv` của `judge_run.py` ghép theo `query_id`.

## 7. Schema log (đã chạy thật)

| File | Ghi bởi | Một dòng / bản ghi |
|---|---|---|
| `index_requests.jsonl` | index_run | `request_model, max_tokens, seed, prompt_sha256, phase (extract/glean), chunk_id, ok, error_type, latency_s, response_model, finish_reason, prompt_tokens, completion_tokens, response_text, at` |
| `index_progress.jsonl`, `events.jsonl` | index_run | lô đã xong; start / resume / reconcile / batch / failed / finish |
| `index_manifest.json` | index_run | identity (docs sha256, chọn bài, settings, source sha256, endpoint sha256), `status`, `verification` (6 kiểm), `counts`, `file_sha256` |
| `kw_s<seed>.jsonl` | phased A | `prompt_sha256, result, query_id` (định dạng cache của MiniRAG) |
| `<cfg>_s<seed>/contexts.jsonl` | phased B | `query_id, status (ok/no_context/early_exit), context, retrieval_s` |
| `<cfg>_s<seed>/context.jsonl` | MiniRAG (`MINIRAG_CONTEXT_LOG`) | `query, n_chunks, sources_tok, entities_tok, fusion, chunk_ids, ranked_ids, graph_ids, vector_ids, context_sha256, graph_seeds, graph_paths, retrieval_ms` |
| `<cfg>_s<seed>/answers.jsonl`, `answers.csv` | phased C | `query_id, answer, context_status`; CSV `Question, Gold Answer, minirag` theo thứ tự đầu vào |
| `requests.jsonl` | phased A/C | như `index_requests.jsonl`, không có `response_text` |
| `judge/judge.jsonl` | judge_run | `query_id, pass, status (ok/parse_failed/judge_failed), label, type, attempts[{ok, raw, label, error_type, requests[…]}]` |
| `judge/per_question.csv`, `summary.json` | judge_run | `query_id, Type, pass1..3, majority`; summary chỉ ghi khi mọi bản ghi `ok` |
| `run_note.json` | phased B | config, seed, mode, commit đăng ký + HEAD, sha256 câu hỏi / manifest index / cache từ khoá (trường `environment` hiện ghi rỗng — lỗi ghi chép đã biết, sửa sau dev 400; giá trị thật = bảng §4) |

## 8. Cách ly, lưu trữ, backup

- Mỗi người một nhánh (`research/mhr-qwen`, `research/2wiki-qwen`); không ghi vào `dataset/`, `indexes/`, `runs/` của người
  kia; không sửa `minirag/` (mọi runner bọc từ ngoài, `llm_trace.py` bọc client trong tiến trình).
- `indexes/` và `runs/` gitignored. **Nơi backup: chưa chốt — cần nhóm quyết.** Đề xuất: thư mục Google Drive chung của nhóm,
  mỗi mốc (index đóng băng, run hoàn tất) nén `tar.gz` + `sha256`, mở thử rồi mới coi là đã backup.
- Máy: index đầy 160 MB, mỗi tiến trình pha B ~1,5 GB RAM; ổ đĩa trống ≥ 3 GB cho một đợt dev.

## 9. Còn chờ chốt

| # | Việc | Ai |
|---|---|---|
| 1 | Ký protocol này (hoặc sửa) | Người 2 review, cả hai ký |
| 2 | Nơi backup chung | nhóm |
| 3 | Judge cho 2Wiki: theo Flash-Lite (đề xuất) hay Flash | Người 2 |
| 4 | Tham số hoá runner cho dataset khác: `index_run.py` (đường dẫn `docs.jsonl`, tiền tố thư mục), `phased_qa.py` (hằng `INDEX`) đang gắn MultiHop | Người 1 sửa sau dev 400 MultiHop (đang chạy) |
| 5 | `metrics.py`, fixture offline chung, công tắc ablation S-07 | Người 2 (theo EXECUTION_PLAN) |
