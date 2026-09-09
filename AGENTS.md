# CLAUDE.md — MiniRAG Research Project

Hướng dẫn cho Claude khi làm việc trong repo này. Đọc kèm [ROADMAP.md](ROADMAP.md).

---

## ⚠️ QUY TẮC BẮT BUỘC

### 1. Gemini để lặp. **SLM cho lần chạy cuối** — đã chốt 09/09/2026.

| | Giai đoạn lặp (bây giờ) | **Lần chạy cuối** |
|---|---|---|
| Language model | `gemini-flash-lite-latest` | **SLM cục bộ**: `Qwen/Qwen2.5-3B-Instruct` hoặc `microsoft/Phi-3.5-mini-instruct` |
| Dùng cho | index + query + generation | **giống hệt** — MiniRAG chỉ có một `llm_model_func` |
| Judge | `gemini-flash-lite-latest`, 3 lượt | `gemini-flash-lite-latest`, 3 lượt (giữ nguyên để so sánh được) |
| Embedding | local `all-MiniLM-L6-v2` (384d) | **không đổi** — giống bài báo |
| Hạ tầng | API free tier | Modal / Kaggle GPU (CUDA) |
| Chi phí | 0đ | ~1–2 USD trên Modal A10G |

**Vì sao đổi từ `gpt-4o-mini` sang SLM.** Luận điểm trung tâm của MiniRAG là hệ
thống chạy được với **Small Language Model** — đó là lý do bài báo tồn tại. Con số
so sánh được với bảng của bài báo phải là dòng SLM (`Phi-3.5-mini 53,29%`,
`Qwen2.5-3B 48,75%`), không phải dòng `gpt-4o-mini`. Chạy thêm `gpt-4o-mini` là
tuỳ chọn, không bắt buộc.

**Sai lệch hiện tại phải ghi vào Limitations.** `reproduce/gemini_common.py:117`
đặt `llm_model_func=gemini_complete`, và `Step_0_index.py` dùng chính hàm đó. Nên
`gemini-flash-lite` đã làm **cả 4 việc**: trích xuất entity lúc index
(`operate.py:271`), gleaning (`:275`), phân tích câu hỏi (`:1425`), sinh câu trả
lời (`:1474`). Đồ thị 770 node hiện tại là **do Gemini dựng**, không phải SLM —
nên nó sạch hơn đồ thị mà bài báo đo được, và baseline 57,33% cao hơn **mọi** dòng
trong bảng bài báo kể cả `gpt-4o-mini` (54,08%).

**Chạy SLM thế nào.** Phải index lại **bằng chính SLM đó** rồi mới QA — chạy SLM
trên index Gemini chỉ là ablation phần sinh, không phải tái tạo.

- Đừng dùng `minirag/llm/hf.py`: nó sinh từng prompt một (`hf.py:150`, batch=1) →
  10–14 giờ trên T4, vượt giới hạn 12 giờ/phiên của Kaggle.
- Dùng **vLLM**, nó phục vụ API tương thích OpenAI nên tái dùng được cấu trúc của
  `gemini.py` (đổi base URL, bỏ key pool). **30–60 phút** trên A10G.
- Khối lượng: 503 chunk × 2 + 200 câu × 2 = **1.406 lời gọi**.
- **Không chọn `GLM-Edge-1.5B`** — context thật đo được có trung vị 3.908 token,
  p90 6.830, max 8.291; cửa sổ 8k của nó sẽ tràn.
- Cảnh báo: `main.py:61` đặt `llm_model_max_token_size=200` và `hf.py:151` giới hạn
  `max_new_tokens=512`. Đầu ra trích xuất dễ bị cắt giữa chừng → node rác. Kiểm chỗ
  này trước khi kết luận đồ thị thưa là do SLM yếu.

**Không tự ý gọi API trả phí.** Mọi thí nghiệm trung gian chạy Gemini free tier.

### 1b. ⛔ Thế nào là đóng góp khoa học, thế nào là cải tiến giả

Chốt với nhóm 09/09/2026. **Đọc trước khi đề xuất bất kỳ cải tiến nào.**

Một đóng góp hợp lệ phải đủ **5 bước**:

| # | Bước | Nghĩa là |
|---|---|---|
| 1 | **Observed Problem** | Có dữ liệu thực nghiệm chứng minh MiniRAG hỏng ở đâu (Failure Taxonomy) |
| 2 | **Hypothesis** | Giả thuyết khoa học: vì sao cơ chế mới khắc phục được lỗi đó |
| 3 | **Designed Mechanism** | Giải thuật cụ thể — hybrid fusion, path re-weighting, adaptive routing |
| 4 | **Controlled Experiment** | Cô lập biến, cùng tập dữ liệu, cùng điều kiện |
| 5 | **Measurable Effect** | Đo được cả Quality lẫn Efficiency, kèm Ablation |

**Sáu hành vi bị cấm — không được gọi là Proposed Method:**

| Bị cấm | Lý do |
|---|---|
| Đổi Top-K đơn thuần | Tinh chỉnh tham số, không phải phương pháp |
| Đổi LLM temperature | Không can thiệp vào cơ chế RAG bên dưới |
| Đổi sang API / LLM to hơn | Điểm tăng do model, không chứng minh được đóng góp thuật toán |
| Đổi sang embedding model khác | Không phải đóng góp về cấu trúc hay cơ chế retrieval |
| Sửa vài câu trong system prompt | Prompt engineering, thiếu tính khái quát hoá |
| Bọc thêm framework / tool UI | Kỹ thuật phần mềm bề mặt, không phải nghiên cứu giải thuật |

**Hệ quả cho các giả thuyết đang có** trong
[`docs/phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md`](docs/phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md):

| Giả thuyết | Có phải Proposed Method không? | Vai trò đúng |
|---|---|---|
| **G1** sửa lỗi hoa/thường `get_node_from_types` | ❌ **Không** — sửa bug | **Sửa baseline.** Baseline hiện đang đo một cơ chế hỏng. Phải sửa, đo lại, và báo cáo như một *finding*, không phải đóng góp |
| **G3** chỉnh `top_k` / giới hạn token Sources | ❌ **Không** — đúng ô cấm số 1 | Hạ xuống thành **sensitivity study** làm bằng chứng cho Observed Problem (`context_precision 0,316`) |
| **G2** chuẩn hoá thực thể lúc merge | ✅ **Có** | Designed Mechanism — đổi cách dựng đồ thị |
| **G4** hybrid BM25 + dense | ✅ **Có** | Designed Mechanism — "hybrid fusion" nằm đúng trong ví dụ hợp lệ |
| **Path pruning / re-weighting** *(từ phát hiện 22.879 đường, 96% vô ích)* | ✅ **Có** | Designed Mechanism — "path re-weighting" nằm đúng trong ví dụ hợp lệ |
| **G5** bật lại tóm tắt description | ⚠️ Ranh giới | Khôi phục hành vi upstream đã tắt. Chỉ tính nếu trình bày như đóng góp **Efficiency** kèm số đo |
| **G6** dọn node rác lúc extraction | ⚠️ Ranh giới | Làm sạch dữ liệu. Gộp vào H2 như một thành phần, đừng đứng riêng |

**Lưu ý về ô cấm "đổi LLM to hơn":** dùng Gemini **không** vi phạm, với điều kiện
nó là **hằng số** giữa baseline và proposed — đó là Controlled Experiment. Vi phạm
là khi lấy điểm cao nhờ model mạnh rồi trình bày như đóng góp thuật toán.

### 2. Baseline đã đóng băng — mọi so sánh phải dựa vào nó.

Cấu hình chuẩn nằm trong **[`baseline.yaml`](baseline.yaml)** (chốt 07/09/2026,
commit `dbfa0d1`). **Không sửa file đó.** Muốn thử cấu hình khác thì tạo file mới,
giữ nguyên file này làm mốc.

Baseline corpus 442 đã chạy xong, nên ràng buộc *"chưa được cải tiến vội"* trước đây
đã được gỡ. Nhưng cải tiến vẫn phải đi theo trình tự trong ROADMAP: **failure
taxonomy trước, giả thuyết sau** — không thử mò tham số.

### 3. Quy tắc đọc kết quả (sàn nhiễu judge = **sd 1,53 điểm**)

Đo trên chính baseline corpus 442: acc dao động **3,00 điểm** giữa 3 lượt judge.

| Mức thay đổi | Kết luận |
|---|---|
| > +5 điểm | Gần như chắc chắn có cải thiện → tiếp tục |
| +3 đến +5 điểm | Có triển vọng, nhưng phải rerun 3 lượt mới dám khẳng định |
| **< 3 điểm** | **Không kết luận được** — nằm trong nhiễu của judge |

⚠️ Con số cũ **sd 0,29** đo trên corpus 267 tài liệu, **đã lỗi thời**. Corpus đầy đủ
khó hơn → nhiều câu trả lời mơ hồ hơn → judge đổi ý nhiều hơn. Ngưỡng "không kết
luận được" vì thế nhảy từ 0,6 lên ~3 điểm.

Khi làm benchmark cuối để viết báo cáo: **rerun nhiều lượt** để chứng minh cải tiến
là thật, không phải may mắn.

### 4. Không xoá index khi chưa hỏi.

`./LiHua-World-gemini/` là tài sản đắt nhất trong repo. Trước đây đã từng bị `rm -rf`
làm mất một index 32 tài liệu. **Luôn hỏi trước khi xoá hoặc ghi đè.**

---

## Trạng thái index hiện tại

Thư mục làm việc: `./LiHua-World-gemini/`

| Thành phần | Giá trị |
|---|---|
| Tài liệu | **442 / 442 processed** (toàn bộ corpus LiHua-World) |
| Chunks | 503 |
| `extracted_chunks.json` | 516 chunk đã trích xuất (checkpoint chống bug O(N²)) |
| Embedding | **local `all-MiniLM-L6-v2`, 384 chiều** |
| Cache LLM | `kv_store_llm_response_cache.json` — **0 entry dù `enable_llm_cache=True`** (nghi bug upstream, chưa điều tra) |

**Embedding 384d không trộn được với index dùng Gemini embedding (3072d).** Đổi
embedding model = phải index lại từ đầu.

### Khi nào PHẢI index lại

| Thay đổi | Index lại? |
|---|---|
| `chunk_token_size`, gleaning, entity types, embedding model | ✅ Bắt buộc |
| `top_k`, `max_token_for_text_unit`, `response_type`, `mode` | ❌ Không |
| Sửa thuật toán ranking trong `operate.py` | ❌ Không |

Chi phí index sau khi vá bug: **~2,2 lời gọi LLM / tài liệu**. Trước khi vá là ~150.

---

## Kiến trúc code đã thêm

| File | Vai trò |
|---|---|
| `minirag/llm/gemini.py` | Backend Gemini qua endpoint OpenAI-compatible + `_KeyPool` (12 key, leaky bucket kép req/min và **token/min**) |
| `reproduce/gemini_common.py` | Nạp `.env`, parse tham số dùng chung, `build_rag()`, `build_query_param()` |
| `reproduce/Step_0_index.py` | Index. `--evidence` chọn tài liệu theo cột Evidence thay vì cắt theo alphabet |
| `reproduce/Step_1_QA.py` | Sinh câu trả lời, ghi từng dòng (resume được) |
| `reproduce/Step_2_evaluate.py` | Chấm acc/err theo **đúng giao thức bài báo**: 3 lượt độc lập, xáo thứ tự, mean ± std |
| `reproduce/Step_3_collect_context.py` | Thu context cho RAGAS (`only_need_context=True`) |
| `reproduce/Step_4_ragas.py` | Chạy 4 chỉ số RAGAS |
| `reproduce/ragas_adapters.py` | Ép RAGAS đi qua key pool, không bypass rate limiter |
| `reproduce/make_devset.py` | Đóng băng dev set 200 câu phân tầng (seed 13) |

### Sửa quan trọng ở code gốc

**`minirag/minirag.py` — bug O(N²) trong `ainsert`.** Hàm này dựng lại tập chunk từ
**mọi** tài liệu đang ở trạng thái `PROCESSED`, nên chèn N tài liệu lần lượt thì
trích xuất lại toàn bộ corpus N lần. Đã vá bằng `extracted_chunks.json`:
**~68.000 → 653 lời gọi** cho 267 tài liệu.

*Tác dụng phụ đã biết:* đồ thị **thưa hơn upstream**, vì upstream trích xuất lặp nên
vô tình gom thêm entity. Phải ghi vào phần Limitations.

---

## Rate limiting Gemini — đừng tự ý chỉnh

Ràng buộc thật là **token/phút**, không phải request/phút. Đã sweep trên pipeline thật:

| `GEMINI_TPM` | Thông lượng | Tỷ lệ 429 |
|---|---|---|
| 5000 | 17 ok/phút | 16% |
| **3000** | **26 ok/phút** | **4%** ← đang dùng |
| 2000 | 22 ok/phút | 12% |
| 1200 | 16 ok/phút | 21% |

Chat và embedding **dùng chung một pool** vì chung quota project. Client tạo với
`max_retries=0` để SDK không retry vòng trong, bỏ qua limiter.

---

## Kết quả đã có

### ⭐ Baseline chính thức — corpus 442, dev set 200 câu, 3 lượt judge

| Chỉ số | Giá trị |
|---|---|
| **Accuracy** | **57,33 ± 1,53** |
| **Error** | **21,00 ± 2,00** |
| Single (n=159) | acc 60,17 ± 1,31 · err 16,77 ± 2,21 |
| Null (n=20) | acc 50,00 ± 5,00 · err 31,67 ± 2,89 |
| **Multi (n=21)** | **acc 42,86 · err 42,86** ← điểm yếu rõ nhất |

### Baseline cũ (corpus 267) — chỉ để đối chiếu, ĐỪNG dùng làm mốc

| Chỉ số | Giá trị | Ghi chú |
|---|---|---|
| 637 câu | 66,41% / 19,15% | thiếu 175 distractor |
| dev set 200 | 65,67 ± 0,29 / 16,83 ± 1,15 | **lạc quan hơn thực tế 8,3 điểm** |

### Chẩn đoán RAGAS (n=100, corpus 267)

faithfulness 0,703 · **context_precision 0,316** · context_recall 0,560
→ context_precision thấp = retrieval kéo về nhiều chunk rác.

### Hai quan sát đáng chú ý từ baseline 442

1. **Multi-hop hỏng nặng**: tỷ lệ sai bằng tỷ lệ đúng (42,86 / 42,86).
2. **Null err 31,67%**: câu không có đáp án trong dữ liệu, hệ thống **bịa** thay vì
   nói không biết. Thêm distractor vào thì err tăng 4 điểm — nó trả lời sai một
   cách tự tin, chứ không im lặng.

*(n của Multi và Null chỉ ~20 câu, sai số lớn — đừng kết luận mạnh, cần xác nhận
trên tập đầy đủ.)*

---

## Quirks của dataset — biết trước để khỏi debug nhầm

- `query_set.csv` có **637 dòng nhưng chỉ 635 câu duy nhất** (2 dòng trùng hệt nhau, lỗi upstream)
- **Không có câu nào thiếu file evidence.** Kiểm lại 09/09/2026: cả 637 câu đều trỏ tới file có thật trong 442 tài liệu. Ghi chú cũ "68 câu thiếu file → trần điểm cứng" là **sai** — đó là số câu trỏ tới tài liệu *chưa được index* hồi corpus mới có 267 file.
- MiniRAG `.strip()` nội dung trước khi lưu → tính coverage phải hash nội dung **đã strip**

---

## Nhánh git

| Nhánh | Nội dung |
|---|---|
| `MiniRag-Base` | **Code gốc của MiniRAG, không sửa gì** (`e204d23`). Đừng commit vào đây. |
| `gemini-benchmark` | Backend Gemini + pipeline đo |
| `dev` | Nhánh làm việc hiện tại |

`main.py` có sửa đổi **không phải của Claude** (chỉ thụt lề comment) — **đừng đưa vào commit**.

---

## Lệnh hay dùng

```bash
# Index theo evidence (chỉ tài liệu thật sự cần)
python reproduce/Step_0_index.py --evidence --workingdir ./LiHua-World-gemini

# Sinh câu trả lời trên dev set
python reproduce/Step_1_QA.py --questions ./logs/devset.csv \
    --outputpath ./logs/run.csv --workingdir ./LiHua-World-gemini

# Chấm theo giao thức bài báo (3 lượt)
python reproduce/Step_2_evaluate.py --inputpath ./logs/run.csv --repeats 3
```

Cả 3 script đều **resume được** — quota hết thì hôm sau chạy lại đúng lệnh cũ, nó
bỏ qua phần đã làm.

---

## Nhóm

**Hùng** (Retrieval & Proposed Method) · **Tài** (Baseline & Failure Analysis) ·
**HuyDog** (Experiment & Evaluation). Không cần quá khắt khe về biên công việc.

Đường găng hiện tại: **Failure Taxonomy T4–T6 của Tài** — Hùng không sang được `H2`
nếu chưa có tập query lỗi đã gán nhãn.
