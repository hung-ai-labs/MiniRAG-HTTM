# Cải tiến cơ chế đồ thị — kế hoạch chia việc cho 2 người

Chốt 09/11/2026. Đọc kèm [PHASE1_REPORT.md](PHASE1_REPORT.md) (chẩn đoán), [PAPER_CODE_AUDIT.md](PAPER_CODE_AUDIT.md)
(9 điểm lệch code–bài báo) và CLAUDE.md §1b (thế nào là đóng góp hợp lệ).

## Mục tiêu

Thắng MiniRAG gốc **bằng chính cơ chế đồ thị**: Sources vẫn hoàn toàn do đồ thị chọn — không vector, BM25, RRF hay
reranker ngoài. Mốc là **C0** (MiniRAG gốc + bản vá answer-type + A1@4000, `top_k` 60).

## Chunk đáp án bị mất ở đâu (C0, 180 câu dev có Evidence, 207 chunk đáp án)

| Tầng | Chunk | Câu | Nghĩa |
|---|---:|---:|---|
| L0 không đường nào tới | 2 | 2 | Lỗi trích xuất lúc index — chỉ ghi Limitations |
| **L1** tới được, không được chọn | **70** | **69** | Chunk có trong Counter của một thực thể xuất phát nhưng ngoài 3 chunk được chọn (hạng trung vị 17,5) |
| **L2** là ứng viên, ngoài top 30 | 6 | 6 | Hạng 31–69 |
| **L3** trong top 30, bị A1 cắt | 33 | 31 | Hạng 4–29 (trung vị 12), hết 4.000 token |
| Giữ được | 96 | 75 câu đủ | |

Đã biết, không cần thử lại: điểm đường đi và bản vá answer-type **không đổi** chunk nào (0/180); bỏ thưởng ×10 / ×2 làm
**hại**; giảm `top_k` làm hại (75 → 60 → 48); cộng điểm đường đi thô (C2/C3 của Hùng) làm hại mạnh vì thực thể hub.

## Chia việc

| | **Người 1 — chọn chunk trong thực thể xuất phát** | **Người 2 — xếp chunk vào ngân sách Sources** |
|---|---|---|
| Nhánh git | `graph/seed-select` | `graph/source-pack` |
| Worktree | `.worktrees/seed-select` | `.worktrees/source-pack` |
| Tầng | L1 (trần lạc quan 69 câu) | L3 + L2 (trần lạc quan ~37 câu) |
| Được sửa | `path2chunk` trong `minirag/operate.py` | `kwd2chunk` và đoạn cắt A1 (`MINIRAG_TRUNCATE_SOURCES`) trong `_build_mini_query_context` |
| Tiền tố công tắc | `MINIRAG_SEL_*` (đã có: `MINIRAG_FLOW_SPEC`, `MINIRAG_FLOW_NORM`) | `MINIRAG_PACK_*` |
| Tiền tố tên nhánh thí nghiệm | `S-*` (đang chạy: G-A, G-B, G-AB, G-B0) | `P-*` |
| Điểm xuất phát | [PHASE2_REGISTRATION.md](PHASE2_REGISTRATION.md): trọng số đặc hiệu `1/df` + chuẩn hoá theo thực thể, thiết kế giai thừa 2 × 3 | Viết đăng ký mới. Hướng gợi ý (chọn theo dữ liệu, không bắt buộc): chọn Sources phủ đủ các thực thể/từ khoá của câu hỏi thay vì lấy thuần theo điểm; chọn theo điểm trên mỗi token |
| Rủi ro riêng | Lặp lại lỗi hub; tăng ứng viên có thể dìm vàng ở A1 | Hiệu ứng biến mất khi `top_k` nhỏ (ở `k`=5, A1 không còn là nút thắt); dễ làm hại câu Null |

Hai tầng **nối tiếp**: Người 1 đưa thêm chunk đáp án vào ứng viên thì chúng lại tranh ngân sách ở bước của Người 2. Vì vậy
mỗi người đo độc lập với C0 trước, rồi mới đo kết hợp (mục Lịch).

## Luật chung — bắt buộc cho cả hai

1. **Không sửa bộ đo dùng chung:** `reproduce/graph_repair/run_offline.py`, `compare_phase2.py`, `diagnose.py`,
   `reproduce/path/eval_offline.py`, `reproduce/research/phased_qa.py`, mốc đóng băng `logs/c_ablation/graph/C*/`,
   cache từ khoá. Cần thêm tính năng ⇒ sửa trên `graph-repair` rồi cả hai cùng rebase.
2. **Mỗi người chỉ sửa hàm của mình**, mọi công tắc **mặc định tắt**. Tắt hết ⇒ C0 phải khớp `chunk_ids` 180/180.
3. **Đăng ký trước rồi mới chạy** (mẫu: `PHASE2_REGISTRATION.md`): giả thuyết, công tắc, dự đoán, luật chọn, đóng băng
   bằng sha256. Sửa đổi chỉ thêm ở cuối, ghi ngày và đã xem số nào.
4. **Dev 180 để CHỌN, 435 câu ngoài dev để KẾT LUẬN.** Mỗi người tối đa **4 biến thể** đã đăng ký trên dev. Không chỉnh
   gì sau khi đã chạy trên 435 câu.
5. **Đọc kết quả bằng McNemar**, ghép cặp từng câu; "tốt hơn" trên 435 câu = cả 3 lượt sinh cùng chiều và p < 0,05 mỗi
   lượt (CLAUDE.md §3). Truy hồi (Evidence Recall) không thay được accuracy, và không đo được câu Null.
6. **Không được gọi là phương pháp:** đổi `top_k`, ngân sách token, prompt, model, embedding; bỏ thưởng; sửa bug.
   Những thứ đó chỉ là sensitivity hoặc sửa baseline (CLAUDE.md §1b).
7. **Tài nguyên dùng chung — báo trước trong nhóm:** máy 16 GB chỉ chạy **một** lượt offline mỗi lúc (2 shard — 4 shard
   từng làm crash cả máy); GPU Modal và quota Gemini cần cả nhóm đồng ý; theo dõi log Modal, `modal app stop` ngay khi
   xong hoặc khi khởi động lỗi lặp.
8. **Không xoá index.** Không commit log thô (`diag.jsonl`, `shard_*`): giữ ở máy, chỉ commit file tổng hợp.

## Thiết lập worktree

```powershell
# một lần, từ thư mục chính (E:\Project\MiniRAG)
git worktree add .worktrees/seed-select graph/seed-select     # Người 1
git worktree add .worktrees/source-pack graph/source-pack     # Người 2
# trong worktree: tokenizer cache (không có trong git)
Copy-Item -Recurse E:\Project\MiniRAG\data-gym-cache .\data-gym-cache
```

Chạy một nhánh trên dev 180 (luôn trỏ index của thư mục chính — bản checkout trong worktree có graphml CRLF, sai
fingerprint):

```powershell
E:\Project\MiniRAG\.venv\Scripts\python.exe reproduce\graph_repair\run_offline.py --phase p_pack --name c0_reg --arm C0 `
    --index E:\Project\MiniRAG\LiHua-World-qwen-modal
E:\Project\MiniRAG\.venv\Scripts\python.exe reproduce\graph_repair\run_offline.py --phase p_pack --name p_x --arm C0 `
    --env MINIRAG_PACK_X=1 --index E:\Project\MiniRAG\LiHua-World-qwen-modal
```

Lượt đầu tiên trong worktree mới **luôn** là `c0_reg` và phải khớp `logs/c_ablation/graph/C0/C0_records.jsonl` 180/180.
`--env` từ chối các khoá mà `eval_offline` tự đặt lại (`MINIRAG_CHUNK_CUT`, `MINIRAG_TRUNCATE_SOURCES`, …). Mỗi lượt
ghi `run_env.json` cạnh kết quả. Đầu ra nằm trong `logs/graph_repair/<phase>/<name>/`; so với C0 bằng
`compare_phase2.py` (Người 2 sao chép thành bản của mình, đổi danh sách nhánh — không sửa bản gốc).

Worktree không có `.venv` riêng: dùng Python của thư mục chính như trên. `eval_offline.py` tự chèn gốc worktree vào
`sys.path`, nên code `minirag` được nạp là của worktree, không phải của thư mục chính.

## Lịch

| Bước | Người 1 | Người 2 | Chi phí |
|---|---|---|---|
| 1. Dev 180 | G-A / G-B / G-AB / G-B0 (đang chạy) → chọn theo luật đã đăng ký | Đăng ký `P-*` (≤ 4 biến thể) → chạy → chọn | CPU |
| 2. 435 câu ngoài dev, chỉ truy hồi | nhánh `S-` được chọn + các ô ablation 2 × 3 vs L-C0R | nhánh `P-` được chọn + ablation của mình vs L-C0R | CPU, ~25 phút / nhánh / lượt sinh |
| 3. Điểm hợp | — giai thừa 2 × 2 trong **cùng một đợt**: C0, S-best, P-best, S+P — | | CPU |
| 4. Accuracy | — **một** đợt GPU: nhánh thắng (hoặc S+P) vs L-C0R, 3 lượt sinh, chấm 3 lượt — | | ~1,5 USD / cặp nhánh, cần đồng ý |

Bước 2 dùng `reproduce/research/phased_qa.py contexts` theo giao thức `LIHUA_FLOW.md` (nhánh `research/lihua-flow`):
cùng `runs/lihua_world/flow_v1/kw_s{101,202,303}.jsonl`, `PYTHONHASHSEED=13`, đối chứng L-C0R đã dựng sẵn và đã kiểm
khớp từng byte. Mỗi người thêm cấu hình của mình vào `phased_qa.py` trên nhánh của mình (`FUSION`, `EXTRA_ENV`,
`registration_for`).

## Hợp nhánh

Nhánh chỉ merge về `graph-repair` khi: công tắc mặc định tắt, `c0_reg` khớp 180/180, test qua
(`tests/test_flow_spec_norm.py`, `test_path_score_flow.py`, `test_c_ablation.py`), có đăng ký và kết quả 435 câu (kể cả
kết quả phủ định). `graph-repair` chỉ về `main` sau bước 4.
