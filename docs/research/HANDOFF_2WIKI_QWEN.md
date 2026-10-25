# Bàn giao: luồng 2WikiMultiHopQA — đợt Qwen2.5-3B

> ⚠️ **Code không nằm trên `main`.** Trên `main` chỉ có tài liệu kế hoạch này; `main` vẫn là bản upstream HKUDS
> (`e204d23`). Toàn bộ code thực thi, dataset, `CLAUDE.md`, `ROADMAP.md` và mọi đường dẫn/lệnh nhắc tới trong tài liệu
> nằm trên branch **`dev`**, commit **`9c59062`**
> ([xem cây code](https://github.com/hung-ai-labs/MiniRAG-HTTM/tree/9c59062)). Trước khi làm:
> `git fetch origin && git checkout 9c59062` (hoặc tạo branch từ `origin/dev`). Các link tương đối tới `CLAUDE.md`,
> `ROADMAP.md` chỉ chạy được khi mở file từ checkout của `dev`.

> Dành cho **Người 2**, người phụ trách trọn luồng 2WikiMultiHopQA: dữ liệu → index → baseline → cải tiến → ablation →
> chấm → báo cáo. Soạn 25/10/2026 từ [`EXECUTION_PLAN_QWEN_NEW_DATASETS.md`](EXECUTION_PLAN_QWEN_NEW_DATASETS.md)
> (gọi tắt là **kế hoạch chung**), trên branch `dev`, HEAD `9c59062`. Tài liệu này đọc độc lập được; khi hai tài liệu
> lệch nhau thì kế hoạch chung thắng và cần sửa tài liệu này.
>
> Đọc kèm [`../../CLAUDE.md`](../../CLAUDE.md): §1b (thế nào là đóng góp hợp lệ), §3 (đọc kết quả bằng McNemar, nhiễu
> giữa các lượt sinh), §4 (không xoá/ghi đè index khi chưa hỏi).

**Nhãn trạng thái dùng trong tài liệu**

| Nhãn | Nghĩa |
|---|---|
| **[CÓ SẴN]** | Đã kiểm trong repo hoặc PDF lúc soạn |
| **[CẦN TRIỂN KHAI]** | Chưa tồn tại; tên file/flag là **đề xuất** |
| **[CHƯA XÁC MINH]** | Chưa đủ bằng chứng; luôn có task xác minh đi kèm |

**Mọi lệnh trong tài liệu đều chưa kiểm thử.** Lệnh gọi script chưa tồn tại có chú thích `# [SCRIPT CHƯA TỒN TẠI]`.
Placeholder: `<PYTHON>` (Python trong venv của bạn), `<TMP>` (thư mục tạm của bạn), `<BACKUP_ROOT>` (nơi lưu trữ chung,
nhóm chốt), `<PAPER_PDF>` (bản `miniRAG1.pdf`), `<RUN_ID>`, `<CORPUS_ID>`.

---

## 1. Bạn cần biết gì trước khi bắt đầu

### 1.1 Mục tiêu của luồng

Kiểm tra B2 (cải tiến truy hồi của nhóm) có giữ được lợi ích ngoài LiHuaWorld không, đo thêm các ablation, và để lại
bộ artifact đủ cho người khác chấm lại và tái lập. Kết quả âm vẫn là kết quả: ghi lại rồi chẩn đoán, không bỏ cấu hình
khỏi báo cáo. LiHuaWorld **không** chạy lại trong đợt này.

### 1.2 Hai loại "test" — không được lẫn

| Tên | Là gì | Dùng thế nào |
|---|---|---|
| **test chính thức** | `dataset/2WikiMultiHopQA/raw/extracted/test.json` — 12.576 câu, **không có** `answer`, `supporting_facts`, `evidences` | **không chấm được → không dùng** cho bất kỳ số liệu nào |
| **dev chính thức** | `.../extracted/dev.json` — 12.576 câu có đủ nhãn | nguồn của **mọi** câu hỏi trong đợt này |
| **`internal_dev`** | phần của pool (mục 3.3) dành cho pilot, phân tích lỗi, tinh chỉnh | xem tự do |
| **`internal_test`** | phần còn lại của pool, giữ riêng | chỉ chạy ở P8 khi phương pháp đã đóng băng |

Mọi bảng và báo cáo phải ghi **"test nội bộ tách từ dev chính thức"**, không bao giờ gọi `internal_test` là test chính
thức của 2WikiMultiHopQA. Nếu sau khi xem `internal_test` bạn sửa phương pháp, kết quả sau đó phải ghi rõ đã tiếp xúc test.

### 1.3 Dữ liệu 2Wiki đã có trong repo [CÓ SẴN]

| Mục | Giá trị |
|---|---|
| Archive | `dataset/2WikiMultiHopQA/raw/data_ids_april7.zip.part-00` … `part-05` (commit `9c59062`) |
| sha256 zip ráp lại | `95DF2BF56FDABE034E27AEBC580E02264232203CF52552F9EFE8A919E5529EEF` (theo `dataset/2WikiMultiHopQA/README.md`) |
| Bản giải nén | `dataset/2WikiMultiHopQA/raw/extracted/{train,dev,test,id_aliases}.json` — **bị gitignore**, máy bạn có thể chưa có |
| Trường mỗi câu | `_id, type, question, context, entity_ids, supporting_facts, evidences, answer, evidences_id, answer_id` |
| `context` | danh sách 10 phần tử `[title, [câu 1, câu 2, …]]` — gold + distractor |
| `supporting_facts` | danh sách `[title, chỉ số câu]` |
| Loại câu (dev) | compositional 5.236 · comparison 3.040 · bridge_comparison 2.751 · inference 1.549 |
| Trùng lặp (dev) | 0 câu hỏi trùng; mỗi title chỉ ứng với một văn bản |
| Không có | loại câu null/không trả lời được → không có nhóm "từ chối đúng" như LiHua |

**Không có corpus chung.** Mỗi câu chỉ kèm 10 đoạn của riêng nó. Muốn chạy MiniRAG (cần một kho tài liệu để index) thì
phải tự dựng corpus — mục 3.3.

Cỡ corpus đo offline lúc soạn (gộp 10 đoạn của N câu dev chọn ngẫu nhiên, seed 13, token đếm bằng tiktoken `gpt-4o`):

| N câu | Đoạn duy nhất | Token |
|---:|---:|---:|
| 200 | 1.446 | 144k |
| 500 | 3.324 | 342k |
| 1.000 | 6.360 | 663k |
| 2.000 | 11.564 | 1,23M |

Thành phần liên thông giữa các câu (dùng để chia dev/test không rò rỉ), đo trên cùng mẫu:

| N | Nối theo title **gold** (`supporting_facts`) | Nối theo **mọi** title trong `context` |
|---:|---|---|
| 500 | 482 thành phần, lớn nhất 3 câu | 117 thành phần, lớn nhất 304 câu |
| 1.000 | 907 thành phần, lớn nhất 6 câu | 185 thành phần, lớn nhất 723 câu |

→ Nối theo title gold chia được; nối theo mọi title thì một thành phần nuốt phần lớn pool. **Đây là số đo trên mẫu, không
phải quy tắc đã khoá** — bạn phải đo lại trên pool thật ở `2W-04`.

### 1.4 Bài báo đích và số tham chiếu

Bài báo đích: `miniRAG1.pdf` (bản ba dataset), sha256 `a62cad8535e27a9005fa25098ba69908604f3f4158b39f5a7bab00a1d654bd86`.
File **không** có trong repo — xin Người 1 hoặc lấy ở `<BACKUP_ROOT>/paper/` sau khi `S-01` xong. **Không** dùng
`miniRAG.pdf` (bản khác, sha256 `6a7e3674…d1f561`), và không dùng số trong `README.md`/`CLAUDE.md` (thuộc bản khác).

Table 1, hàng 2wikimultihopqa, Qwen2.5-3B-Instruct, GPT-4o chấm (acc / err, %):

| BM25 | RAPTOR | HippoRAGv2 | GraphRAG | LightRAG | **MiniRAG** |
|---|---|---|---|---|---|
| 46,32 ± 2,44 / 31,71 ± 4,69 | 43,80 ± 3,45 / 34,25 ± 3,87 | 45,02 ± 4,18 / 38,94 ± 4,61 | / | 28,29 ± 5,50 / 21,77 ± 4,02 | **52,30 ± 6,11 / 36,29 ± 4,95** |

Đây là **cột tham chiếu**, không phải đối chứng: khác judge (bạn dùng Gemini Flash), khác corpus (bài báo không mô tả cách
dựng), khác code. Không điền số bài báo vào ô chưa chạy của nhóm.

Những điều bài báo **có** nói (Phụ lục B, §4): chunk 1.200 token, overlap 100; embedding all-MiniLM-L6-v2; một model làm
cả index, sinh truy vấn và trả lời; không reranker; judge GPT-4o chấm 3 lượt có xáo thứ tự; "top-k retrieval to 5
documents", "maximum token limit 6000 tokens". Những điều **không** nói: cách dựng corpus 2Wiki, số câu, cách chia,
cách hiện thực −I/−Rchunk/−Redge. Cụm "MultihopQA test set" ở §4.2 không rõ chỉ dataset nào.

### 1.5 Các cấu hình bạn sẽ chạy

| ID | Là gì | Trong code | Trạng thái |
|---|---|---|---|
| GROUP_BASE | baseline nhóm đã vá: xếp hạng chunk chỉ bằng đồ thị, cắt Sources ở 4.000 token (A1), vá answer-type | `MINIRAG_ANSWER_TYPE_FIX=1 MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT=`, không đặt `MINIRAG_CHUNK_FUSION` | [CÓ SẴN] |
| B2_FULL | GROUP_BASE + trộn RRF (k=60) của vector top-30 và BM25 top-30 trên nguyên câu hỏi; bảng Entities vẫn từ đồ thị | thêm `MINIRAG_CHUNK_FUSION=vector_bm25` (`minirag/operate.py:1504-1520`, `minirag/bm25.py`) | [CÓ SẴN] |
| B2_NO_BM25 | B2 bỏ BM25 = vector thuần | `MINIRAG_CHUNK_FUSION=vector` | [CÓ SẴN]; tương đương với "B2 bỏ BM25" phải kiểm bằng fixture (`S-07`) |
| B2_NO_VECTOR | B2 bỏ vector = BM25 thuần | đề xuất `MINIRAG_CHUNK_FUSION=bm25` | [CẦN TRIỂN KHAI] |
| B2_NO_ENT | B2 bỏ bảng Entities khỏi prompt, Sources giữ nguyên từng byte | đề xuất `MINIRAG_DROP_ENTITIES=1` | [CẦN TRIỂN KHAI] |
| HYBRID_NO_GRAPH | RRF(vector, BM25), **không** gọi parser từ khoá, không truy hồi đồ thị | đề xuất `MINIRAG_NO_GRAPH=1` | [CẦN TRIỂN KHAI] |
| MR_FULL | MiniRAG đầy đủ theo protocol tái hiện | chốt ở `V-03` | [CHƯA XÁC MINH] |
| MR_MINUS_I / RCHUNK / REDGE | ablation gốc của bài báo, áp sang 2Wiki (thí nghiệm **mở rộng**) | chốt ở `V-01` | [CHƯA XÁC MINH] — không chạy khi chưa có định nghĩa |

Ba điều dễ nhầm:
- **MR_FULL ≠ tắt A1 và tắt bản vá answer-type.** Hai công tắc `MINIRAG_TRUNCATE_SOURCES=0` và `MINIRAG_ANSWER_TYPE_FIX=0`
  chỉ đưa code gần lại upstream (`e204d23`) ở hai điểm; code vẫn có bản vá O(N²) (không tắt được) và chưa chứng minh là
  cấu hình của bài báo.
- **−Redge ≠ bỏ Entities khỏi prompt** (đó là B2_NO_ENT). **−Rchunk ≠ xoá Sources.**
- B2_FULL và B2_NO_ENT **vẫn** chạy đồ thị phía trước: nếu đồ thị không ra node hoặc cạnh, câu trả lời là
  `fail_response` (`minirag/operate.py:1522-1526`). Chỉ HYBRID_NO_GRAPH bỏ đồ thị hoàn toàn.

### 1.6 Code hiện có và lỗ hổng — vì sao không dùng thẳng `Step_*`

| Thành phần | Vấn đề với đợt này |
|---|---|
| `reproduce/Step_0_index.py` | chỉ đọc `.txt`; không ghi lại request; không lưu mapping tài liệu → chunk |
| `reproduce/Step_1_QA.py` | resume **theo số dòng**, khoá bằng văn bản câu hỏi; lỗi endpoint ghi thành câu trả lời `"Error"` |
| `reproduce/Step_2_evaluate.py` | đầu ra judge không khớp nhãn → **tự thành `neither`** (`:108`); không lưu response thô; model mặc định Flash-Lite |
| `minirag/llm/gemini.py` | không log request/response, không lưu model thực trả về |
| `MINIRAG_CONTEXT_LOG` | không lưu văn bản context, đầu ra parser từ khoá; không ghi gì khi thoát sớm |
| Thoát sớm | parse JSON từ khoá hỏng (`operate.py:1655-1676`) và đồ thị rỗng đều trả `fail_response` mà không để lại dấu vết |
| `minirag/bm25.py` | tách từ `[a-z0-9]+` sau khi viết thường → tên có dấu bị cắt (ví dụ "Żuławski" → mảnh ASCII). Đặc tả BM25 đã chốt, **không sửa** — ghi vào Limitations |
| `llm_model_max_token_size=200` (`reproduce/gemini_common.py:118`) | grep tĩnh không thấy chỗ nào trong `minirag/` đọc trường này → ảnh hưởng runtime [CHƯA XÁC MINH] (`V-05`, Người 1) |
| Script chạy hiện có | giả định macOS/zsh (`caffeinate`, `pmset`, `.venv/bin/python`). Script mới viết bằng Python thuần |

Vì vậy đợt này dùng bộ runner mới `reproduce/research/` [CẦN TRIỂN KHAI], làm chung ở phần chuẩn bị (mục 2).

### 1.7 Quy tắc bắt buộc

- Qwen2.5-3B-Instruct làm **cả** trích xuất index, gleaning, phân tích câu hỏi và sinh câu trả lời.
- Không đưa `answer`, `supporting_facts`, `evidences`, `id_aliases` vào generation hay index. Corpus là **toàn bộ đoạn** của
  pool (gold **và** distractor), không chỉ đoạn gold.
- Không dùng câu `internal_test` để chọn cấu hình hay tinh chỉnh.
- Judge phát triển: **Gemini Flash** (không phải Flash-Lite). GPT-4o chỉ chấm, chỉ ở P8, cần nhóm duyệt chi phí.
- Không ghi vào index LiHua (`LiHua-World-*`) hay thư mục của Người 1. Không xoá index khi chưa hỏi nhóm.
- Mọi công tắc mới trong `minirag/` mặc định tắt: không đặt biến thì kết quả phải giống hệt trước.
- Không ghi API key, header `Authorization`, URL chứa token vào bất kỳ log nào.
- Một run mới = một thư mục mới. Không resume theo số dòng, không ghép theo văn bản câu hỏi.

### 1.8 Thư mục của bạn

| Đường dẫn | Nội dung | Git? |
|---|---|---|
| `dataset/2WikiMultiHopQA/processed/` | dữ liệu chuẩn hoá | không (gitignore ở `S-02`) — backup |
| `indexes/2wiki-qwen-<CORPUS_ID>/` | index của bạn | không — backup + checksum |
| `runs/2wiki/dataset_manifest.json`, `runs/2wiki/split_manifest.json`, `runs/2wiki/corpus_manifest.json` | manifest cấp dataset | manifest nhỏ: có (trừ ID `internal_test` đầy đủ) |
| `runs/2wiki/qwen/<experiment_id>/<RUN_ID>/` | một lần chạy | file nhỏ (manifest, metrics, per_question, report): có; JSONL thô: backup |
| `configs/research/2wiki/*.yaml` | cấu hình từng thí nghiệm | có |

---

## 2. Phần chuẩn bị chung (P0)

Hai người làm phần này **trước khi tách**. Không task 2Wiki nào từ `2W-05` trở đi bắt đầu khi `S-01`…`S-09` chưa xong.

### 2.1 Bảng phân việc chung

| Task | Người làm | Bạn làm gì |
|---|---|---|
| S-01 Khoá protocol và nguồn | Người 1 | **review**, ký tên vào protocol |
| S-02 Chuẩn bị repo | **Bạn** | làm |
| S-03 Môi trường | mỗi người | làm cho máy bạn |
| S-04 Logger request LLM | Người 1 | **review** |
| S-05 Log truy hồi + đường thoát sớm | Người 1 | **review** |
| S-06 Runner chung | Người 1 (index, QA) · **Bạn** (judge, metrics) | làm phần judge + metrics |
| S-07 Ba công tắc ablation B2 | **Bạn** | làm |
| S-08 Fixture offline | **Bạn** | làm |
| S-09 Kiểm chéo schema | cả hai | làm cùng |
| V-01 Định nghĩa −I/−Rchunk/−Redge | cả hai | làm cùng |
| V-02 Cách tác giả dựng corpus 2Wiki | **Bạn** | làm |
| V-03 Ánh xạ top-k / ngân sách token vào code | Người 1 | chờ kết quả (chặn MR_FULL) |
| V-04 Sampling vLLM, HF revision | Người 1 | chờ kết quả (chặn P2) |
| V-05 Ảnh hưởng của `llm_model_max_token_size=200` | Người 1 | chờ kết quả |
| V-06 ID model Gemini Flash | **Bạn** | làm |

### 2.2 Các task chung bạn làm

**S-02 · Chuẩn bị repo**
- Phụ thuộc: —
- Hành động: tạo worktree/branch riêng (đề xuất `research/2wiki-qwen`); thêm `runs/`, `indexes/`, `dataset/*/processed/`
  vào `.gitignore`; tạo bốn file trạng thái khung trong `docs/research/`: `PROJECT_STATE.md`, `BASELINE_MANIFEST.yaml`,
  `EXPERIMENT_HISTORY.md`, `CODE_MAP.md`. **Không** sửa `baseline.yaml` (đóng băng, CLAUDE.md §2).
- Lệnh dự kiến:
  ```bash
  git worktree add ../MiniRAG-2wiki -b research/2wiki-qwen dev
  git check-ignore -v runs/x indexes/x dataset/2WikiMultiHopQA/processed/x
  ```
- Đầu ra: `.gitignore` cập nhật, bốn file khung
- Hoàn thành khi: `git check-ignore` khớp cả ba đường dẫn; Người 1 review xong; nhóm đã quyết có commit index mới vào Git
  hay chỉ backup ngoài (LiHua hiện đang commit `LiHua-World-qwen-modal/`)

**S-03 · Môi trường máy bạn**
- Hành động: ghi `docs/research/env/nguoi2.md`: hệ điều hành, phiên bản Python, `pip freeze` so với `requirements.lock.txt`,
  CPU/RAM/GPU, backend phục vụ Qwen, phần cứng endpoint.
- Lệnh dự kiến: `<PYTHON> -m pip freeze > runs/_env/nguoi2_freeze.txt`
- Hoàn thành khi: import được `minirag`, `tiktoken`, `transformers`; tải được `sentence-transformers/all-MiniLM-L6-v2`

**S-06 (phần của bạn) · Runner judge và metrics** [CẦN TRIỂN KHAI]
- `reproduce/research/judge_run.py`:
  - rubric có version (`rubric_v1`), dùng chung cho MultiHop-RAG và 2Wiki: giữ định nghĩa accurate / error / neither của
    `reproduce/Step_2_evaluate.py`; thêm hướng dẫn cho câu so sánh, câu ngày tháng, đáp án yes/no, và nhận **alias** của
    đáp án (2Wiki: từ `id_aliases.json`, chỉ đưa vào phía judge);
  - đầu ra judge là JSON `{"label": "accurate|error|neither"}`; không parse được → **`parse_failed`**, không bao giờ thành
    `neither`; API hỏng sau số lần thử giới hạn → `judge_failed`, lượt chưa hoàn tất;
  - xáo thứ tự câu theo seed của từng lượt chấm; ghi `pass_id`;
  - lưu: rubric version, đầu vào judge đầy đủ, model gọi, **model response trả về**, response thô, nhãn, lỗi, attempt.
- `reproduce/research/metrics.py`: `per_question.csv` (một dòng / query × lượt sinh × lượt chấm), `metrics.json`; Acc, Err,
  Neither, `n_valid`, `n_expected`, `n_parse_failed`, `n_infra_failed`, `n_early_exit` theo lý do; McNemar chính xác (tái
  dùng `mcnemar_p` trong `reproduce/screening/screen_variant.py`); paired bootstrap theo query giữ các lượt lặp trong query;
  bảng theo loại câu; Evidence Recall@k.
- `reproduce/research/check_run.py` (làm cùng Người 1): đếm dự kiến/thực tế, ID duy nhất, checksum index/split, từ chối
  trộn `config_hash`.
- Hoàn thành khi: test offline (S-08) xanh — judge trả rác → `parse_failed`; metric tính lại từ `per_question.csv` khớp
  `metrics.json`; kill giữa lượt chấm rồi chạy lại không chấm trùng.

**S-07 · Ba công tắc ablation B2** [CẦN TRIỂN KHAI], đều mặc định tắt, trong `minirag/operate.py`
- `MINIRAG_CHUNK_FUSION=bm25` → B2_NO_VECTOR (BM25 top-30 thuần). Hiện giá trị lạ ném `ValueError` (`operate.py:1519-1520`).
- `MINIRAG_DROP_ENTITIES=1` → B2_NO_ENT: bảng Entities thay bằng header rỗng; Sources không đổi.
- `MINIRAG_NO_GRAPH=1` (hoặc mode riêng) → HYBRID_NO_GRAPH: không gọi parser từ khoá, không truy hồi đồ thị, không có đường
  thoát `None` của đồ thị; tham khảo `naive_query` (`operate.py:1081`).
- Hoàn thành khi (kiểm bằng fixture S-08):
  - `vector` cho thứ tự chunk trùng `_rrf_fuse(chunks_ids)` → xác nhận B2_NO_BM25 đúng nghĩa;
  - B2_NO_ENT: dựng context **một lần**, so sha256 phần Sources với B2 → trùng từng byte;
  - HYBRID_NO_GRAPH: không có lời gọi phase `kw_parse`, vẫn có bản ghi truy hồi;
  - không đặt biến nào → sha256 context và prompt giống hệt trước khi sửa;
  - Người 1 review.

**S-08 · Fixture offline** [CẦN TRIỂN KHAI]
- `tests/research/fixtures/`: khoảng 5 tài liệu, 6 câu, LLM giả trả kết quả trích xuất và câu trả lời cố định.
- Lệnh dự kiến: `<PYTHON> -m pytest tests/research -q` (chạy không mạng)
- Hoàn thành khi: toàn bộ test chạy offline, không gọi endpoint nào.

**S-09 · Kiểm chéo schema** — cùng Người 1
- Mỗi người chạy runner trên fixture, đổi file cho nhau; người kia ghép `generation` / `judge` / `per_question` bằng
  `query_id` và tính lại metric.
- Hoàn thành khi: hai người ra cùng số; ghi vào `docs/research/EXPERIMENT_HISTORY.md`.

**V-01 · Định nghĩa −I / −Rchunk / −Redge** — cùng Người 1
- Đầu vào: `<PAPER_PDF>` §4.4 và chú thích Table 2; repo upstream `HKUDS/MiniRAG` (branch, issue, script).
- Biết trước: bài báo chỉ nói −I thay heterogeneous graph indexing bằng indexing dựa trên mô tả (kiểu LightRAG/GraphRAG);
  −Redge bỏ thông tin cạnh, −Rchunk bỏ chunk nodes khi truy hồi đồ thị. Code hiện tại: prompt `entity_extraction` **đã**
  yêu cầu description cho entity và relationship (`minirag/prompt.py:13`); `entity_extraction_noDes` chỉ còn trong
  comment (`operate.py:251`) và không được định nghĩa → ranh giới hai kiểu indexing trong code chưa rõ.
- Đầu ra: một đoạn định nghĩa hiện thực cho từng biến thể, hoặc ghi "không đủ căn cứ — không chạy".
- Chặn: mọi lượt MR_MINUS_* (`2W-10`).

**V-02 · Cách tác giả dựng corpus 2Wiki** — bạn
- Đầu vào: toàn văn `<PAPER_PDF>`, repo upstream, issue.
- Biết trước: PDF không mô tả. Phụ lục A.1 có mô tả cho **NQ/TQA** ("randomly sampled supporting documents for 500 questions
  as the document corpus and randomly selected 100 questions") — đó là dataset khác, **không** phải bằng chứng cho 2Wiki.
- Đầu ra: ghi chú nguồn trong `docs/research/EXPERIMENT_HISTORY.md`. Không tìm được → giữ nguyên nhãn
  **"chuyển đổi benchmark do nhóm đề xuất, không phải tái hiện chính xác"** cho mọi kết quả 2Wiki.
- Chặn: chốt N ở `2W-03`; cách gọi tên cột "tái hiện" trong báo cáo.

**V-06 · ID model Gemini Flash** — bạn
- Hành động: liệt kê model qua API (lời gọi metadata, không tốn quota sinh) bằng khoá của bạn; chọn và ghim ID có version
  nếu có; gửi một request thử, lưu trường `model` trong response.
- Biết trước: repo chỉ dùng `gemini-flash-lite-latest`; trợ giúp `--model` trong `reproduce/gemini_common.py` nhắc
  `gemini-3.6-flash` — chưa ai kiểm.
- Đầu ra: `<JUDGE_MODEL_ID>` ghi vào protocol (S-01).
- Chặn: P2 (`2W-08`).

### 2.3 Những gì bạn nhận từ Người 1 (đọc, review, rồi dùng)

| Từ task | Bạn nhận | Dùng ở |
|---|---|---|
| S-01 | `docs/research/PROTOCOL_QWEN_NEW_DATASETS.md` (protocol v1: model, serving, index, judge, số lượt lặp, ngân sách) | mọi task |
| S-04 | `reproduce/research/llm_logging.py`: ghi messages, kwargs, response thô, model trả về, latency, attempt sau **mỗi** lời gọi LLM, theo phase `extract` / `glean` / `kw_parse` / `answer` / `judge` | 2W-05 trở đi |
| S-05 | công tắc `MINIRAG_RETRIEVAL_LOG=<jsonl>` (tên đề xuất): đầu ra parser từ khoá, ứng viên/hạng/điểm từng nhánh, chunk chọn, điểm cắt A1, context cuối, bản ghi cho `kw_parse_failed` / `no_nodes` / `no_edges` | 2W-08 trở đi |
| S-06 | `reproduce/research/index_run.py`, `reproduce/research/qa_run.py` | 2W-05 trở đi |
| V-03 | định nghĩa MR_FULL | 2W-09 |
| V-04 | HF revision và thông số sampling đã ghim | 2W-05 |
| V-05 | kết luận về `llm_model_max_token_size=200` | 2W-05/06 |

---

## 3. Các task 2Wiki theo thứ tự

Mỗi task: **Phụ thuộc · Đầu vào · Hành động · Lệnh dự kiến · Đầu ra · Log phải lưu · Hoàn thành khi.**

### P0 — Dữ liệu

**2W-01 · Kiểm kê dữ liệu thô**
- Phụ thuộc: S-02
- Đầu vào: `dataset/2WikiMultiHopQA/raw/data_ids_april7.zip.part-0*`
- Hành động: ráp zip **vào thư mục tạm**, kiểm sha256, giải nén (nếu máy chưa có `extracted/`), kiểm sha256 từng file JSON.
- Lệnh dự kiến:
  ```bash
  cat dataset/2WikiMultiHopQA/raw/data_ids_april7.zip.part-* > <TMP>/data_ids_april7.zip
  sha256sum <TMP>/data_ids_april7.zip
  sha256sum dataset/2WikiMultiHopQA/raw/extracted/*.json
  ```
  (Windows `cmd.exe`: lệnh `copy /b …` trong `dataset/2WikiMultiHopQA/README.md`.)
- Đầu ra: phần "source" của `runs/2wiki/dataset_manifest.json`: sha256 zip và từng JSON, số câu dev/test, đếm theo loại.
- Log phải lưu: lệnh và output kiểm sha256 trong manifest.
- Hoàn thành khi: zip khớp `95DF2BF5…5529EEF`; dev 12.576 câu có nhãn; manifest ghi rõ **test chính thức không có nhãn,
  không dùng**.

**2W-02 · Chuẩn hoá dev chính thức**
- Phụ thuộc: 2W-01, S-01
- Đầu vào: `extracted/dev.json`, `extracted/id_aliases.json`
- Hành động — `reproduce/research/prepare_2wiki.py` [SCRIPT CHƯA TỒN TẠI]:
  - `paragraphs.jsonl`: mỗi title một dòng, `doc_id` = title, `text` = `Title\n<các câu nối bằng dấu cách>` (định dạng
    chính xác ghi vào manifest);
  - `queries.jsonl`: `query_id` = `_id` gốc, `question`, `type`, danh sách `doc_id` trong context — **không có** đáp án;
  - `gold.jsonl`: `answer`, `answer_id`, alias, `supporting_facts`, `evidences` — **tách riêng**, chỉ judge và metrics đọc.
  - Đo thêm và ghi manifest: phân bố đáp án (bao nhiêu câu yes/no, ngày tháng, tên riêng) để viết rubric; số đoạn gold mỗi
    câu theo loại; cấu trúc `id_aliases.json` — **[CHƯA XÁC MINH]** lúc soạn, phải đọc file trước khi dùng.
- Lệnh dự kiến: `<PYTHON> reproduce/research/prepare_2wiki.py --raw dataset/2WikiMultiHopQA/raw/extracted --out dataset/2WikiMultiHopQA/processed  # [SCRIPT CHƯA TỒN TẠI]`
- Đầu ra: ba file trên + mục "normalize" trong `dataset_manifest.json`
- Log phải lưu: sha256 ba file đầu ra; số câu vào/ra; số câu bị loại kèm lý do (kỳ vọng 0).
- Hoàn thành khi: `query_id` duy nhất; mỗi title một văn bản; mọi title trong `supporting_facts` nằm trong context của chính
  câu đó; `queries.jsonl` không chứa trường gold nào.

**2W-03 · Chọn pool N và dựng corpus**
- Phụ thuộc: 2W-02, V-02
- Đầu vào: `queries.jsonl`, `paragraphs.jsonl`, ngân sách còn lại (mục 5)
- Hành động:
  1. Với vài giá trị N, chọn ngẫu nhiên N câu (seed công bố); tính số đoạn duy nhất, token, và **số chunk thật** bằng
     `chunking_by_token_size` (`minirag/operate.py:42`, 1.200 / 100) — không gọi LLM. Đoạn 2Wiki thường ngắn, nên dự kiến
     mỗi đoạn một chunk; phải xác nhận bằng số đo.
  2. Ước lượng tĩnh số lời gọi index = số chunk × 2 (đọc code: gleaning 1 → một lời gọi trích xuất + một gleaning mỗi chunk,
     `operate.py:276-292`). **Đây chưa phải dự toán** — số thật lấy ở pilot `2W-05`.
  3. Chọn N theo số đo và ngân sách; ghi lý do.
  4. Corpus = hợp **cả 10 đoạn** (gold + distractor) của **mọi** câu trong pool.
- Đầu ra: `runs/2wiki/corpus_manifest.json` (seed, N, danh sách `query_id` của pool, danh sách `doc_id`, số chunk, token),
  `<CORPUS_ID>` (ví dụ `pool<N>s<seed>`)
- Log phải lưu: bảng N → đoạn / token / chunk / lời gọi ước lượng.
- Hoàn thành khi: corpus không thiếu đoạn nào của pool và không có đoạn nào ngoài pool; manifest ghi rõ nhãn **"chuyển đổi
  benchmark"** nếu V-02 không ra bằng chứng; nhóm biết N trước khi index.

**2W-04 · Thiết kế split `internal_dev` / `internal_test`**
- Phụ thuộc: 2W-03
- Đầu vào: pool, `gold.jsonl`
- Hành động — `reproduce/research/split_groups.py` [SCRIPT CHƯA TỒN TẠI] (dùng chung với Người 1):
  1. Báo cáo phân bố thành phần liên thông trên **pool thật** theo hai quy tắc: nối theo title gold; nối theo mọi title
     context (đối chứng). Thêm nhóm gần trùng văn bản câu hỏi (chuẩn hoá chữ thường/dấu câu + Jaccard 5-gram ký tự, ngưỡng
     ghi manifest) — chỉ để **gắn nhóm**, không xoá câu.
  2. Đánh giá khả năng chia: nhóm lớn nhất chiếm bao nhiêu % pool; tỷ lệ 4 loại câu ở hai phía; số cặp câu dev–test dùng
     chung đoạn gold.
  3. **Chỉ sau khi đọc báo cáo** mới chọn quy tắc; nếu không quy tắc nào chia được, dừng và báo nhóm — không tự nới.
  4. Chia theo nhóm (mỗi nhóm nằm trọn một phía), phân tầng theo loại câu, seed công bố.
- Lệnh dự kiến: `<PYTHON> reproduce/research/split_groups.py --dataset 2wiki --pool runs/2wiki/corpus_manifest.json --report runs/2wiki/split_report.md  # [SCRIPT CHƯA TỒN TẠI]`
- Đầu ra: `runs/2wiki/split_manifest.json` (seed, quy tắc, nhóm, ID `internal_dev`; ID `internal_test` đầy đủ chỉ để ở
  `<BACKUP_ROOT>`), `runs/2wiki/split_report.md`
- Log phải lưu: báo cáo phân bố trước khi chọn quy tắc (giữ cả phương án bị loại).
- Hoàn thành khi: không ID nào ở cả hai phía; mỗi nhóm nằm trọn một phía; chênh lệch tỷ lệ loại câu không vượt mức chốt
  trước; báo cáo ghi rõ distractor **có** dùng chung giữa hai phía (do corpus chung — là thiết kế, phải ghi vào
  Limitations).

### P1 — Index

**2W-05 · Pilot index trên corpus con**
- Phụ thuộc: S-04…S-08, V-04, 2W-03
- Đầu vào: khoảng 200 đoạn chọn có seed từ corpus; endpoint Qwen đã ghim revision
- Hành động: index để kiểm **kỹ thuật** (không phải benchmark); đo lời gọi/chunk thật, thời gian, lỗi, retry; xem
  `max_tokens` thực gửi (phục vụ V-05); kiểm có đầu ra trích xuất nào bị cắt cụt; thử BM25 trên vài title có dấu và ghi
  hiện tượng (không sửa tokenizer).
- Lệnh dự kiến: `<PYTHON> reproduce/research/index_run.py --dataset 2wiki --subset pilot200 --workingdir indexes/2wiki-qwen-pilot200  # [SCRIPT CHƯA TỒN TẠI]`
- Đầu ra: index pilot, `index_manifest.json`, dự toán cho index toàn corpus (lời gọi, thời gian máy, tiền)
- Log phải lưu: `index_requests.jsonl` (mỗi request: chunk_id, phase, messages, kwargs, response thô, model trả về, latency,
  attempt, lỗi), `events.jsonl` (start/end, retry, timeout, checkpoint, resume).
- Hoàn thành khi: mỗi chunk có đủ cặp request extract + glean có response; không response cắt cụt nào chưa được giải thích;
  dự toán lập từ **số đo**; nếu dự toán vượt trần thì **dừng và báo nhóm**.

**2W-06 · Index chính thức**
- Phụ thuộc: 2W-05, nhóm duyệt dự toán
- Đầu vào: corpus `<CORPUS_ID>`, cấu hình index đã khoá: chunk 1.200 / 100, gleaning 1, embedding
  `sentence-transformers/all-MiniLM-L6-v2` 384 chiều, entity types mặc định (`minirag/prompt.py:10`)
- Lệnh dự kiến: `<PYTHON> reproduce/research/index_run.py --dataset 2wiki --subset <CORPUS_ID> --workingdir indexes/2wiki-qwen-<CORPUS_ID>  # [SCRIPT CHƯA TỒN TẠI]`
- Đầu ra: `indexes/2wiki-qwen-<CORPUS_ID>/` (các file `kv_store_*.json`, `vdb_*.json`, `graph_chunk_entity_relation.graphml`,
  `extracted_chunks.json`); `index_manifest.json` (corpus_id, model + revision, embedding, sha256 prompt, commit, sha256 từng
  file, số node/cạnh/chunk, lỗi); mapping `doc_id ↔ doc-<md5>` và `chunk_id → doc_id` (MiniRAG đặt ID theo md5 nội dung,
  `minirag/minirag.py:438`, nên mapping phải tự ghi).
- Log phải lưu: như 2W-05, cho toàn bộ corpus.
- Hoàn thành khi: mọi tài liệu ở trạng thái `processed`; mọi chunk có `full_doc_id` hợp lệ và có mặt trong `vdb_chunks.json`;
  node đồ thị trỏ về chunk tồn tại; đã backup lên `<BACKUP_ROOT>`, mở thử được, sha256 khớp; index đánh dấu **chỉ đọc**
  (từ đây không ghi thêm — mọi cấu hình retrieval dùng chung index này; −I nếu chạy thì có index riêng).

**2W-07 · Ánh xạ supporting_facts → chunk**
- Phụ thuộc: 2W-06
- Hành động: với mỗi câu, ánh xạ title gold → `doc_id` → chunk.
- Đầu ra: `runs/2wiki/gold_chunks.jsonl` — **chỉ** dùng cho metric truy hồi.
- Hoàn thành khi: tỷ lệ ánh xạ được báo cáo; trường hợp không ánh xạ được liệt kê, không đoán.

### P2 — Smoke

**2W-08 · Smoke 10–20 câu `internal_dev`**
- Phụ thuộc: 2W-06, V-06, S-09
- Đầu vào: mẫu có seed, phủ cả 4 loại câu; cấu hình `configs/research/2wiki/group_base.yaml` và `b2_full.yaml`
  [CẦN TRIỂN KHAI]
- Hành động: 1 lượt sinh × 1 lượt chấm cho GROUP_BASE và B2_FULL; kiểm đường chạy, không đọc kết quả như kết luận.
- Lệnh dự kiến:
  ```bash
  <PYTHON> reproduce/research/qa_run.py --config configs/research/2wiki/b2_full.yaml --split internal_dev --sample smoke20 --seed 101   # [SCRIPT CHƯA TỒN TẠI]
  <PYTHON> reproduce/research/judge_run.py --run runs/2wiki/qwen/b2_full/<RUN_ID> --rubric rubric_v1 --passes 1            # [SCRIPT CHƯA TỒN TẠI]
  <PYTHON> reproduce/research/check_run.py --run runs/2wiki/qwen/b2_full/<RUN_ID>                                         # [SCRIPT CHƯA TỒN TẠI]
  ```
- Đầu ra: thư mục run đầy đủ (mục 4)
- Log phải lưu: `retrieval.jsonl`, `generation.jsonl`, `judge.jsonl`, `events.jsonl`, `run_manifest.json`
- Hoàn thành khi: mọi bản ghi ghép đúng theo `query_id`; câu thoát sớm (nếu có) có bản ghi lý do; không `parse_failed` nào
  bị che; `check_run.py` không báo lỗi.

### P3 — Pilot

**2W-09 · Pilot 50–100 câu `internal_dev`**
- Phụ thuộc: 2W-08
- Cấu hình: GROUP_BASE, B2_FULL, và MR_FULL nếu V-03 đã chốt (chưa chốt → ghi "chưa chạy, chặn bởi V-03"). 1 lượt sinh,
  seed 101, cùng mẫu câu cho mọi cấu hình.
- Đầu ra: `report.md` cho từng run: acc / err / neither / parse_failed / early_exit, theo loại câu, Evidence Recall@k,
  latency p50/p95, token, số lời gọi; McNemar từng cặp B2_FULL–GROUP_BASE và B2_FULL–MR_FULL (`b lên / c xuống, p`);
  dự toán chi phí cho P4–P6 từ số đo.
- Log phải lưu: như 2W-08; thêm endpoint, concurrency phía client, khung giờ chạy trong `run_manifest.json`.
- Hoàn thành khi: `n_valid = n_expected` hoặc có danh sách câu thiếu kèm lý do; dự toán đã gửi nhóm. Cỡ pilot **không đủ**
  để kết luận — chỉ để quyết bước tiếp.

### P4 — Ablation

**2W-10 · Ablation trên cùng mẫu `internal_dev`**
- Phụ thuộc: 2W-09, S-07; V-01 cho MR_MINUS_*
- Thứ tự (mỗi lượt một biến, báo cáo riêng): B2_NO_BM25 → B2_NO_VECTOR → B2_NO_ENT → HYBRID_NO_GRAPH → MR_MINUS_I →
  MR_MINUS_RCHUNK → MR_MINUS_REDGE (ba lượt cuối chỉ khi V-01 có định nghĩa; MR_MINUS_I cần index riêng — dự toán trước).
- So sánh: ablation B2 so với **B2_FULL**; ablation MR so với **MR_FULL**; không so với ablation chạy ngay trước.
- Đầu ra: mỗi lượt một thư mục run + `report.md` (chất lượng, chi phí, McNemar, ví dụ lên/xuống có bằng chứng).
- Log phải lưu: như 2W-08. Với B2_NO_ENT: lưu sha256 phần Sources của từng câu để chứng minh trùng B2_FULL.
- Hoàn thành khi: mọi lượt có đối chứng; kết quả âm vẫn ghi; không index lại khi index không đổi.

### P5 — Phân tích và một điều chỉnh

**2W-11 · Failure taxonomy, đề xuất một thay đổi**
- Phụ thuộc: 2W-10
- Hành động: phân loại lỗi trên `internal_dev` (truy hồi trượt đoạn gold, có đoạn gold nhưng sinh sai, thoát sớm, judge
  nghi sai…). Nếu đề xuất thay đổi, phải đủ 5 bước của CLAUDE.md §1b (vấn đề quan sát được → giả thuyết → cơ chế →
  thí nghiệm có kiểm soát → hiệu quả đo được) và chỉ đổi **một** thành phần. Đổi top-k, temperature, prompt, embedding
  hay model **không** phải phương pháp.
- Đầu ra: đăng ký trước trong `docs/research/EXPERIMENT_HISTORY.md` (giả thuyết, cấu hình, phép so, ngưỡng) **trước khi
  chạy**; rồi run + report.
- Hoàn thành khi: không dùng câu `internal_test`; lịch sử mọi lượt thử (kể cả thất bại) có trong ledger.

### P6 — Xác nhận

**2W-12 · Xác nhận trên toàn `internal_dev`**
- Phụ thuộc: 2W-11
- Cấu hình: các cấu hình được chọn × **3 lượt sinh** (seed 101 / 202 / 303, cùng danh sách cho mọi nhánh) × số lượt chấm
  chốt trước (đề xuất 3).
- Thống kê: ghép theo `query_id`; McNemar cho từng lượt sinh, paired bootstrap theo query giữ cấu trúc query × lượt.
  sd giữa lượt sinh và sd giữa lượt chấm báo **riêng**, không gộp dưới một dấu ±. Không kết luận "tương đương" chỉ vì
  p lớn; nếu cần kết luận không kém hơn, biên phải chốt trước khi xem số. Ở LiHua nhiễu giữa lượt sinh lớn hơn nhiễu
  judge nhiều lần (CLAUDE.md §3) — thiếu lượt lặp thì phải ghi.
- Hoàn thành khi: mỗi run đạt định nghĩa "completed" (mục 4.3); Người 1 kiểm chéo một mẫu.

### P7 — Bàn giao

**2W-13 · Tổng hợp và bàn giao**
- Phụ thuộc: 2W-12
- Đầu ra (mục 4.4) + cập nhật `docs/research/PROJECT_STATE.md`, `BASELINE_MANIFEST.yaml`, `EXPERIMENT_HISTORY.md`,
  `CODE_MAP.md` (khi code đổi): artifact nằm ở đâu, ai chịu trách nhiệm.
- Hoàn thành khi: backup đã kiểm; người khác chạy lại được metric từ `per_question.csv`; giới hạn ghi đủ (không cần kết quả
  dương để chuyển sang SLM khác).

### P8 — Sau các đợt SLM (không thuộc đợt này)

Đóng băng phương pháp → chạy `internal_test` → GPT-4o chấm **cùng một tập câu trả lời** của mọi nhánh được báo cáo (nhóm
duyệt chi phí trước). Không so số Gemini chấm với số GPT-4o chấm.

---

## 4. Log và artifact

### 4.1 Mỗi run phải có

| File | Nội dung bắt buộc | Ghi lúc |
|---|---|---|
| `run_manifest.json` | experiment_id, run_id, cấu hình đầy đủ + `config_hash`, seed, version prompt/rubric, môi trường, sha256 index và split, endpoint, concurrency, khung giờ, người chạy, lệnh chạy, `status` (planned · running · partial · completed · failed · invalid) | đầu run, cập nhật cuối run |
| `retrieval.jsonl` | query_id, đầu ra parser từ khoá (thô + đã parse), ứng viên / hạng / điểm từng nhánh, chunk chọn, điểm cắt A1, lý do thoát sớm | ngay sau mỗi câu |
| `generation.jsonl` | messages thực gửi Qwen, context đầy đủ (Entities + Sources), response thô, answer đã xử lý, status | ngay sau mỗi câu |
| `judge.jsonl` | rubric version, đầu vào judge, model gọi, model trả về, response thô, nhãn, pass_id, lỗi | ngay sau mỗi verdict |
| `events.jsonl` | start/end, lỗi, timeout, retry, resume, checkpoint, thoát sớm | ngay khi xảy ra |
| `per_question.csv`, `metrics.json` | ghép cặp được theo query; metric tính lại được | cuối run |
| `report.md` | kết luận, giới hạn, ví dụ lên/xuống, chi phí, lệnh tái lập, quyết định tiếp | cuối run |

Mọi bản ghi có `dataset_id`, `experiment_id`, `run_id`, `query_id`, `gen_repeat`, `seed`, `request_id`/`pair_id`, `attempt`,
`timestamp` (UTC). Ghi từng dòng rồi flush ngay: process chết thì phần đã xong vẫn dùng lại được. Ghi cả cache hit,
context `None`, parse từ khoá hỏng và lỗi API — không chỉ câu thành công. Retry giữ dấu vết attempt; metric chỉ tính bản
ghi `ok` cuối cùng của mỗi khoá. Gold chỉ nằm ở `gold.jsonl`, không đi vào generation.

### 4.2 Resume

Resume theo khoá `(query_id, gen_repeat, config_hash)`. Thư mục run có `config_hash` khác cấu hình đang chạy → runner phải
từ chối ghi tiếp. Lỗi hạ tầng là `infra_failed`, không bao giờ thành câu trả lời sai hay từ chối.

### 4.3 Một run chỉ "completed" khi

- đủ câu dự kiến, hoặc có danh sách thiếu kèm lý do được phân loại;
- request / context / answer / judge ghép được bằng ID; không lỗi parse bị che;
- manifest và checksum index/split khớp protocol;
- metric tính lại được từ `per_question.csv`;
- `report.md` nêu cả lên lẫn xuống, có ví dụ lỗi kèm bằng chứng và giới hạn;
- có lệnh tái lập, backup đã kiểm (mở được, sha256 khớp), Người 1 kiểm chéo một mẫu.

### 4.4 Bàn giao cuối luồng

Protocol + mọi manifest; index + `index_requests.jsonl`; toàn bộ run artifact thô; script và lệnh tái lập;
`per_question.csv`; `metrics.json`; `report.md`; ledger `docs/research/EXPERIMENT_HISTORY.md`. File gitignore **vẫn phải**
được lưu ở `<BACKUP_ROOT>` kèm sha256 — gitignore chỉ có nghĩa là không vào Git. Chưa xoá bản local khi backup chưa được
kiểm.

### 4.5 Bảng phải có trong báo cáo 2Wiki

| Bảng | Cột tối thiểu |
|---|---|
| So sánh chính | dataset, model, cấu hình, protocol, n valid / expected, Acc, Err, Neither, nguồn biến thiên của ±, Δ so với baseline cùng giao thức, McNemar |
| Ablation MiniRAG | MR_FULL, −I, −Rchunk, −Redge (ô chưa chạy để trống / ghi "chưa chạy") |
| Ablation B2 | B2_FULL, NO_BM25, NO_VECTOR, NO_ENT, HYBRID_NO_GRAPH; chất lượng và chi phí |
| Theo loại câu | compositional, comparison, bridge_comparison, inference: n, Acc, Err; từ chối sai trên câu có đáp án (không có loại null) |
| Truy hồi | Evidence Recall@k theo đoạn gold; Full Evidence Success@k (mọi đoạn gold của câu nằm trong Sources) |
| Hiệu năng | thời gian index, retrieval p50/p95, end-to-end p50/p95, dung lượng index, số lời gọi, token, chi phí |
| Judge audit | model ID + rubric version, số mẫu đối chiếu, tỷ lệ bất đồng, ghi chú rà tay |
| Tham chiếu bài báo | cột riêng, ghi "tham chiếu, không phải đối chứng" |

Mọi bảng ghi rõ split (`internal_dev` hay `internal_test` — **test nội bộ tách từ dev chính thức**), model, judge, protocol,
số lượt sinh / lượt chấm, ý nghĩa của ± hoặc CI.

---

## 5. Endpoint, tài nguyên, ngân sách

- Endpoint Qwen **có thể dùng chung** với Người 1. Điều kiện: lịch chạy ghi trong `docs/research/RUN_SCHEDULE.md`
  [CẦN TRIỂN KHAI]; mỗi run ghi endpoint, concurrency phía client và khung giờ vào `run_manifest.json`. Endpoint Modal hiện
  có (`reproduce/modal_slm.py`) chạy `max_containers=1` → hai người chạy cùng lúc là tranh một GPU: **không đo latency**
  khi người kia đang chạy; đo latency ở cùng phần cứng, cùng tải, tách warm/cold, tách thời gian model với toàn pipeline.
- Không mặc định tăng concurrency là nhanh hơn hay rẻ hơn.
- Ngân sách: trần tổng cho compute của cả đợt (hai người) **dưới 1 triệu VND**. Trước mỗi pilot/run lớn: hỏi nhóm phần còn
  lại, đặt trần cho lượt đó, dừng khi chạm trần.
- Công thức (không phải dự toán):
  - lời gọi index ≈ số chunk × 2 + retry (số thật từ `2W-05`);
  - số answer = số câu × số cấu hình cần sinh × số lượt sinh; lời gọi QA ≈ số answer × 2 (parser + sinh; HYBRID_NO_GRAPH
    chỉ 1);
  - số verdict = số answer × số lượt chấm + retry + audit.
- Cỡ tham chiếu (ước lượng tĩnh, **chưa đo**): pool 500 câu → 3.324 đoạn → khoảng 6.650 lời gọi index nếu mỗi đoạn một
  chunk. Không quy ra tiền hay giờ trước khi có số đo pilot.
- Gemini: không mặc định miễn phí; ghi khoá/quota dùng cho mỗi lượt chấm. GPT-4o chỉ ở P8, cần nhóm duyệt.

---

## 6. Còn thiếu — và chặn bước nào của bạn

| # | Chưa có | Chặn | Ai xử lý |
|---|---|---|---|
| 1 | Cách tác giả dựng corpus/sample 2Wiki | chốt N (2W-03); tên gọi "tái hiện" trong báo cáo | V-02 — bạn |
| 2 | ID model Gemini Flash | 2W-08 | V-06 — bạn |
| 3 | Định nghĩa hiện thực −I / −Rchunk / −Redge | MR_MINUS_* trong 2W-10 | V-01 — cả hai |
| 4 | Ánh xạ "top-k = 5 documents", "6000 tokens", k, n của bài báo vào code | MR_FULL trong 2W-09 | V-03 — Người 1 |
| 5 | Sampling mặc định của vLLM, HF revision | 2W-05 | V-04 — Người 1 |
| 6 | Ảnh hưởng của `llm_model_max_token_size=200` | kết luận chất lượng đồ thị ở 2W-06 | V-05 — Người 1 |
| 7 | Cấu trúc `id_aliases.json` | rubric alias (S-06), 2W-02 | bạn, trong 2W-02 |
| 8 | `<BACKUP_ROOT>` và quyền truy cập | đánh dấu completed từ 2W-06 | nhóm |
| 9 | Ngân sách còn lại thực tế | 2W-06, 2W-09 | nhóm |
| 10 | Commit index mới vào Git hay chỉ backup ngoài | 2W-06 | nhóm (S-02) |

Giới hạn đã biết, ghi sẵn vào Limitations: corpus 2Wiki do nhóm dựng (chưa chắc giống bài báo); `internal_test` tách từ dev
chính thức, không phải test chính thức; distractor dùng chung giữa hai phía split; BM25 cắt tên có dấu; judge Gemini Flash
khác GPT-4o của bài báo; 2Wiki là dataset công khai lâu năm nên có thể đã nằm trong dữ liệu huấn luyện của Qwen (bài báo
cũng nêu rủi ro này với dataset cũ, Phụ lục A.1).

---

## 7. Bắt đầu từ đâu

1. Đọc mục 1, rồi đọc mục B của kế hoạch chung để cùng Người 1 chốt protocol (S-01).
2. Làm ngay, không cần API hay code mới: **S-02** (worktree, `.gitignore`, bốn file trạng thái) và **2W-01** (ráp zip, kiểm
   sha256).
3. Tiếp theo: **V-02** (tìm cách tác giả dựng corpus 2Wiki), **V-06** (ghim ID Gemini Flash), rồi **S-07** và **S-08**.
4. Sau khi S-09 xong: 2W-02 → 2W-03 → 2W-04, rồi mới đến P1.
