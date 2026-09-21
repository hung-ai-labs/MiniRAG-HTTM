# CE3 — Đăng ký trước: một backend suy luận CPU cho **đúng model CE1**

> 21/09/2026 · Viết **trước khi đo** bất kỳ độ trễ hay điểm số nào của backend mới.
> Chỉ offline: không sinh, không chấm, không 637, không tầng D. B2 đông lạnh vẫn là bản dự phòng chính thức.
> **Không mở lại hướng xếp hạng lại tất định.** CE1 vẫn là kết quả lịch sử; quyết định STOP ở tầng dev **không bị diễn
> giải lại**.

## Câu hỏi của giai đoạn này

*"Có chạy được **cùng một model CE1** nhanh hơn trên CPU mà **không đổi thứ hạng** một cách đáng kể không?"*

Không đổi kiến trúc model. Không fine-tune. Không đổi BM25 / vector / RRF / A1@4000 / parser / generator / prompt /
embedding.

## Phase 0 — mốc đã xác nhận lại (21/09/2026, dùng hiện vật đã lưu, không dựng lại)

| | |
|---|---|
| B2 đông lạnh | `ce1_off_dev_ctx.jsonl` hash trùng `logs/screening/b2/answers.jsonl` **198/198** |
| Model CE1 | `cross-encoder/ms-marco-MiniLM-L6-v2` @ `233902d25c440f23af6f7d6e94d2946bac0bee0a` |
| Tokenizer | `BertTokenizer`, vocab 30.522, `model_max_length` 512 |
| Chính sách cắt | MaxP, cửa sổ `512 − len(q) − 3`, bước `cửa sổ // 2`, lấy max |
| Lô · thiết bị | 32 · CPU float32 |
| Điểm CE1 đã lưu | `logs/rerank/ce1_scores.json` — 18.723 cửa sổ, 200 câu |
| Thứ hạng CE1 đã lưu | `ce1_on_dev_ctx.jsonl` (`post_rerank_ids`, `chunk_ids`, `context_sha256`) |
| 20 ca độ sâu xếp hạng | xác nhận lại = 20 · CE1 cứu được **11** (`logs/rerank/ce1_refs.json`) |
| Giữ đủ bằng chứng dev | **151 → 162** trên 180 câu |
| An toàn Null | sự kiện phân biệt 10,5 → 7,5 · 4/20 câu có chunk mới khớp đủ thực thể · L002 8→3, L052 1→1, L055 4→16 |
| Độ trễ CE1 trên CPU | p50 **1830** · p95 **2731** · **max 3429** ms · 5/200 câu vượt 3000 |

## Lựa chọn **một** backend, chốt trước khi đo

**ONNX Runtime 1.30.0, `CPUExecutionProvider`, float32, không lượng tử hoá.**

| | |
|---|---|
| Xuất model | `torch.onnx` từ đúng checkpoint đã ghim, opset 17, trục động cho batch và độ dài |
| Execution provider | **chỉ `CPUExecutionProvider`** — `CoreMLExecutionProvider` có sẵn nhưng **bị cấm dùng** ở đây: nó đẩy tính toán sang GPU/ANE, tương đương việc lén đổi sang MPS để cứu số CPU |
| Tối ưu đồ thị | `ORT_ENABLE_ALL` (mặc định của ORT) |
| Luồng | `intra_op_num_threads = 6`, `inter_op_num_threads = 1` — bằng đúng `torch.get_num_threads()` của lượt CE1 gốc, để phép so là công bằng chứ không phải lợi thế luồng |
| Lô · MaxP · tokenizer | **không đổi** so với CE1 |

**Vì sao chọn cái này, lý lẽ trước khi có số:** trong các phương án nêu ra, ORT fp32 là phương án **gần như không mất mát
số học** (chỉ sắp xếp lại đồ thị và hợp nhất kernel), nên có cơ hội cao rơi vào nhóm A. Mức cần cải thiện cũng nhỏ:
max 3429 → cần ≤ 3000, tức **−12,5%**, nằm sâu trong dải tăng tốc thường thấy của ORT trên BERT ở CPU.

**Không đo nhiều phương án rồi chọn cái thắng.** Lượng tử hoá INT8 động **không** nằm trong giai đoạn này. Nếu ORT fp32
trượt cổng độ trễ thì đi sang Phase 2 (CE-lite) theo đúng thứ tự đã định, **không** quay lại thử INT8 để cứu.

## Dung sai "tương đương thứ hạng" — chốt trước khi so sánh

Đo trên toàn bộ 9.351 cặp (câu hỏi, chunk) của dev 200:

| Nhóm | Điều kiện |
|---|---|
| **A — tối ưu hệ thống, gần như y hệt** | `max |Δđiểm| ≤ 1e−3` **và** thứ tự sau xếp lại trùng **200/200** câu **và** `chunk_ids` sau A1 trùng **200/200** **và** `context_sha256` trùng **200/200** |
| **A− — y hệt trừ hoà điểm sát nhau** | `max |Δđiểm| ≤ 1e−3`, `chunk_ids` trùng **≥ 198/200**, và mọi khác biệt truy được về cặp điểm cách nhau < 1e−3 |
| **B — đổi thứ hạng** | mọi trường hợp còn lại |

**Nếu rơi vào nhóm B:** **không** được gọi là "vẫn là CE1". Phải coi là **biến thể truy hồi mới**, cần phân tích an toàn
offline mới (20 ca, giữ bằng chứng, Single/Multi/Null, ba chunk gây nhầm) trước khi bàn tiếp. Không tự động đẩy tiếp.

## Cổng độ trễ — giữ nguyên, không nới sau khi thấy kết quả

**Mốc vận hành vẫn là `max ≤ 3000 ms/câu` trên CPU**, đúng như cổng 8 của CE1. Báo cáo đủ p50 / p95 / max cho phần xếp
lại, cộng tổng B2 + xếp lại p50 / p95 / max, thời gian nạp model **đo riêng**, và bộ nhớ nếu đo được dễ.

## Luật quyết định Phase 1 — chốt trước khi đo

| Kết quả | Hành động |
|---|---|
| Nhóm A hoặc A− **và** max ≤ 3000 ms | **ĐẠT** → dừng, báo cáo, **không** sang CE-lite |
| Nhóm A hoặc A− **nhưng** max > 3000 ms | trượt độ trễ → sang Phase 2 (CE-lite), chỉ offline |
| Nhóm B | không gọi là CE1; báo cáo như biến thể mới cần phân tích an toàn riêng; không đẩy tiếp |

Trượt hết → tắt chế độ thí nghiệm, **giữ B2**. Không sửa B2 để chiều thí nghiệm.

## Bất biến giữ nguyên

Cờ tắt mặc định · đường đi B2 không đụng tới · cờ tắt thì hash B2 phải trùng khít · reranker hỏng thì **ném lỗi**,
không âm thầm trộn B2 với câu đã xếp lại trong cùng một lượt đánh giá · không nhãn vàng lúc chạy · không thêm lời gọi LLM.
