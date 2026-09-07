# CLAUDE.md — MiniRAG Research Project

Hướng dẫn cho Claude khi làm việc trong repo này. Đọc kèm [ROADMAP.md](ROADMAP.md).

---

## ⚠️ QUY TẮC BẮT BUỘC

### 1. Hiện tại CHỈ dùng Gemini. OpenAI để cuối dự án.

Toàn bộ giai đoạn phát triển và thử nghiệm chạy trên **Gemini free tier** . Chỉ khi **đã chốt Proposed Method và chuẩn bị viết báo cáo
cuối** mới chạy lại full trên OpenAI để có con số so sánh trực tiếp với bài báo.

| | Giai đoạn phát triển (bây giờ) | Lần chạy cuối (cuối dự án) |
|---|---|---|
| Generation | `gemini-flash-lite-latest` | `gpt-4o-mini` (như bài báo) |
| Judge | `gemini-flash-lite-latest`, 3 lượt | `gpt-4o`, 3 lượt |
| Embedding | local `all-MiniLM-L6-v2` (384d) | giữ nguyên local |
| Chi phí | 0đ | ~$10 cho 2 lượt full |

**Không tự ý gọi OpenAI API.** Mọi thí nghiệm — sweep tham số, ablation, đo noise,
RAGAS — đều chạy Gemini. Con số Gemini dùng để **so sánh tương đối** (baseline vs
cải tiến); con số OpenAI dùng để **so sánh tuyệt đối** với bài báo.

### 2. Chưa cải tiến khi chưa có baseline trung thực.

Yêu cầu đứng của chủ dự án: *"chưa được cải tiến vội nhé, tôi cần benchmark giống
bản gốc trước để lên plan làm cải tiến"*. Không sửa `operate.py`, không đổi tham số
retrieval, không thử ý tưởng mới cho tới khi baseline corpus 442 tài liệu hoàn tất
và `baseline.yaml` được đóng băng.

### 3. Quy tắc đọc kết quả (sàn nhiễu judge = sd 0,29 điểm)

| Mức thay đổi | Kết luận |
|---|---|
| +4 đến +6 điểm | Gần như chắc chắn có cải thiện → tiếp tục |
| ~+1 điểm | Phải đo generation noise trước khi kết luận |
| < 0,6 điểm | **Không kết luận được** — nằm trong nhiễu của judge |

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

| Chỉ số | Giá trị | Ghi chú |
|---|---|---|
| Baseline acc / err (637 câu, corpus 267) | **66,41% / 19,15%** | corpus thiếu 175 distractor → **lạc quan hơn thực tế** |
| Baseline dev set 200 câu | **65,67 ± 0,29 / 16,83 ± 1,15** | 3 lượt judge |
| Sàn nhiễu judge | sd acc **0,29 điểm** | |
| RAGAS (n=100) | faithfulness 0,703 · **context_precision 0,316** · context_recall 0,560 | context_precision thấp = nhiều chunk rác |
| Baseline corpus đầy đủ 442 | 🔄 đang chạy | index xong, đang QA |

---

## Quirks của dataset — biết trước để khỏi debug nhầm

- `query_set.csv` có **637 dòng nhưng chỉ 635 câu duy nhất** (2 dòng trùng hệt nhau, lỗi upstream)
- **68 câu có cột `Evidence` trỏ tới file không tồn tại** → không hệ thống nào trả lời đúng được, đây là trần điểm cứng
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
