# Baseline 2Wiki dev401: initial offline failure review

Inputs: C0, seed 101, `baseline-dev-s101-c4`; judge `baseline-dev-s101-fl35-v2`, Gemini `gemini-3.5-flash-lite`, rubric v2. Only internal dev401 is used. No held-out questions, inference calls, or index changes.

## Completed evaluation

All 1,203 judgments are valid. Judge-pass mean ± sample SD: accurate 35.33 ± 0.29%, error 25.02 ± 0.29%, neither 39.65 ± 0.00%. These SDs describe judge variation on one generation, not uncertainty across generations.

| Question type | n | Majority accurate | Majority error | Majority neither |
|---|---:|---:|---:|---:|
| comparison | 96 | 66 | 28 | 2 |
| bridge_comparison | 97 | 46 | 30 | 21 |
| compositional | 159 | 20 | 20 | 119 |
| inference | 49 | 10 | 21 | 18 |
| Total | 401 | 142 | 99 | 160 |

## Evidence diagnostics, not causal labels

Run `python reproduce/research/analyze_2wiki_dev_failures.py` to recreate ignored artifacts under `runs/2wiki/analysis/baseline-dev-s101-v2/`:

- `diagnostics.jsonl`: all 401 records joined by query ID, including question, answer, gold evidence and retrieved context.
- `manual_review_sample.jsonl`: 37 deterministic cases, up to five per type × error/neither stratum. This stratified sample is for inspection; its frequencies do not estimate population failure rates.
- `diagnostics_summary.json`: counts and coverage proxy.

The proxy checks normalized exact supporting-fact substrings in the Sources CSV only. Formatting, truncation, paraphrases and evidence-mapping errors can create misses. It does not measure semantic sufficiency, inspect graph paths, or establish which retrieval stage failed.

| Majority label | All gold evidence facts matched | Some matched | None matched |
|---|---:|---:|---:|
| accurate | 78 | 63 | 1 |
| error | 36 | 60 | 3 |
| neither | 23 | 103 | 34 |

Both incomplete retrieved evidence and failure to use available evidence merit investigation; neither alone explains all failures.

## Initial examples inspected

- `39fa366e0bd911eba7f7acde48001122`: Gilbert Dying to Die → director birth date. The answer identifies Maurice Elvey but does not give his birth date. Only part of the supporting evidence matches Sources. Inspect the missing director biography before assigning a retrieval stage.
- `8398f07e0bdb11eba7f7acde48001122`: Magic Hunter → director's father. The answer identifies Ildikó Enyedi but refuses the father relation; only part of the supporting evidence matches Sources. This is a candidate missing second-hop evidence case, pending context review.
- `07aae62e0baf11ebab90acde48001122`: Empress Wang → mother-in-law. Both supporting facts occur in Sources: Wang is Gaozong's wife, and Gaozong is the son of Empress Zhangsun. The answer nevertheless says the mother-in-law cannot be determined. This example supports an evidence-use/generation failure, without proving that prompt changes would solve it.
- `511af4e80baf11ebab90acde48001122`: Archduchess Rosa → mother-in-law has a gold sentence index out of range. Audit the original document before assigning a retrieval failure; incomplete gold mapping is a confounder.

## Rà soát tiếp ngày 01/11/2026

Đã rà 37 câu mẫu bằng agent, lưu nhận xét từng ID ở `docs/research/dev401_review_annotations.json`. Đây không phải chấm độc lập bởi con người; nhãn Gemini và điểm chính thức được giữ nguyên.

| Nhóm quan sát trong mẫu | Số câu |
|---|---:|
| Sources thiếu ít nhất một tài liệu supporting | 23 |
| Có bằng chứng nhưng câu trả lời bỏ qua hoặc suy luận sai | 11 |
| Cần đối soát dữ liệu/diễn giải đáp án | 3 |

Các nhóm trên mô tả quan sát, không thay thế taxonomy nhân quả sáu giai đoạn. Mẫu phân tầng có chủ đích nên không ngoại suy tỷ lệ 23/37 lên toàn bộ tập. `reviewed_sample.jsonl` chứa nhận xét và context đầy đủ; `manual_stage=causal_stage_unresolved` giữ rõ giới hạn kết luận. File mẫu gốc vẫn để `unreviewed`, tách khỏi bản đã rà.

### Đối chiếu log trên toàn bộ 259 câu error/neither

Đã ghép log retrieval bằng **hash context và câu hỏi**, rồi nối chunk → document ID → supporting title. Không chạy lại retrieval. Những phép đếm sau là chẩn đoán theo tài liệu, không phải độ đầy đủ ngữ nghĩa:

| Loại câu | error + neither | Có ít nhất một supporting title vắng khỏi Sources |
|---|---:|---:|
| bridge_comparison | 51 | 51 |
| comparison | 30 | 5 |
| compositional | 139 | 120 |
| inference | 39 | 24 |
| Tổng | 259 | 200 |

- 293 lượt supporting title bị thiếu trên 200 câu này đều **không có trong `ranked_ids` trước khi cắt Sources**. Không quan sát được trường hợp supporting document có trong ranked list rồi mất sau cắt ở tập lỗi này. Điều này không chứng minh cắt token vô hại: một chunk giữ lại vẫn có thể thiếu câu cần thiết.
- 72/293 lượt thiếu, thuộc **67 câu**, lại có tài liệu trong `vector_ids` đã ghi sẵn. Có tín hiệu cụ thể để kiểm tra việc phối hợp danh sách ứng viên; chưa chứng minh fusion sẽ giữ được tài liệu sau giới hạn token hoặc tăng accuracy.
- Chưa đủ căn cứ gán tất cả 200 câu cho lỗi path discovery hay extraction. Cần trace sâu các khâu đó nếu muốn một taxonomy nhân quả đầy đủ.

### Các vấn đề dữ liệu phải tách riêng

- `fd4bc65e0bda11eba7f7acde48001122`: hỏi nơi sinh Ning Hao, nhưng supporting sentence nói về **Taiyuan Film School**; đoạn biography trong corpus không nêu nơi sinh. Không coi proxy “all facts matched” là bằng chứng model có đủ thông tin.
- `31218d120bde11eba7f7acde48001122`: hỏi nơi sinh Albert II, nhưng supporting sentence nói ông **không sở hữu Prince's Palace**. Cụm đáp án xuất hiện trong context không có nghĩa context xác nhận nơi sinh.
- `f4b202740bda11eba7f7acde48001122`: gold là “French”, biography ghi “French-Canadian”, answer đoán “Canadian”. Cần đối soát cách diễn giải quốc tịch; không tự đổi nhãn hoặc loại câu.
- `5a5718140bde11eba7f7acde48001122`: supporting index nói về phim thất bại, nhưng full Sources thực sự có câu Brij chết ở **Mumbai**. Qwen vẫn báo thiếu thông tin. Bombay/Mumbai là điểm cần kiểm tra alias khi đối soát, không đổi rubric đang dùng.
- `511af4e80baf11ebab90acde48001122`: index supporting vượt số câu; corpus vẫn nêu mẹ Philipp Albrecht là Margarete Sophie. Tài liệu này vắng khỏi Sources, nên đồng thời có lỗi annotation supporting và quan sát thiếu tài liệu truy hồi.

## Hướng thử nghiệm dev tiếp theo

**Observed problem:** trong tập error/neither, 200/259 câu thiếu supporting document trong Sources; 67 câu có ít nhất một tài liệu thiếu mà danh sách vector hiện có đã tìm được.

**Hypothesis:** phối hợp ứng viên truy hồi có thể bổ sung bằng chứng bị danh sách baseline bỏ qua, nếu giữ được chúng trong cùng ngân sách context. Đây là giả thuyết về retrieval, không bảo đảm sửa 11 lỗi sử dụng bằng chứng trong mẫu.

**Mechanism candidate:** đánh giá cấu hình C1 `vector_bm25` đã tồn tại trong repo đối chiếu C0; không gọi đổi runner/acceleration là đóng góp khoa học mới. Kết quả hiện tại chỉ hỗ trợ kiểm tra fusion như một ứng viên, chưa chứng minh riêng BM25 cần thiết.

**Controlled experiment:** tạo context C1 trên cùng dev401 bằng keyword cache seed101, index Qwen hiện có, embedding và ngân sách Sources không đổi. Đầu tiên so coverage theo tài liệu và các ví dụ dữ liệu đã gắn cờ bằng CPU; không đưa gold vào retrieval/generation. Không đổi top-k, prompt, temperature hay model trong phép so sánh. Sau đó mới cân nhắc sinh/chấm C1 nếu còn ngân sách, dùng cùng judge/rubric và ghép query_id để báo b/c cùng McNemar. Đánh giá cuối phải lặp lượt sinh và có ablation vector-only để tách hiệu ứng BM25/đồ thị; một cặp seed101 chưa đủ kết luận cải tiến khoa học.

**Measurable effect:** báo supporting-document coverage (proxy), acc/error/neither, số token context, thời gian retrieval và generation, cùng số request. Nếu danh sách mở rộng không cải thiện coverage trong giới hạn context, dừng hướng đó trước khi tốn GPU sinh đáp án.

Đây là kế hoạch nghiên cứu dev, chưa phải đăng ký phương pháp cuối. Giữ tập test1599 chưa mở cho đến khi chốt phương pháp/protocol. Kiểm tra Billing trước GPU: số cuối người dùng cung cấp trước QA là $17.74/$25, không còn đại diện chi phí hiện tại.

### Tái tạo và kiểm chứng

Chạy script offline ở trên đã xác nhận đủ 401 ID duy nhất, cùng tập ID giữa question/gold/context/answer/judge, đủ 37 annotation khớp mẫu, mọi context có log hash/câu hỏi tương ứng và mọi chunk ID có trong index. Đầu ra `review_summary.json` lưu hash các nguồn, annotation và script; `trace_summary.json` lưu thống kê giai đoạn ứng viên. Không có lời gọi API, sửa index hay sửa kết quả đánh giá.
