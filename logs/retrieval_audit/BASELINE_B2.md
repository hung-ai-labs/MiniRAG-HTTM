# Mốc B2 đông lạnh và kiểm truy hồi offline — 19/09/2026

> Giai đoạn 0–2 viết xong và luật dừng ở cuối file chốt **trước** khi chạy `simulate.py`.
> Không gọi sinh, không gọi giám khảo, không sửa `minirag/`.

## Giai đoạn 0 — B2 như đang chạy

| Thành phần | Giá trị | Chỗ trong code |
|---|---|---|
| Công tắc | `MINIRAG_CHUNK_FUSION=vector_bm25` | `minirag/operate.py`, `_build_mini_query_context`, khối `fusion = os.environ.get(...)` |
| Vector | `chunks_vdb.query(originalquery, top_k = top_k/2 = 30)`, MiniLM-L6 384d, câu hỏi nguyên văn | ngay trên khối trộn |
| BM25 | `BM25Index.rank(originalquery, 30)`, k1 = 1,2, b = 0,75, `[a-z0-9]+`, bỏ STOP | `minirag/bm25.py`; chỉ mục dựng một lần trong bộ nhớ (`_bm25_index`) |
| Trộn | `_rrf_fuse(vector_ids, bm25_ids)`, k = 60, hoà điểm giữ thứ tự xuất hiện | `_rrf_fuse` |
| Ứng viên | danh sách id chunk, trung vị 48 (≤ 60) | `final_chunk_id` |
| Cắt A1@4000 | `truncate_list_by_token_size(..., key = nội dung chunk, 4000)` — tiktoken gpt-4o, **dừng ở chunk đầu tiên làm tràn** | `minirag/utils.py:189` |
| Context | bảng Entities (đồ thị, ≤ 500 token) + Sources (chunk nguyên văn theo thứ tự trộn) | cuối `_build_mini_query_context` |
| Log | `MINIRAG_CONTEXT_LOG`: `chunk_ids`, `ranked_ids`, `vector_ids`, `bm25_ids`, `context_sha256`, `sources_tok`, `retrieval_ms` | cùng hàm |
| Tham số khác | top_k 60, max_token_for_text_unit 4000, answer-type fix bật, parser từ khoá qua cache sàng lọc | `reproduce/screening/screen_variant.py` `BASE_ENV` |

Đồ thị vẫn chạy trong B2: nó dựng bảng Entities và quyết định câu có context hay không (`results_node`/`results_edge`
rỗng → None). Nó **không** tham gia xếp hạng chunk.

**Hiện vật B2:** tầng D `logs/stage_d/b2_s{101,202,303}{.csv,_judged.csv,_ctx.jsonl}`; sàng lọc dev
`logs/screening/b2/answers.jsonl` (1 lượt sinh seed 20260914, 1 lượt chấm, có `context_sha256`).

**Kiểm đồng nhất:** `reproduce/retrieval_audit/dump_contexts.py` dựng lại toàn bộ dev 200 offline (parser đọc cache,
`MINIRAG_KW_CACHE_ONLY=1`, 0 lời gọi LLM) → `context_sha256` **trùng 198/198** câu có context với B2 đông lạnh; 2 câu
còn lại vốn không có context. Tái dựng A1 từ `ranked_ids` khớp `chunk_ids` 200/200.

## Giai đoạn 1 — chẩn đoán (`diagnose.txt`, 180 câu dev có evidence)

| Chỉ số | B2 |
|---|---:|
| chunk đáp án có trong ứng viên | 203/207 = **98,1%** |
| chunk đáp án còn sau A1 | 178/207 = 86,0% |
| câu đủ mọi chunk đáp án: trong ứng viên → sau A1 | 97,8% → **83,9%** (151/180) |
| Single / Multi đủ đáp án sau A1 | 85,5% / 71,4% |
| hạng chunk đáp án đầu tiên | trung vị 1 · p75 3 · p90 10 |
| số chunk: ứng viên / vào Sources | trung vị 48 / 8 (min 3, max 33) |
| token Sources | trung vị 3.602; ngân sách bỏ trống do A1 dừng sớm trung vị 398 |
| chunk trong Sources: cả hai nguồn / chỉ vector / chỉ BM25 | 65% / 19% / 16% |
| chunk đáp án trong ứng viên: cả hai / chỉ BM25 / chỉ vector | 85% / 11% / 3% |
| cặp chunk gần trùng (Jaccard ≥ 0,6) | 343 cặp nhưng chỉ ở 8/200 câu |

**Bảng tần suất thất bại — 29 câu không đủ đáp án sau A1:**

| Kiểu thất bại | Số câu |
|---|---:|
| chunk đáp án có trong ứng viên nhưng **bị A1 cắt** | **25 (86%)** |
| chunk đáp án không có trong ứng viên | 4 (14%) |
| — trong 25 câu bị cắt: chunk dài (≥ 800 token) chiếm ≥ 1/3 số token đứng trước chunk đáp án | 21/25 |
| — trong 25 câu bị cắt: **chính chunk đáp án dài 1.200 token** | 16/25 |
| — trùng lặp / gần trùng là nguyên nhân | không đáng kể (8/200 câu có cặp gần trùng) |
| — nhiễu đồ thị | không áp dụng: B2 không dùng đồ thị để xếp chunk |

Chunk dài 1.200 token là giới hạn cắt chunk khi index (hội thoại dài bị cắt thành nhiều mảnh 1.200 token). 72/207 chunk
đáp án ≥ 800 token; 138/200 câu có ít nhất một chunk dài trong Sources; chunk ≥ 800 token chiếm trung vị 37% token Sources.
Khi thứ tự trộn đưa 3 chunk dài lên đầu, Sources chỉ còn 3 chunk. Nguồn (vector / BM25 / cả hai) của chunk chiếm chỗ chia
đều — không có "bộ nhiễu từ vựng" hay "bộ nhiễu ngữ nghĩa" trội. Proxy "cùng người nói, khác thời điểm" khớp 98% chunk
chiếm chỗ vì Li Hua có mặt trong hầu hết hội thoại — không dùng được làm phân loại.

**Nút thắt:** độ chính xác của **đơn vị bằng chứng** — mỗi chunk dài đưa vào 1.200 token trong khi phần liên quan tới
câu hỏi thường chỉ vài lượt thoại. Recall không phải vấn đề (98%).

**Null (chẩn đoán):** lần kiểm độ phủ trước (`giai_phap_null_b2_do_phu.md`) cho thấy chunk gây nhầm của 9 câu Null sai
nằm trong top Sources của B2, cùng chủ đề và thường khớp từ khoá — cùng họ "chunk liên quan chủ đề chiếm chỗ" nhưng
không phải hiện tượng chunk dài. Cơ chế dưới đây **không** được thiết kế để sửa Null; Null là ràng buộc an toàn.

## Giai đoạn 2 — cơ chế chọn: cửa sổ trong chunk dài

Chọn theo chẩn đoán, chưa nhìn kết quả mô phỏng:
- *Lấp ngân sách thừa (bỏ qua chunk tràn, xét tiếp)* bị loại: không cứu được 16/25 ca mà chính chunk đáp án dài 1.200 token;
  trần tối đa ~9 câu.
- *Giảm trùng lặp / đa dạng hoá* bị loại: trùng lặp chỉ ở 8/200 câu.
- *Hiệu chỉnh vector–BM25* bị loại: chunk chiếm chỗ chia đều giữa các nguồn.

**Định nghĩa (khoá):** giữ nguyên danh sách ứng viên và thứ tự RRF của B2. Chunk dài hơn **W = 400 token** được thay bằng
một cửa sổ liền mạch ≤ W token: chấm mỗi dòng bằng tổng idf BM25 (chỉ mục chunk hiện có, cùng tokenizer và STOP) của các
từ câu hỏi xuất hiện trong dòng; lấy dòng cao nhất (hoà → dòng đầu), mở rộng sang dòng kề có điểm cao hơn (hoà → dòng sau)
đến khi chạm W; giữ dòng `Time:` làm tiêu đề. Sau đó A1@4000 **y hệt** B2. Không gọi LLM, không đọc Type/Evidence/đáp án,
không index lại, không đổi prompt, không đổi ngân sách.

W = 400 chọn trước: gần p75 độ dài chunk ngắn tự nhiên (trung vị 215–274), để một chunk dài tốn ngang một chunk thường.
Không quét W.

## Luật dừng — chốt trước khi chạy mô phỏng

Chỉ số chính có hai tầng, vì "id chunk đáp án có trong context" không còn đủ khi chunk bị rút thành cửa sổ:
- **P (chính):** tập câu có đáp án vàng trích được nguyên văn từ chunk đáp án — đáp án (chuẩn hoá) có trong Sources không.
- **E:** 180 câu có evidence — mọi chunk đáp án có mặt (nguyên chunk hoặc cửa sổ).

Đi tiếp khi **đạt cả sáu**:
1. P: net > 0 và McNemar p < 0,05.
2. E: net ≥ +9 câu và McNemar p < 0,05.
3. Multi: net ≥ −1 ở cả P và E.
4. Token Sources trung vị trong ±5% của B2; không câu nào vượt 4.000.
5. Context đổi ở ≥ 20/198 câu.
6. An toàn Null: số sự kiện phân biệt (giá trị `Time:` khác nhau) trong Sources của câu Null tăng không quá 25% ở trung vị.
   Nhiều sự kiện hơn trong cùng ngân sách = nhiều mảnh thật hơn để ghép thành sự kiện sai.

Trượt bất kỳ điều nào → **dừng**, ghi kết quả phủ định, không viết code runtime, không chạy QA.

## Giai đoạn 3 — kết quả mô phỏng (chạy sau khi chốt luật dừng ở trên) → **DỪNG**

`simulate.txt`, `headroom.txt`.

| Cổng | Kết quả | |
|---|---|---|
| 1. P — đáp án nguyên văn trong Sources (94 câu) | 82 → 85 · 5 lên / 2 xuống · p = 0,45 | **TRƯỢT** |
| 2. E — đủ chunk đáp án (180 câu) | 151 → 163 · 12 lên / 0 xuống · p = 0,0005 | đạt |
| 3. Multi net ≥ −1 | E +1 · P 0 | đạt |
| 4. Token Sources trung vị ±5% | 3.602 → 3.867 (+7,4%); max 4.000 | **TRƯỢT** |
| 5. Context đổi ≥ 20 câu | 178/200 | đạt |
| 6. An toàn Null: sự kiện phân biệt +≤ 25% | Null 10,5 → 14,0 (+33%); mọi câu 8 → 13 | **TRƯỢT** |

**Khoảng trống có thật** (`headroom.txt`): trên dev, B2 đúng 85,9% ở câu đủ chunk đáp án nhưng chỉ 20,0% ở 25 câu chunk
đáp án bị A1 cắt. Trần của mọi cơ chế chọn chunk ≈ +16,5 câu = **+8,2 điểm acc dev** — lớn hơn sàn nhiễu sinh.

**Vì sao cửa sổ không đạt:** giữ được một nửa trần ở mức chunk (+12), cửa sổ giữ đáp án trong 91% chunk đáp án dài (51/56),
nhưng (a) nó nạp thêm ~60% số mảnh vào context (8 → 13 chunk), làm câu Null có thêm 33% sự kiện phân biệt để ghép sai —
đúng cơ chế gây ảo giác đang cần tránh; (b) dùng thêm 7,4% token trong cùng trần 4.000; (c) chỉ số chính P có trần nhỏ
(12 câu) và chỉ cải thiện net +3.

Theo luật đã chốt: **không viết code runtime, không chạy QA** cho quy tắc này. Không quét W sau khi thấy kết quả.

## Kiểm thêm — overflow-rescue (cứu một cửa sổ từ chunk tràn đầu tiên) → **DỪNG ở bước đo độ phủ**

Đo độ phủ tối đa trước khi mô phỏng (`rescue_coverage.txt`). Cơ chế chỉ tác động lên đúng một chunk — chunk đầu tiên làm
tràn ngân sách — nên nó chỉ cứu được câu mà chunk đó là chunk đáp án.

| | |
|---|---|
| 25 câu chunk đáp án có trong ứng viên nhưng mất ở A1: chunk tràn đầu tiên là chunk đáp án | **5/25** (Single 5/21, Multi 0/4) |
| trong các ca chunk đáp án bị cắt dài 1.200 token | 5/17 |
| 20 câu còn lại: chunk đáp án đứng sau chunk tràn đầu tiên | 1–38 vị trí (trung vị 7) |
| ngân sách còn lại cho cửa sổ ở 5 câu trúng | 125 · 919 · 1.052 · 1.112 · 1.156 token |
| Null: chunk tràn đầu tiên thuộc sự kiện chưa có trong Sources | **20/20** — mọi câu Null nhận thêm đúng một sự kiện |

**Trần tuyệt đối:** 5/200 câu dev (2,5%). Kể cả cứu trọn cả 5 và cả 5 chuyển sang đúng như nhóm đủ đáp án
(85,9% so với 20,0%), mức tăng tối đa ≈ 3,3 câu = **+1,6 điểm dev** — dưới dải nhiễu của ba lượt V3 cùng cấu hình (1,5 điểm) và
chỉ bằng khoảng 40% ngưỡng 4,18 điểm của tầng D. Không phép thử QA nào đã đăng ký có thể phát hiện nó. Trong khi đó cơ chế
kích hoạt ở gần như mọi câu và thêm một sự kiện mới vào context của **cả 20/20 câu Null**.

**Kết luận:** chính sách "dừng ở chunk tràn đầu tiên" của A1 chỉ gây ra 5/25 ca mất bằng chứng; 20/25 ca còn lại là do
**thứ tự xếp hạng** đặt chunk đáp án quá sâu so với ngân sách. Không tiền đăng ký, không mô phỏng, không viết code.
