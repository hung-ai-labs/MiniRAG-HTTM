# Đối chiếu bài báo MiniRAG với code công bố

Ngày: 08/11/2026 · Bài báo: MiniRAG, Proceedings of the 64th ACL (2026), tr. 37121–37144
(`miniRAG1.pdf` ở gốc repo) · Code: `HKUDS/MiniRAG` commit `e204d23` — trùng HEAD upstream
(`git ls-remote https://github.com/HKUDS/MiniRAG.git` ngày 08/11/2026).

Số dòng dưới đây là của **code upstream `e204d23`**, xem bằng `git show e204d23:<file>`. Phần truy hồi
mini-mode không đổi thuật toán từ commit đầu `4176657` (12/01/2025); các commit sau chỉ định dạng/lint.

**Giới hạn:** chúng tôi không biết tác giả chạy phiên bản code nào để ra bảng số trong bài. Bảng dưới
chỉ khẳng định *code công bố không hiện thực mô tả trong bài*, không khẳng định gì về bản nội bộ.

## Bảng đối chiếu

| # | Bài báo (mục, trang) | Code công bố (`e204d23`) | Hệ quả |
|---|---|---|---|
| 1 | §3.1, tr. 37123: đồ thị dị thể, **chunk là node**, cạnh entity–chunk có mô tả d_eβ | Không có node chunk. Chunk là thuộc tính `source_id` của node/cạnh entity. Đồ thị Qwen LiHua: 1.556 node, toàn entity | Đường đi chỉ đi qua cạnh entity–entity; quan hệ V_e–V_c không tham gia duyệt đồ thị |
| 2 | §3.2.1–3.2.2, tr. 37124–37125: Answer-Aware Entity Selection — chọn node đáp án **từ tập khởi đầu** theo kiểu dự đoán | `networkx_impl.py:160-164` lọc **toàn đồ thị**; `get_types` (`:155`) đưa kiểu viết thường cho LLM, nhưng node lưu `"EVENT"` viết hoa → khớp **0 node** | Thành phần chết trên mọi truy vấn (đã đo: 0 node chưa vá, 49 node đã vá — CLAUDE.md, G1) |
| 3 | Công thức (2), tr. 37125: ω_e(e) = Σ count(v̂, Ĝ_{e,k}) — số seed/node đáp án trong đồ thị con k-hop quanh cạnh | `operate.py:1321` lấy cạnh bằng tìm kiếm vector câu hỏi → `relationships_vdb`; `utils.py:416-429` đếm mỗi cạnh khớp là 1 | Công thức (2) không có trong code |
| 4 | Công thức (3), tr. 37125: ω_p = ω_v(v̂_s\|v_q)·(1 + Σω_e + Σcount), rồi **chọn top-k đường** cho mỗi cặp | `operate.py:1186` `total_score = a + e + 1`, **không nhân ω_v**; không có bước chọn top-k đường — mọi đường 2-hop đều dùng (trung vị ~20.000 đường/câu) | Không có lựa chọn đường theo điểm |
| 5 | §3.2.2: điểm đường đi quyết định chunk được chọn | `operate.py:1202/1206` chọn theo `count_dict` = **chỉ đường cuối** trong vòng lặp; bản đúng nằm trong comment `:1208`. Điểm đường là hằng số nhân đều mọi chunk của đường đó ⇒ thứ tự chỉ còn theo số lần xuất hiện | Công thức (3) **không ảnh hưởng đầu ra** (kiểm thực nghiệm: `PHASE1_REPORT.md` D1) |
| 6 | tr. 37126, Step 1 Candidate Filtering: lấy **giao** V̂_c ∧ V_c^q | `operate.py:1236`: chunk được ×10 nếu là chunk số 1 của seed và nằm trong top-`top_k/2` vector; chunk ngoài giao vẫn vào | Lọc giao thay bằng thưởng mềm |
| 7 | tr. 37126, Step 2 Similarity Computation: độ tương đồng câu hỏi ↔ **chunk ghép mô tả cạnh**, rồi xếp hạng | Không có. Gần nhất: `operate.py:1171-1173` so Levenshtein theo token giữa mô tả entity và câu hỏi, chỉ để **lọc** khi node có > 5 chunk | Bước xếp hạng chính của bài báo không tồn tại |
| 8 | Bảng A3/A4, tr. 37134: k = số hop **và** số đường top-k (4/10/50); n = độ dài đường (2/4/8) | Số hop đóng cứng 2 (`operate.py:1291`); `top_k` chỉ đổi số seed (`:1271`), số cạnh (`:1321`), số chunk vector và chunk ra (`:1375`); không có tham số n | Không dựng lại được A3/A4 từ code công bố |
| 9 | Phụ lục B, tr. 37136: top-k 5 tài liệu, giới hạn 6.000 token | `base.py:25` `top_k = 60`; `max_token_for_text_unit = 4000` (`base.py:29`) khai báo nhưng mini-mode không dùng ⇒ Sources **không bị cắt** (trung vị 22.839 token, max 33.412 — `measure_sources_cap.py`, dev 200) | Ngân sách context khác hoàn toàn; có câu vượt cửa sổ 32k của Qwen2.5-3B |
| 10 | Cạnh liên quan câu hỏi trên một đường đi phải được tính theo từng cạnh khi lấy chứng cứ | `operate.py:1138-1141` (upstream `e204d23`) tạo danh sách `source_id` từ mọi cạnh trong `pairs_append[path]` rồi lấy `[0]` — chỉ cạnh đầu đóng góp chunk; trung vị 98 cạnh liên quan nằm trên đường mỗi câu dev | Lỗi mã công bố; bản sửa `MINIRAG_EDGE_ALL=1` là finding tái tạo baseline, không phải đóng góp khoa học. Đăng ký và kiểm định riêng ở `cooc/REGISTRATION.md` |

## Thứ thực sự quyết định chunk nào vào context (code công bố)

```
điểm(c) = Σ  Score(seed) × [×2 nếu seed khớp nhất với từ khoá] × [×10 nếu chunk số 1 của seed ∈ top-30 vector]
         qua mọi (từ khoá, seed khớp từ khoá, c ∈ 3 chunk của seed)
```

Score(seed) là cosine tên entity ↔ từ khoá (`nano_vector_db_impl.py` trường `distance` = `__metrics__`).
Công thức (2), (3), lựa chọn top-k đường và Step 2 — phần "topology-enhanced retrieval" — không phần nào
tác động tới đầu ra. Đây là lý do mọi can thiệp vào điểm đường đi của nhóm (V1, P1, P2) đo ra không đổi.

## Mâu thuẫn số liệu trong chính bài báo

LiHua-World, Qwen2.5-3B, MiniRAG: Bảng 1 ghi 46,78 ± 4,55; Bảng 2 (ablation) ghi 46,93; CLAUDE.md của nhóm
trích 48,75 (chưa ghi nguồn — có thể là bản arXiv; cần kiểm lại trước khi trích trong báo cáo).

## Bằng chứng thực nghiệm bổ sung

Các phép kiểm thực nghiệm cho mục 2, 5, 7 và phân rã nơi mất chunk đáp án: `PHASE1_REPORT.md` (giai đoạn 1
của nhánh `graph-repair`).
