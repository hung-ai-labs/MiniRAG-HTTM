# Thành viên 1 — Cắt tỉa và chấm lại đường đi trong đồ thị

> Giao 15/09/2026 · mã cũ: **A2** ([`../archive/KE_HOACH_TRIEN_KHAI.md`](../archive/KE_HOACH_TRIEN_KHAI.md)), task **15d** trong
> [`ROADMAP.md`](../../ROADMAP.md) · loại: **Designed Mechanism hợp lệ** ("path re-weighting", [`CLAUDE.md`](../../CLAUDE.md) §1b).
> Chạy song song được với sàng lọc BM25 (Hùng) và việc của thành viên 2 — **đọc mục 7 trước khi sửa code**.

## 1. Việc cần làm

Làm phần duyệt đường đi của MiniRAG **rẻ hơn** (Efficiency) và/hoặc **xếp chunk đáp án lên cao hơn** (Quality). Đo offline
trên index Qwen đã commit. Hành vi mặc định không được đổi.

## 2. Observed Problem — số đã có

| Quan sát | Số | Nguồn |
|---|---|---|
| Thực thể khởi đầu mỗi câu | trung vị **92** | `logs/screening/b1/offline_report.txt` (dev 180, index Qwen) |
| Đường đi 2 hop phải duyệt mỗi câu | trung vị **19.504** | cùng nguồn |
| Thời gian dựng context mỗi câu | trung vị **~5,0 giây**, chưa tách được phần của đồ thị | cùng nguồn |
| Chunk đáp án trong 30 chunk xếp hạng đồ thị | **61,8%** — top-30 vector thuần: 87,0% | `logs/diag_path2chunk_report.txt` |
| Chunk đáp án còn lại sau cắt 4.000 token (xếp hạng đồ thị) | **47,3%** | cùng nguồn |
| Bỏ hẳn xếp hạng đồ thị (vector thuần) so với V3 | 80 lên / 61 xuống, p = 0,13 → đồ thị chưa chứng minh đóng góp | [`../KET_QUA_HIEN_TAI.md`](../KET_QUA_HIEN_TAI.md) |
| Đường nhận phiếu cạnh — index **Gemini** cũ | 971 / 22.879 = **4,2%** | KE_HOACH mục A2 — **chưa đo lại trên Qwen** |

**Trong code** — hàm `_build_mini_query_context`, `minirag/operate.py`:
- Mỗi thực thể khởi đầu bung **cố định 2 hop** bằng `get_neighbors_within_k_hops(key, 2)`, không cắt tỉa trước khi chấm.
- `cal_path_score_list` (`minirag/utils.py:404`) chỉ **đếm** số node đúng kiểu câu trả lời trên đường, không dùng độ khớp cosine.
- `edge_vote_path` (`minirag/utils.py:416`) cộng phiếu cho đường chứa cạnh lấy từ `relationships_vdb`; đường không có phiếu
  vẫn được mang tiếp sang `path2chunk`.
- Hub lớn nhất của đồ thị Qwen là `LIHUA` (bậc 331) — hub sinh phần lớn đường đi.

## 3. Giả thuyết

- **H-E (Efficiency).** Phần lớn đường đi không nhận phiếu cạnh và không làm đổi 30 chunk đồ thị cuối cùng. Bỏ chúng sớm sẽ
  giảm mạnh thời gian dựng context trong khi xếp hạng gần như không đổi.
- **H-Q (Quality).** Chấm đường theo độ khớp với câu hỏi (cosine của thực thể khởi đầu và của node trên đường) thay vì đếm node
  đúng kiểu sẽ đưa chunk đáp án lên cao hơn trong xếp hạng đồ thị, nhất là với câu Multi.

Bước 0 có thể bác một hoặc cả hai giả thuyết. Nếu vậy thì sửa giả thuyết **trước** khi viết cơ chế.

## 4. Kế hoạch — theo thứ tự, mỗi biến thể đổi đúng một biến

| Bước | Việc | Đầu ra |
|---|---|---|
| 0 | **Đo, chưa sửa gì.** Thời gian từng khâu trong `_build_mini_query_context` (tra `entity_name_vdb`, bung 2 hop, `get_node_from_types`, `cal_path_score_list`, tra `relationships_vdb`, `edge_vote_path`, `path2chunk`, `kwd2chunk`); tỉ lệ đường nhận phiếu cạnh; tỉ lệ đường góp vào 30 chunk đồ thị cuối. | `logs/path/step0_report.txt` |
| 1 | **Đăng ký trước** (mục 6): chốt cơ chế P1, P2, chỉ số, cổng, dự báo. Commit **trước** khi chạy biến thể nào. | commit file này |
| 2 | **P1 — cắt tỉa** (Efficiency), bật bằng `MINIRAG_PATH_PRUNE=<tên>`. | `logs/path/p1_offline_report.txt` |
| 3 | **P2 — chấm có trọng số** (Quality), bật bằng `MINIRAG_PATH_SCORE=<tên>`, đo riêng, không gộp với P1. | `logs/path/p2_offline_report.txt` |
| 4 | Gửi báo cáo offline cho nhóm. **Chạy QA chỉ khi nhóm duyệt**, và phối hợp với Hùng để thêm biến thể vào bộ sàng lọc — không tự sửa `reproduce/screening/`. | — |

**Không phải cơ chế** (CLAUDE.md §1b): đổi số hop 2 → 1, đổi `top_k`, đổi ngưỡng cosine đơn thuần. Những thứ đó chỉ được làm
như sensitivity study. Cắt tỉa phải là **một quy tắc** — ví dụ bỏ đường không chạm thực thể quan trọng hay cạnh được bỏ phiếu —
chứ không phải hạ một con số.

## 5. Đo thế nào — offline, không sinh, không chấm

- **Câu hỏi:** 180 câu dev có evidence. Nhãn chunk đáp án ở `logs/diag_path2chunk.jsonl`, **chỉ dùng để chấm**, không bao giờ
  dùng lúc chạy.
- **Index:** `LiHua-World-qwen-modal/`, chỉ đọc.
- **Hai chế độ:** đồ thị thuần (mặc định MiniRAG) và `MINIRAG_CHUNK_FUSION=rrf` (V3), để biết cải thiện ở đồ thị có còn khi trộn không.
- **Ghép cặp:** mặc định và biến thể phải dùng cùng một lần rút parser. Dùng cache parser riêng, khởi tạo từ cache sàng lọc:

```bash
mkdir -p logs/path/cache
cp logs/screening/cache/kw_cache.jsonl logs/path/cache/kw_cache.jsonl
export MINIRAG_KW_CACHE=$PWD/logs/path/cache/kw_cache.jsonl
```

  Lần đầu sẽ gọi SLM cho khoảng 100 câu dev chưa có trong cache. Cài đặt và Modal:
  [`reproduce/screening/HUONG_DAN_CHAY.md`](../../reproduce/screening/HUONG_DAN_CHAY.md) bước 1–2 (không cần khoá Gemini).
- **Số liệu từng câu:** đặt `MINIRAG_CONTEXT_LOG=<file.jsonl>`; mỗi truy vấn ghi `graph_ids`, `ranked_ids`, `chunk_ids` (sau cắt
  4.000), `context_sha256`, `graph_seeds`, `graph_paths`, `retrieval_ms`. Số đường sau cắt tỉa và thời gian từng khâu thì ghi
  vào log riêng của bạn, không thêm trường vào log này.
- **Chạy script** qua wrapper có sẵn (tự nạp endpoint, khoá, `--model`, `--workingdir`):

```bash
SCREEN_SCRIPT=reproduce/path/eval_offline.py reproduce/screening/run_screen.sh
```

  Có thể `import screen_variant` để dùng lại `evidence()`, `mcnemar_p()`, `dev_rows()`, `gold_map()` — chỉ import, không sửa.
  **Đừng gọi** `contexts()`, `run_query()`, `set_env()` của nó: các hàm này ép cache parser trỏ vào `logs/screening/` của Hùng.

| Chỉ số | Cách tính |
|---|---|
| Thời gian dựng context | trung vị và p90 của `retrieval_ms`, cộng thời gian riêng phần đường đi |
| Khối lượng | số đường trước / sau cắt tỉa |
| Độ ổn định xếp hạng | số câu có `graph_ids` giống hệt mặc định; độ trùng top-30 |
| Chunk đáp án | tỉ lệ nằm trong 30 chunk đồ thị; tỉ lệ nằm trong `chunk_ids` (sau cắt 4.000) |
| Câu đủ đáp án | mọi chunk đáp án đều trong `chunk_ids`; ghép cặp từng câu, McNemar |
| Theo loại | tách Single và Multi (Null không có evidence) |

**Gợi ý cổng** — chốt chính thức ở mục 6:
- **P1:** thời gian dựng context trung vị giảm ≥ 30%; chunk đáp án sau cắt 4.000 (đồ thị thuần) giảm không quá 1 điểm; không có
  McNemar "xuống" với p < 0,05; Multi không mất quá 1 câu.
- **P2:** câu đủ đáp án (đồ thị thuần) net ≥ +9 **và** p < 0,01 — cùng cổng R1 của BM25; ở chế độ `rrf` net ≥ 0.

## 6. Đăng ký trước — điền và commit TRƯỚC khi chạy P1 / P2

```
Ngày chốt: 2026-09-17
Kết quả bước 0 (3 số chính):
- Thời gian truy hồi trung vị: 4109,1 ms (p90: 8904,8 ms)
- Khối lượng đường đi 2-hop: trung vị 19.994 đường (p90: 28.383 đường) từ 96 thực thể khởi đầu
- Tỉ lệ giữ chunk đáp án: top-30 đồ thị đạt 62,3%, sau cắt A1@4000 còn 46,4% (Multi: 28,6% đủ đáp án)

P1 — quy tắc cắt tỉa (mô tả đủ để người khác cài lại):
- Bỏ các đường 2-hop đi qua hub bậc cao (>100) nếu đường đó không chứa node thuộc maybe_answer_list hoặc không nằm trong danh sách cạnh có phiếu (edge_vote).
- Với mỗi seed entity, chỉ giữ tối đa K đường có liên quan ngữ cảnh cao nhất thay vì bung toàn bộ 2-hop.

P2 — công thức điểm:
- Score(Path) = (1 + count(maybe_answer_nodes)) * (1 + edge_votes) * Sim(seed_entity, query)

Chỉ số chính của P1 / P2:
- P1: Thời gian dựng context (retrieval_ms), số đường duyệt (paths), tỉ lệ giữ chunk đáp án sau A1@4000.
- P2: Tỉ lệ câu giữ đủ đáp án (full_answer_pct) và McNemar p-value.

Cổng P1 / P2 (số cụ thể):
- Cổng P1: retrieval_ms trung vị giảm ≥ 30% (từ 4109 ms xuống ≤ 2876 ms); chunk đáp án sau A1@4000 không giảm quá 1,0% (≥ 45,4%); Multi không mất quá 1 câu (giữ ≥ 5 câu đủ).
- Cổng P2: Câu đủ đáp án (đồ thị thuần) net ≥ +9 câu và McNemar p < 0,01 so với baseline.

Dự báo:
- P1: Số đường giảm từ ~20.000 xuống < 5.000 đường, thời gian giảm ~40-50%, độ giữ chunk đáp án giữ nguyên hoặc nhích nhẹ do giảm nhiễu.

Trượt cổng thì ghi gì vào ROADMAP:
- "P1/P2 không vượt qua baseline: việc cắt tỉa đường đi đồ thị làm mất ngữ cảnh kết nối gián tiếp (Multi-hop)".
```

## 7. Ranh giới — để không đụng Hùng và thành viên 2

**Được tạo / sửa**
- `minirag/path_rerank.py` (mới): toàn bộ logic cắt tỉa và chấm điểm.
- Trong `_build_mini_query_context`: **chỉ** đoạn từ vòng `get_neighbors_within_k_hops` tới lời gọi `path2chunk(...)`, và chỉ để
  gọi hook bọc trong biến môi trường. Không đặt biến thì context phải **giống hệt từng byte** — kiểm bằng `context_sha256` trên
  180 câu trước khi mở PR.
- `minirag/utils.py`: được **thêm hàm mới**; không đổi hành vi của `cal_path_score_list`, `edge_vote_path`.
- `reproduce/path/`, `logs/path/` (mới).

**Không được sửa**
- Khối trộn chunk và ghi log ở cuối `_build_mini_query_context` (từ comment `# MINIRAG_CHUNK_FUSION=rrf` tới hết hàm), các dòng
  `_t0`, `_n_seeds`, `_n_paths`; các hàm `_rrf_fuse`, `_bm25_index`, `_keyword_llm`, `minirag_query`; `minirag/bm25.py` — **Hùng**.
- `reproduce/screening/`, `logs/screening/` — **Hùng** (chỉ đọc hoặc copy).
- `LiHua-World-qwen-modal/` — index chung, chỉ đọc (CLAUDE.md §4).
- `reproduce/entity_resolution/`, `logs/entity_resolution/`, `LiHua-World-qwen-entres/` — **thành viên 2**.

**Git:** làm trên nhánh `tv1/path-pruning` tách từ `dev`. Mở PR vào `dev` sau khi có báo cáo offline và đã kiểm "mặc định giống hệt".

## 8. Chi phí, rủi ro, nếu không ăn thua

- **Chi phí:** CPU là chính; khoảng 100 lời gọi parser trên Modal của bạn (vài phút GPU). Bước 0–3 không tốn lượt chấm Gemini.
- **Rủi ro:** cắt tỉa quá tay giết đúng câu Multi, nhóm cần đường dài nhất — luôn báo Multi riêng. Bỏ bớt đường qua hub là cách
  giảm khối lượng dễ nhất, và cũng dễ mất đáp án nhất.
- **Nếu không ăn thua:** P1 "giảm X% thời gian, xếp hạng không đổi" vẫn là một kết quả Efficiency hoàn chỉnh. P2 trượt cổng thì
  ghi kết quả phủ định vào ROADMAP — đó vẫn là kết quả khoa học hợp lệ.
