# Graph repair — Giai đoạn 1: CHẨN ĐOÁN (chưa có cơ chế mới)

Ngày giao: 08/11/2026 · Nhánh: `graph-repair` (tách từ `c123-benchmark-fixes`, commit `423707d`)

## Mục tiêu của cả hướng

Nhóm muốn **thắng MiniRAG gốc ngay trên cơ chế đồ thị** — giữ nguyên "cổng đồ thị" (mọi chunk vào
Sources phải đi qua xếp hạng của đồ thị), **không** thêm kênh vector/BM25/RRF/reranker. Trước khi đề xuất
cơ chế, phải biết chính xác đồ thị làm rơi chunk đáp án ở đâu và vì sao. Giai đoạn 1 chỉ làm việc đó.

**Giai đoạn này KHÔNG thiết kế, KHÔNG đo cơ chế mới.** Cơ chế sẽ được đăng ký trước (pre-register) ở
giai đoạn 2, dựa trên báo cáo của giai đoạn 1.

## Bối cảnh đã biết (đừng đo lại, chỉ dùng)

- Code trong repo là code chính thức `HKUDS/MiniRAG` (`e204d23` = HEAD upstream), phần truy hồi chưa đổi
  thuật toán từ commit đầu `4176657`. Các thay đổi của nhóm đều nằm sau công tắc env.
- Luồng mini-mode: `minirag/operate.py` `_build_mini_query_context` (~dòng 1355) → `cal_path_score_list`,
  `edge_vote_path` (`minirag/utils.py` ~404–437) → `path2chunk` (~1129, `max_chunks=3`) → `kwd2chunk`
  (~1310) → A1 cắt Sources 4000 token (~1590). Đồ thị: `minirag/kg/networkx_impl.py`
  (`get_neighbors_within_k_hops` số hop đóng cứng 2, `get_node_from_types`).
- Đồ thị không có node chunk; chunk là thuộc tính `source_id` (ngăn bởi `<SEP>`) của node/cạnh.
- `kwd2chunk` chỉ duyệt **thực thể khởi đầu (seed)** trong `ent_from_query_dict`; mỗi seed chỉ góp
  **tối đa 3 chunk** (`v["Path"]` do `path2chunk` chọn). Điểm chunk =
  Σ Score(seed) × (×2 nếu seed khớp nhất với từ khoá) × (×10 nếu chunk số 1 của seed ∈ top-30 vector).
- Kết quả offline C0–C3 đã có ở `logs/c_ablation/graph/C{0..3}/` (180 câu dev có Evidence, A1@4000):
  C0 retention top-30 62,3% / sau A1 46,4% / 75 câu giữ đủ đáp án. Tập ứng viên của `kwd2chunk`
  (trung vị 119 chunk) chứa 68,1% chunk đáp án, phủ đủ 115/180 câu.
- Đọc thêm: `reproduce/path/SCORE_FLOW.md`, `reproduce/path/C_ABLATION.md`,
  `logs/retrieval_audit/README.md` (hướng reranker tất định đã ĐÓNG — đừng mở lại),
  phụ lục bài báo `miniRAG1.pdf` mục 3.2.2 (tr. 37125–37126) và Phụ lục B (tr. 37136).

## Quy tắc cứng

1. **Không gọi API nào** (Gemini, OpenAI, Modal...). Mọi lần chạy đặt `MINIRAG_KW_CACHE_ONLY=1` với cache
   `logs/path/cache/kw_cache.jsonl` (200 dòng, đã có). Đặt `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
   `TIKTOKEN_CACHE_DIR=E:\Project\MiniRAG\data-gym-cache`.
2. **Không sửa, xoá, ghi đè** bất kỳ thư mục index nào (`LiHua-World-*`, `indexes/`, `runs/`, `.worktrees/`).
   `eval_offline.py` đã chạy trên bản sao tạm — giữ nguyên cơ chế đó. Nếu sandbox chặn `%TEMP%`, đặt
   `TMP`/`TEMP` vào `logs/graph_repair/tmp/` (tự tạo).
3. **Không sửa** `baseline.yaml`, `.gitignore`, `reproduce/demo/*`, và không đụng các file đang dở dang
   trong working tree không thuộc việc này.
4. Mọi thay đổi trong `minirag/` phải **mặc định tắt** (env rỗng ⇒ hành vi byte-identical). Chứng minh
   bằng phép kiểm hồi quy ở T0.
5. **Không commit.** Để thay đổi trong working tree; người giao việc sẽ review rồi commit.
6. Trên Windows, `TemporaryDirectory` trong `eval_offline.py` crash khi dọn (`minirag.log` còn mở). Sửa
   bằng `ignore_cleanup_errors=True` trong file đó là được phép.
7. Báo cáo con số đúng như đo được. Không làm tròn cho đẹp, không bỏ ca xấu.

## Nhiệm vụ

### T0 — Khung chẩn đoán + kiểm hồi quy

- Thêm env `MINIRAG_DIAG_LOG=<đường dẫn jsonl>` (mặc định tắt). Khi bật, mỗi truy vấn ghi một dòng chứa
  đủ nội tại để T1–T2 tính offline, tối thiểu:
  - từ khoá truy vấn (`ent_from_query`), `type_keywords`, `len(maybe_answer_list)`;
  - mỗi seed: tên, Score (cosine), từ khoá đã khớp nó + hạng trong danh sách khớp, có bị loạt
    "short path 20%" loại không, bậc trong đồ thị, `df` = số chunk trong `source_id`, số đường;
  - mỗi seed: 3 chunk được chọn (`v["Path"]`) và **toàn bộ** `node_chunk_id` / `count_dict` trước khi cắt
    còn 3 (để biết chunk đáp án bị loại ở bước chọn top-3 hay chưa từng xuất hiện);
  - số lần bộ lọc Levenshtein (`calculate_similarity`, operate.py ~1179) chạy và số chunk nó loại;
  - danh sách chunk của `kwd2chunk` kèm phân rã đóng góp: với mỗi chunk, danh sách
    (từ khoá, seed, Score, có ×2 không, có ×10 không, contribution);
  - tập "reachable": hợp `source_id` của mọi node nằm trên mọi đường (kể cả seed) và, tách riêng, của
    các cạnh trên đường;
  - top-30 vector (`chunks_ids`), top-30 `kwd2chunk`, danh sách sau A1.
- Thêm `--top-k` cho `reproduce/path/eval_offline.py` (truyền vào `QueryParam(top_k=...)`; lưu ý
  `QueryParam.top_k` mặc định đọc env `TOP_K` lúc import). Mặc định 60.
- **Kiểm hồi quy bắt buộc:** chạy C0 (`--arm C0`, fusion graph) với DIAG bật và tắt; `chunk_ids` của cả
  180 câu phải trùng khớp với `logs/c_ablation/graph/C0/C0_records.jsonl`. Ghi kết quả kiểm vào báo cáo.
- Thêm test trong `tests/` cho: DIAG tắt ⇒ không ghi gì, không đổi đầu ra.

### T1 — Kiểm chứng thực nghiệm các thành phần "chết"

Chạy trên C0, 180 câu dev có Evidence, top_k 60:

- **D1 — Công thức (3) của bài báo không ảnh hưởng đầu ra?** Thêm env chỉ dùng cho chẩn đoán
  `MINIRAG_DIAG_PATH_SCORE=zero|shuffle` (mặc định tắt) ghi đè điểm đường đi sau `edge_vote_path`
  (`zero`: mọi `[a, e]` = `[0, 0]`; `shuffle`: hoán vị ngẫu nhiên các `[a, e]` trong mỗi seed, seed RNG cố
  định 13). Đếm số câu có `chunk_ids` khác C0. Giả thuyết: 0/180 với code upstream (vì `path2chunk` chỉ
  dùng `count_dict` của đường cuối và nhân hằng số). Nếu khác 0, giải thích vì sao.
- **D2 — Answer-aware:** phân bố `len(maybe_answer_list)` với `MINIRAG_ANSWER_TYPE_FIX=0` và `=1`; số
  đường có `a > 0`.
- **D3 — Bộ lọc Levenshtein** (thứ gần nhất với "Step 2: Similarity Computation" trong bài báo): bao
  nhiêu câu nó chạy, loại bao nhiêu chunk, có loại chunk đáp án không.
- **D4 — Seed:** số seed/câu, tỉ lệ bị loại bởi "short path 20%", bao nhiêu câu có hub (bậc top-1%) làm
  seed.

### T2 — Quy trách nhiệm cho từng chunk đáp án bị mất (C0, top_k 60)

Với mỗi câu và mỗi chunk đáp án (gold lấy từ `reproduce/screening/screen_variant.py` `gold_map()`), xác
định **tầng đầu tiên làm mất nó**:

| Tầng | Định nghĩa |
|---|---|
| L0 `not_reachable` | Không nằm trong `source_id` của bất kỳ node nào trên bất kỳ đường nào |
| L1 `reach_not_cand` | Reachable nhưng không thuộc top-3 của seed nào (không vào `kwd2chunk`) |
| L2 `cand_not_top30` | Có điểm trong `kwd2chunk` nhưng ngoài top-30 |
| L3 `top30_not_a1` | Trong top-30 nhưng bị A1@4000 cắt |
| OK | Giữ lại |

Rồi phân rã tiếp:
- **L0:** chunk đáp án có thuộc thực thể nào không; thực thể đó có được khớp làm seed không (nếu không:
  cosine của nó với từ khoá gần nhất, hạng của nó); có nằm trong 2 hop từ seed nào không.
  Phân biệt "lỗi khớp seed" và "lỗi số hop / đồ thị thưa / thực thể nhân đôi" (ví dụ `LIHUA` và `LI HUA`).
- **L1:** chunk bị loại vì giới hạn 3 chunk/seed, vì bộ lọc Levenshtein, hay vì lỗi "chỉ đường cuối".
  Thứ hạng của nó trong `node_chunk_id` / `count_dict` của seed liên quan.
- **L2 + L3:** hạng của chunk đáp án; các chunk xếp trên nó được đóng góp chủ yếu bởi seed nào; tỉ lệ
  ngân sách A1 bị chiếm bởi chunk mà đóng góp lớn nhất đến từ hub (bậc hoặc `df` top-1% và top-5%);
  có bao nhiêu ca hệ số ×10 hoặc ×2 quyết định thứ tự (đếm phản thực tế: đặt riêng từng hệ số về 1 rồi
  tính lại thứ hạng **từ log**, không chạy lại pipeline — chỉ là ablation của hệ số đang có, không phải
  công thức mới).

Bảng tổng: số chunk đáp án và số câu ở mỗi tầng; tách Single / Multi.

### T3 — Độ bền theo `top_k`

Lặp T2 (rút gọn: bảng tầng + chỉ số hub + retention/đủ đáp án) với `--top-k 10` và `--top-k 5`. A1 vẫn
4000. Mục đích: xem kết luận "hub chiếm ngân sách" và phân bố tầng có giữ khi `top_k` nhỏ như bài báo ghi
(top-k 5) hay chỉ là hệ quả của mặc định 60.

### T4 — Báo cáo

Viết `reproduce/graph_repair/PHASE1_REPORT.md` (tiếng Việt), gồm:
1. Kết quả kiểm hồi quy T0.
2. D1–D4 với số liệu.
3. Bảng tầng mất mát T2 + phân rã + chỉ số hub; 5 ví dụ cụ thể (câu hỏi, chunk đáp án, tầng mất, seed
   chiếm chỗ).
4. Bảng độ bền T3.
5. Mục **"Ứng viên cơ chế cho giai đoạn 2"**: liệt kê tối đa 4 hướng *thuần đồ thị* mà số liệu ủng hộ,
   mỗi hướng ghi rõ: tầng nó nhắm, số câu tối đa nó có thể lấy lại (trần), rủi ro. **Không cài đặt, không
   đo** các hướng này.
6. Danh sách file đã tạo/sửa và lệnh tái tạo từng con số.

Đầu ra dữ liệu: `logs/graph_repair/phase1/` (jsonl log chẩn đoán, json tổng hợp). Script phân tích:
`reproduce/graph_repair/diagnose.py`.

## Tiêu chí hoàn thành

- [ ] Kiểm hồi quy C0: 180/180 `chunk_ids` trùng, DIAG bật lẫn tắt.
- [ ] `python -m pytest tests/test_path_score_flow.py tests/test_c_ablation.py` và test mới đều qua.
- [ ] Mọi con số trong báo cáo tái tạo được bằng lệnh ghi trong báo cáo.
- [ ] Không có lời gọi mạng nào; không file index nào bị đổi (`git status` sạch ở các thư mục index).
