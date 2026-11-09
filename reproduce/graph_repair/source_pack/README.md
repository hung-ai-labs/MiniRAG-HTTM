# Người 2 — "xếp chunk vào ngân sách Sources": hướng dẫn từ đầu

Viết 09/11/2026 cho thành viên mới chưa làm với repo này. Đọc hết file này trước khi chạy gì. Phần việc của bạn
**hoàn toàn tách khỏi** phần của Người 1 (chọn chunk trong thực thể xuất phát): bạn không cần — và không được — đụng vào
code của họ.

## 1. Nhóm đang làm gì

Nhóm tái tạo bài báo **MiniRAG** (RAG chạy được với model nhỏ, ở đây là Qwen2.5-3B) trên bộ dữ liệu **LiHua-World**
(442 tài liệu là tin nhắn chat của nhân vật Li Hua, 637 câu hỏi). Thầy hỏi: *"đóng góp của các em là gì?"* — vector,
BM25, hybrid đã có từ lâu. Nên mục tiêu bây giờ là **thắng MiniRAG gốc ngay trên cơ chế đồ thị** — thứ bài báo tự hào
nhất — mà **không** thêm vector / BM25 / RRF / reranker.

Giai đoạn 1 (đã xong, [PHASE1_REPORT.md](../PHASE1_REPORT.md)) đã đo chunk đáp án bị mất ở bước nào. Mỗi người nhận một
bước. **Bạn nhận bước cuối: từ 30 chunk đồ thị đã xếp hạng, chọn chunk nào đưa vào ngân sách 4.000 token.**

## 2. MiniRAG truy hồi thế nào (chế độ `mini`, `minirag/operate.py`)

Ví dụ câu hỏi: *"What does LiHua say Cersei's power came at the price of?"*

| Bước | Việc | Ở đâu | Của ai |
|---|---|---|---|
| 1 | Qwen tách từ khoá từ câu hỏi (đã cache sẵn — bạn không gọi model) | `_keyword_llm` | — |
| 2 | Mỗi từ khoá → tới 60 node đồ thị có **tên** gần nhất (cosine embedding) = **thực thể xuất phát** | `_build_mini_query_context` | — |
| 3 | Từ mỗi thực thể xuất phát đi tối đa 2 bước dọc cạnh, chấm điểm đường đi | `edge_vote_path`, `cal_path_score_list` | Người 1 |
| 4 | Mỗi thực thể xuất phát góp **tối đa 3 chunk** văn bản | `path2chunk` | **Người 1 — không đụng** |
| 5 | Gộp chunk của mọi thực thể, cộng điểm, lấy **30 chunk đầu** | `kwd2chunk` (~dòng 1348) | **Bạn** |
| 6 | Đưa 30 chunk theo thứ tự vào Sources, **cắt khi vượt 4.000 token** (gọi là A1) | cuối `_build_mini_query_context` (~dòng 1716) | **Bạn** |
| 7 | Bảng Entities + Sources → Qwen sinh câu trả lời | | — |

**Điểm của chunk ở bước 5**: `điểm(c) = Σ` qua các thực thể xuất phát góp `c`, của `cosine(tên thực thể, từ khoá)`
× **2** nếu là thực thể khớp nhất của từ khoá × **10** nếu chunk số 1 của thực thể đó nằm trong top-30 vector của câu
hỏi (hệ số ×10 dính luôn cho cả 3 chunk của thực thể). Giai đoạn 1 đo được: **bỏ ×10 hay ×2 đều làm hại** — giữ
nguyên chúng.

## 3. Phần của bạn mất bao nhiêu đáp án (180 câu dev có Evidence, mốc C0 = MiniRAG gốc)

| Tầng | Chunk đáp án | Câu | Nghĩa |
|---|---:|---:|---|
| **L3** trong top 30 nhưng bị cắt ở 4.000 token | **33** | **31** | Hạng 4–29, trung vị 12 |
| **L2** là ứng viên nhưng ngoài top 30 | 6 | 6 | Hạng 31–69 |
| Giữ được (để so) | 96 / 207 | 75 câu đủ đáp án | |

Dữ kiện đo được trên đúng đồ thị này — **điểm xuất phát cho chẩn đoán của bạn**:
- Bước cắt (`truncate_list_by_token_size`, `minirag/utils.py:189`) **dừng ở chunk đầu tiên làm tràn**, kể cả khi các
  chunk ngắn phía sau vẫn còn vừa.
- Trung vị **6 / 30** chunk vào được Sources (3.692 token). Chunk trung vị 274 token, p90 và tối đa **1.200 token** — một
  chunk dài ăn gần 1/3 ngân sách.
- Thực thể hub (`LIHUA`, nối với 331 node) có mặt ở hầu hết câu; seed hub top-5% góp ~37% token Sources (mô tả, chưa
  phải nhân quả).

## 4. Ranh giới — đọc kỹ

**Không được đụng** (phần Người 1 / phần đã có của nhóm):
- hàm `path2chunk`; các công tắc `MINIRAG_PATH_SCORE_FLOW`, `MINIRAG_PATH2CHUNK_FIX`, `MINIRAG_PATH_SCORE`,
  `MINIRAG_FLOW_SPEC`, `MINIRAG_FLOW_NORM`; ý tưởng trọng số `1/df` (độ đặc hiệu theo số chunk của node) — đó là giả
  thuyết của Người 1, dùng lại là trùng đóng góp.
- bộ đo dùng chung: `reproduce/graph_repair/run_offline.py`, `compare_phase2.py`, `diagnose.py`,
  `reproduce/path/eval_offline.py`, `reproduce/screening/screen_variant.py`, mốc `logs/c_ablation/graph/C*/`,
  `baseline.yaml`, index `LiHua-World-qwen-modal/`.

**Không được dùng làm tín hiệu** (đã có hoặc đã đóng, xem CLAUDE.md):
- vector / BM25 / RRF / cross-encoder (`MINIRAG_RERANK`) / so khớp chữ giữa câu hỏi và nội dung chunk. Hướng "xếp hạng
  lại bằng tín hiệu bề mặt tất định" **đã bị đóng** 20/09 sau kiểm toán 9 tín hiệu — đừng mở lại.
- `vector_ids` trong log chỉ được dùng như upstream (hệ số ×10), không làm tín hiệu mới.

**Không được gọi là phương pháp** (CLAUDE.md §1b): đổi `top_k`, đổi ngân sách 4.000, đổi prompt/model/embedding, bỏ hệ số
thưởng, **sửa bug thuần tuý**. Ví dụ: nếu chỉ sửa bước cắt để "bỏ qua chunk tràn rồi lấy tiếp chunk sau" thì đó là **sửa
baseline** — vẫn đáng đo và báo cáo như một *finding*, nhưng không phải đóng góp.

**Tín hiệu bạn được dùng**: mọi thứ có từ **cấu trúc đồ thị** đã nằm trong pipeline — chunk do từ khoá nào / thực thể
xuất phát nào góp, bao nhiêu thực thể cùng góp, điểm từng phần, độ dài chunk (token), quan hệ giữa các thực thể.

## 5. Quy trình — 5 bước, có điểm dừng để nhóm duyệt

Một đóng góp hợp lệ phải đủ: **vấn đề quan sát được → giả thuyết → cơ chế → thí nghiệm có kiểm soát → hiệu quả đo được
kèm ablation**.

### B0. Cài đặt và kiểm hồi quy (nửa ngày)

```powershell
# máy riêng: clone KHÔNG đổi xuống dòng, nếu không file đồ thị bị đổi sang CRLF
git clone -c core.autocrlf=false https://github.com/hung-ai-labs/MiniRAG-HTTM.git
cd MiniRAG-HTTM; git checkout graph/source-pack
py -3.13 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
# kiểm đồ thị đúng từng byte (phải ra 3be760266aff16799a30d9f1b18badcfce50cc2098f6a562135cded5913f037b)
(Get-FileHash LiHua-World-qwen-modal\graph_chunk_entity_relation.graphml).Hash
```

Lần đầu cần mạng **một lần** để tải embedding và tokenizer (miễn phí, không phải API trả tiền); runner chạy ở chế độ
offline nên phải tải trước:

```powershell
$env:TIKTOKEN_CACHE_DIR="$PWD\data-gym-cache"
.\.venv\Scripts\python.exe -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"
.\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')"
# data-gym-cache phải có 9b5ad71b2ce5302211f9c61530b329a4922fc6a4 và fb374d419588a4632f3f557e76b4b70aebbca790
```

Sau đó mọi lượt chạy đều offline. Nếu dùng chung máy
chính của nhóm thì không cần cài: dùng worktree `E:\Project\MiniRAG\.worktrees\source-pack` và
`E:\Project\MiniRAG\.venv\Scripts\python.exe` — nhưng **báo nhóm trước**, vì máy đó chỉ chạy được một lượt mỗi lúc.

Chạy kiểm hồi quy + bật log chẩn đoán (~20 phút, CPU):

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe reproduce\graph_repair\run_offline.py --phase p_pack --name c0_diag --arm C0 --diag
.\.venv\Scripts\python.exe reproduce\graph_repair\verify_t0.py --frozen logs\c_ablation\graph\C0\C0_records.jsonl `
    --off logs\graph_repair\p_pack\c0_diag\C0_records.jsonl --on logs\graph_repair\p_pack\c0_diag\C0_records.jsonl `
    --output logs\graph_repair\p_pack\c0_regression.json
```

Phải khớp **180/180**. Không khớp ⇒ dừng, báo nhóm (thường do file đồ thị bị đổi xuống dòng hoặc thiếu cache).

### B1. Chẩn đoán L3/L2 — "vấn đề quan sát được" (1–2 ngày, chỉ đọc log)

Dữ liệu: `logs/graph_repair/p_pack/c0_diag/diag.jsonl` (mỗi dòng một câu: `keywords`, `seeds`, `contributions` =
chunk → danh sách `{keyword, seed, score, x2, x10, contribution}`, `graph_ids` = top 30 theo thứ tự, `chunk_ids` = phần
giữ sau A1) và `logs/graph_repair/phase1/t2_summary.jsonl` (mỗi chunk đáp án: `layer`, `rank`, `dominant_above` =
chunk phía trên và thực thể góp nhiều nhất). Độ dài chunk: trường `tokens` trong
`LiHua-World-qwen-modal/kv_store_text_chunks.json`. Đáp án chỉ dùng làm **nhãn chẩn đoán**, không bao giờ đưa vào cơ chế.

Với 31 câu L3 và 6 câu L2, trả lời bằng số:
1. Ngân sách bị lãng phí bao nhiêu: số token còn trống khi bước cắt dừng; có bao nhiêu câu mà chunk đáp án **vẫn vừa**
   phần trống đó?
2. Phía trên chunk đáp án là gì: chunk dài? chunk do cùng một từ khoá / cùng một thực thể xuất phát góp lặp lại? chunk
   của hub?
3. Chunk đáp án do từ khoá nào góp, và từ khoá đó đã có bao nhiêu chunk trong Sources — có từ khoá nào **không có chunk
   nào** trong Sources không?
4. So với 75 câu đã đủ đáp án: các đặc điểm trên có khác không (để biết cơ chế có làm hại các câu đang đúng không)?

Được phép **mô phỏng offline** vài cách xếp lại từ log (không chạy pipeline) để ước lượng trần — nhưng ghi lại **mọi**
cách đã thử, kể cả cách không ăn thua.

**Sản phẩm:** `reproduce/graph_repair/source_pack/DIAGNOSIS.md` + script trong cùng thư mục. **⛔ Dừng — gửi nhóm duyệt
trước khi sang B2.**

### B2. Đăng ký trước (nửa ngày)

Viết `reproduce/graph_repair/source_pack/REGISTRATION.md` theo mẫu [PHASE2_REGISTRATION.md](../PHASE2_REGISTRATION.md):
vấn đề (số từ B1) → giả thuyết → cơ chế (công tắc `MINIRAG_PACK_*`, mặc định tắt, **không tham số tự do**, hoặc tham số
chốt trước kèm lý do) → tối đa **4 biến thể** tên `P-*` → **luật chọn** trên dev → **dự đoán** → các phép ablation. Đóng
băng: `sha256sum` file vào `logs/graph_repair/p_pack/REGISTRATION.sha256` và commit **trước** lượt chạy đầu tiên. Sửa
về sau chỉ thêm ở cuối, ghi ngày và đã xem số nào.

Hai hướng gợi ý để bắt đầu — **chỉ chọn nếu B1 ủng hộ**, hoặc đề xuất hướng khác:
- **Phủ từ khoá**: chọn Sources sao cho mỗi từ khoá của câu hỏi có đại diện, thay vì để một từ khoá / một thực thể chiếm
  hết ngân sách (dùng `contributions` để biết chunk thuộc từ khoá nào).
- **Giá trị trên token**: chọn theo điểm đồ thị so với độ dài chunk, để một chunk 1.200 token điểm vừa phải không đẩy
  ra ba chunk 300 token điểm cao.

### B3. Cài đặt (1 ngày)

- Chỉ sửa `kwd2chunk` và đoạn cắt A1 trong `minirag/operate.py`, sau công tắc `MINIRAG_PACK_*`. **Tắt ⇒ code đi đúng
  đường cũ.** Ngân sách vẫn 4.000, `top_k` vẫn 60.
- Thêm test `tests/test_source_pack.py` (dữ liệu giả, không model), chạy:
  `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` cho `test_source_pack.py`,
  `test_path_score_flow.py`, `test_c_ablation.py`, `test_flow_spec_norm.py`.
- Chạy lại `c0_reg` với công tắc tắt: vẫn 180/180.

### B4. Đo trên dev 180 (CPU, ~20 phút / biến thể)

```powershell
.\.venv\Scripts\python.exe reproduce\graph_repair\run_offline.py --phase p_pack --name p_a --arm C0 --env MINIRAG_PACK_A=1
```

`--env` chỉ nhận khoá `MINIRAG_*` và từ chối khoá mà `eval_offline` tự đặt lại. Mỗi lượt ghi `run_env.json`. So với
C0: sao chép `compare_phase2.py` thành `source_pack/compare_pack.py` (đổi danh sách nhánh; không sửa bản gốc). Báo
**số câu đủ đáp án**, Single / Multi, micro recall, trung vị token, và **lên / xuống so với C0 + McNemar p**. Áp đúng
luật chọn đã đăng ký, **một lần**.

### B5. Bàn giao

Commit lên `graph/source-pack`: code, test, DIAGNOSIS, REGISTRATION, kết quả dev (chỉ file tổng hợp, không commit
`diag.jsonl` hay `shard_*`). Phép thử chính trên **435 câu ngoài dev × 3 lượt sinh** và đợt đo chung với Người 1 sẽ chạy
trên máy chính của nhóm (cần hạ tầng `phased_qa.py` và cache từ khoá của nhánh khác) — bạn không phải tự dựng.

## 6. Đọc kết quả

- **Không** kết luận bằng hiệu số %. Ghép từng câu với C0: b = sai→đúng, c = đúng→sai, McNemar chính xác, báo
  `b lên / c xuống, p = …`.
- Dev 180 chỉ để **chọn**. Kết luận chỉ trên 435 câu ngoài dev: "tốt hơn" khi cả 3 lượt sinh cùng chiều và p < 0,05
  mỗi lượt.
- Evidence Recall **không** đo được 45 câu Null (không có đáp án) — chọn nhiều chunk "trông liên quan" hơn có thể làm Qwen
  bịa ở câu Null. Ghi vào rủi ro.
- Ở `top_k` = 5, bước cắt không còn là nút thắt — cơ chế của bạn có thể mất tác dụng. Ghi vào rủi ro, đo sensitivity nếu
  có thời gian (sensitivity, không phải phương pháp).

## 7. Luật làm việc

1. Không gọi API trả phí, không bật GPU Modal, không dùng quota Gemini — phần của bạn hoàn toàn offline.
2. Không xoá / ghi đè index hay log của người khác. Không push lên `main`. Chỉ commit trên `graph/source-pack`.
3. Máy 16 GB: tối đa 2 worker (runner đã giới hạn), một lượt mỗi lúc.
4. Báo nhóm ở 3 mốc: sau B0 (hồi quy qua), sau B1 (chẩn đoán — chờ duyệt), sau B4 (kết quả dev).

## 8. Từ điển nhanh

| Từ | Nghĩa |
|---|---|
| chunk | đoạn văn bản (một đoạn chat) — đơn vị đưa vào Sources |
| thực thể xuất phát (seed) | node đồ thị khớp với một từ khoá, nơi bắt đầu đi đường |
| Sources | phần văn bản thô trong context đưa cho Qwen, tối đa 4.000 token |
| A1 | bước cắt Sources ở 4.000 token |
| C0 | MiniRAG gốc (+ bản vá answer-type + A1) — mốc so sánh |
| dev 180 | 180 câu dev có Evidence, dùng để chọn |
| 435 câu ngoài dev | tập kết luận, không được nhìn khi thiết kế |
| lượt sinh s101 / s202 / s303 | 3 hạt giống ngẫu nhiên khi Qwen sinh từ khoá / câu trả lời |
| đủ đáp án | mọi chunk đáp án của câu đều có trong Sources |
