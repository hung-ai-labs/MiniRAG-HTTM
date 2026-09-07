# Baseline Status — MiniRAG trên LiHua-World

> Cập nhật 07/09/2026 · commit `dbfa0d1` · cấu hình đóng băng: [`baseline.yaml`](../baseline.yaml)

Tài liệu này trả lời đúng một câu hỏi cho slide: **"Nhóm đã reproduce MiniRAG đến
đâu, và kết quả hiện tại là gì?"**

---

## 1. Đã chạy được đến đâu

| Hạng mục | Tình trạng | Con số |
|---|---|---|
| Index corpus | ✅ Xong | **442 / 442** tài liệu · 503 chunks |
| Đồ thị tri thức | ✅ Xong | **770 nodes · 1.779 edges** |
| Sinh câu trả lời (QA) | ✅ Xong | **200 / 200** câu dev set |
| Chấm điểm (judge) | ✅ Xong | **601 / 601** lượt (200 câu × 3 lượt) |
| RAGAS chẩn đoán | ✅ Xong | 100 câu *(trên corpus 267 cũ)* |

### ⚠️ Phạm vi đã chạy — đọc kỹ trước khi lên slide

Baseline chính thức chạy trên **200 câu dev set**, **không phải 637 câu** của bộ đề
đầy đủ. Dev set là mẫu **phân tầng theo Type, seed 13**, cố định trong
`logs/devset.csv` — mọi thí nghiệm về sau chấm trên đúng 200 câu này để thay đổi
của hệ thống không bị lẫn với thay đổi của mẫu.

Lần chạy 637 câu duy nhất từng làm là trên **corpus 267 tài liệu cũ** — corpus đó đã
bị loại bỏ 175 tài liệu nhiễu nên **không so sánh được** với baseline hiện tại.

---

## 2. Kết quả hiện tại

### Tổng thể (dev set 200 câu, 3 lượt judge, mean ± std)

| Lượt | acc % | err % |
|---|---|---|
| 1 | 57,00 | 21,00 |
| 2 | 59,00 | 19,00 |
| 3 | 56,00 | 23,00 |
| **TỔNG** | **57,33 ± 1,53** | **21,00 ± 2,00** |

### Theo loại câu hỏi

| Loại | acc % | err % | n |
|---|---|---|---|
| Single-hop | 60,17 ± 1,31 | 16,77 ± 2,21 | 159 |
| Null *(không có đáp án trong dữ liệu)* | 50,00 ± 5,00 | 31,67 ± 2,89 | 20 |
| **Multi-hop** | **42,86 ± 0,00** | **42,86 ± 0,00** | 21 |

### Chẩn đoán RAGAS (n = 100, trên corpus 267)

| Chỉ số | Giá trị | Đọc thế nào |
|---|---|---|
| faithfulness | 0,703 | 30% nội dung câu trả lời không tựa vào context |
| **context_precision** | **0,316** | **2/3 chunk lấy về là rác** |
| context_recall | 0,560 | Gần một nửa thông tin cần thiết không được lấy về |

---

## 3. Sàn nhiễu judge — con số bắt buộc phải biết

Giao thức theo bài báo: **3 lượt chấm độc lập, xáo thứ tự câu hỏi mỗi lượt**,
báo cáo mean ± variance.

Acc dao động **3,00 điểm** giữa các lượt, **sd = 1,53**.

> **Chênh lệch dưới ~3 điểm giữa hai cấu hình là KHÔNG kết luận được** nếu chỉ chạy
> một lượt. Muốn khẳng định cải tiến thì phải rerun nhiều lượt.

Con số sàn nhiễu cũ **0,29** đo trên corpus 267 — **đã lỗi thời, đừng dùng**. Corpus
đầy đủ khó hơn nên câu trả lời mơ hồ nhiều hơn, judge đổi ý nhiều hơn.

---

## 4. So với baseline corpus 267 trước đó

| | acc | err |
|---|---|---|
| Corpus 267 (thiếu 175 distractor) | 65,67 ± 0,29 | 16,83 ± 1,15 |
| **Corpus 442 (đầy đủ)** | **57,33 ± 1,53** | **21,00 ± 2,00** |
| Chênh lệch | **−8,34 điểm** | **+4,17 điểm** |

Corpus 267 được chọn theo cột `Evidence`, tức chỉ giữ tài liệu **có chứa đáp án**.
Trong điều kiện đó retrieval gần như không thể lấy nhầm, nên điểm cao giả tạo.

Điều đáng chú ý không phải acc giảm, mà là **err tăng 4 điểm**: khi có tài liệu
nhiễu, hệ thống không im lặng mà **trả lời sai một cách tự tin**.

---

## 5. Các lỗi đã gặp và cách xử lý

| Lỗi | Ảnh hưởng | Xử lý |
|---|---|---|
| **Bug O(N²) trong `ainsert`** | Chèn N tài liệu lần lượt thì trích xuất lại toàn bộ corpus N lần | Vá bằng `extracted_chunks.json`. **~68.000 → 653 lời gọi LLM** |
| Model `gemini-2.0-flash` / `2.5-flash` trả 404 | Không chạy được | Chuyển sang `gemini-flash-lite-latest` |
| Rate limit 429 liên tục | Index chết giữa chừng | Pool 12 key + leaky bucket **theo token/phút** (ràng buộc thật), `GEMINI_TPM=3000` → 429 còn ~4% |
| Embedding Gemini bị đói quota | `entity_vdb.upsert` retry 30 phút rồi chết | Chuyển embedding về **local** `all-MiniLM-L6-v2` (384d) |
| Subset chọn theo alphabet chỉ phủ 7/637 câu | Benchmark vô nghĩa | Thêm chế độ `--evidence`, rồi cuối cùng index toàn bộ 442 |
| `ragas` xung đột `langchain-community` | Không import được | Pin `langchain-community<0.4` |
| RAGAS `TimeoutError` → NaN im lặng | Mất điểm không báo lỗi | Timeout 600 → 3600s, retry 1 → 3 |

### Lỗi còn treo, chưa xử lý

- **`kv_store_llm_response_cache.json` rỗng 0 entry** dù `enable_llm_cache=True`, sau
  hàng nghìn lời gọi. Nghi là bug upstream thứ hai. Không chặn baseline nên để sau.

---

## 6. Đặc điểm dữ liệu ảnh hưởng tới trần điểm

- `query_set.csv` có **637 dòng nhưng chỉ 635 câu duy nhất** — 2 dòng trùng hệt nhau.
- **68 câu có cột `Evidence` trỏ tới file không tồn tại** trong dataset. Không hệ
  thống nào trả lời đúng được → đây là **trần điểm cứng**, không phải lỗi của MiniRAG.
- MiniRAG `.strip()` nội dung trước khi lưu, nên tính coverage phải hash nội dung
  **đã strip** (nhầm chỗ này từng làm tôi báo sai 50/442 thay vì 267/442).

---

## 7. Lệnh chạy lại

```bash
python reproduce/Step_0_index.py --workingdir ./LiHua-World-gemini
```

```bash
python reproduce/Step_1_QA.py --workingdir ./LiHua-World-gemini --questions ./logs/devset.csv --outputpath ./logs/baseline442_devset.csv
```

```bash
python reproduce/Step_2_evaluate.py --inputpath ./logs/baseline442_devset.csv --repeats 3
```

Cả ba script đều **resume được**: hết quota thì hôm sau chạy lại đúng lệnh cũ, nó bỏ
qua phần đã làm. Toàn bộ tham số retrieval để **mặc định thư viện** — baseline phải
là MiniRAG nguyên bản.

---

## 8. Sai lệch so với bài báo (đưa vào Limitations)

| Hạng mục | Nhóm dùng | Bài báo dùng |
|---|---|---|
| LLM sinh câu trả lời | `gemini-flash-lite-latest` | `gpt-4o-mini` |
| LLM chấm điểm | `gemini-flash-lite-latest` | `gpt-4o` |
| Embedding | `all-MiniLM-L6-v2` (local) | giống nhau |
| Số câu chấm | 200 (dev set phân tầng) | 637 |

Đồ thị của nhóm **thưa hơn upstream** do bản vá O(N²): upstream trích xuất lặp lại
nên vô tình gom thêm entity. Đây là đánh đổi có ý thức — không vá thì không chạy nổi.

**Lần chạy cuối dự án** sẽ lặp lại đúng `baseline.yaml` trên OpenAI (`gpt-4o-mini` +
judge `gpt-4o`, ~$10 cho 2 lượt full) để có con số so sánh trực tiếp với bài báo.
