# C1/B2 context dev401 — kết quả ngày 01/11/2026

Đăng ký trước: **DEV401-CTX-C1-001** trong [EXPERIMENT_HISTORY.md](EXPERIMENT_HISTORY.md).
Cấu hình theo [HANDOFF_2WIKI_QWEN.md §1.5](HANDOFF_2WIKI_QWEN.md) và
[RUN_2WIKI_DEV20_TEST80.md](RUN_2WIKI_DEV20_TEST80.md): C0=GROUP_BASE;
C1=B2_FULL, RRF(k=60) của vector top30 và BM25 top30, giữ bảng Entities từ đồ thị.
Đây là đo cấu hình có sẵn của dự án, không phải đề xuất một phương pháp mới.

## Điều kiện và kiểm chứng

- C1 hoàn tất **401/401 context, tất cả status ok**, worker1, seed101. Chỉ dùng internal_dev.
- Run mới `runs/2wiki/analysis/c1-context-dev401-s101`; không ghi đè baseline/index.
- Keyword cache sao chép nguyên byte từ `baseline-dev-s101-c4/kw_s101.jsonl`.
- Run manifest C0/C1 khớp toàn bộ: index, questions, registration, serving declaration,
  seed, concurrency, endpoint hash, source hash và retrieval environment.
- **401/401** bảng Entities, graph candidate list và vector candidate list khớp nhau.
  Thay đổi nằm ở fusion/chọn Sources của cấu hình C1.
- Embedding local384d, Hugging Face/Transformers offline. Pha context đặt LLM thành
  hàm cấm gọi, đọc keyword cache. Không sinh answer, gọi Gemini hay thuê GPU Modal.
- Không đổi `baseline.yaml`, protocol đăng ký QA cũ, rubric/nhãn judge, top-k,
  token budget, prompt hoặc model; chưa mở tập test1599.

## Kết quả truy hồi

Gold supporting titles chỉ dùng **sau** retrieval để phân tích. Đếm document theo
chunk.full_doc_id trong Sources, không chỉ tìm tên/chuỗi đáp án trong context.

| Chỉ số | C0 baseline | C1 B2 |
|---|---:|---:|
| Lượt supporting document có trong Sources / 996 lượt cần | 601 | 672 |
| Recall theo lượt supporting title, micro (proxy) | 60,34% | 67,47% |
| Câu có đủ mọi supporting document /401 | 137 (34,16%) | 154 (38,40%) |
| Mapped supporting-fact substring hits /995 (proxy) | 601 | 672 |
| Sources token trung vị / p95 | 3.836 / 3.987 | 3.924 / 3.994 |
| Số source chunk trung vị / p95 | 27 / 30 | 42 / 55 |
| Retrieval giây trung vị / p95 | 1,33 / 8,06 | 1,51 / 10,42 |

Ngân sách Sources cùng tối đa4.000 token; C1 giữ nhiều chunk ngắn hơn, không phải
được tăng token budget. Entity token trung vị707/p95820 ở cả hai bên (bao gồm
serialization, không diễn giải là thay token budget Entities).

Theo số supporting document tìm được, **87 câu tăng /25 câu giảm /289 câu giữ nguyên**.
Theo tiêu chí đủ tất cả document, **32 thiếu→đủ /15 đủ→thiếu**, net+17 câu.
McNemar chính xác hai phía cho **proxy đủ document**: p=0,01862. Đây không phải
McNemar về câu trả lời đúng và không chứng minh accuracy tăng.

| Loại câu | n | C0 đủ supporting document | C1 đủ supporting document |
|---|---:|---:|---:|
| bridge_comparison | 97 | 0 | 1 |
| comparison | 96 | 85 | 94 |
| compositional | 159 | 29 | 37 |
| inference | 49 | 23 | 22 |

Không viết C1 cải thiện mọi loại câu: inference giảm số câu đủ tài liệu; nhóm
bridge_comparison vẫn gần như không có đủ cả bốn tài liệu cần cho hai nhánh.

## Ví dụ tăng và giảm

- `0729da3c0bde11eba7f7acde48001122`: C1 bổ sung Yolande of Valois, chuyển thiếu→đủ.
- `101a05820bdd11eba7f7acde48001122`: bổ sung Jacques Rivette, chuyển thiếu→đủ.
- `1837ca440bdb11eba7f7acde48001122`: bổ sung Willi Forst, chuyển thiếu→đủ.
- `1b91365c08a311ebbd7bac1f6bf848b6`: mất Hermann Friedrich Graebe, chuyển đủ→thiếu.
- `1cf4dbe80baf11ebab90acde48001122`: mất Marie Leszczyńska, chuyển đủ→thiếu.
- `4a9bfe280baf11ebab90acde48001122`: mất Peter II of Portugal, chuyển đủ→thiếu.

Toàn bộ cặp query và gained/lost titles nằm trong `comparison/per_query.jsonl`.
Không loại các câu annotation đáng ngờ đã nêu ở
[BASELINE_DEV401_FAILURE_REVIEW.md](BASELINE_DEV401_FAILURE_REVIEW.md).

## Giới hạn và bước tiếp theo

Document có mặt không bảo đảm đoạn cần thiết có mặt hay câu trả lời suy ra được.
Supporting sentence có thể sai vị trí/ngữ nghĩa; exact substring proxy không thay
thế rà thủ công. Cả401 context/Sources đều khác byte giữa C0 và C1, nên chưa có
câu trả lời C0 nào được tái dùng trực tiếp cho C1 theo tiêu chí context bất biến.

Latency hai đợt đo khác thời điểm, có thể khác cache/CPU contention: chỉ mô tả,
không dùng để tuyên bố nhanh/chậm hơn một cách có kiểm soát. Một seed, một corpus,
không phải kết quả benchmark cuối. Chưa kiểm tương đương802 context cho runner
acceleration: đợt này dùng runner phased thông thường.

Coverage cho thấy có lý do tiếp tục phép đo B2 đã lên kế hoạch, nhưng chưa có
accuracy C1. Bước GPU tiếp theo là sinh401 đáp án C1 trên các context này, cùng
Qwen/seed101/QA1024, rồi judge cùng model/rubric ba lượt. Trước đó phải đối soát
Billing còn lại trong trần thí nghiệm$25; thông tin giao diện quay về$30 credit
không xác nhận usage đã dùng. Không đổi thuật toán/weight/top-k theo kết quả này.
Các ablation và ba lượt sinh vẫn cần theo handoff trước kết luận khoa học.

## Tái tạo

`python reproduce/research/compare_2wiki_dev_contexts.py`

Lệnh chỉ đọc kết quả đã hoàn tất và xuất `comparison/summary.json`,
`comparison/per_query.jsonl`. Có kiểm đủ401 ID, manifest/cache khớp, context hash,
trace query, số source rows/chunk IDs và fusion đúng cấu hình; summary lưu hash
các nguồn. McNemar proxy: `2*sum(comb(47,k) for k in range(16))/2**47`.
