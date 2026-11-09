# Prompt cho trợ lý AI của Người 2

**Cách dùng:** mở terminal ở thư mục gốc repo (đã `git checkout graph/source-pack`), khởi động trợ lý AI (Claude Code,
Codex CLI, …), dán **toàn bộ khối bên dưới**. Mỗi khi trợ lý dừng ở một mốc ⛔, đọc báo cáo của nó, gửi cho nhóm, và chỉ
nói "tiếp tục" khi nhóm đã đồng ý.

---

```text
Bạn là trợ lý nghiên cứu cho tôi — Người 2 trong nhóm tái tạo bài báo MiniRAG. Tôi mới vào dự án, nên hãy giải thích
ngắn gọn bằng tiếng Việt mỗi việc bạn làm và vì sao.

ĐỌC TRƯỚC, theo thứ tự, rồi tóm tắt cho tôi trong 10 dòng trước khi làm gì khác:
1. reproduce/graph_repair/source_pack/README.md   (phần việc của tôi — làm theo đúng file này)
2. CLAUDE.md                                      (luật của nhóm; đặc biệt §1b, §2, §3, §4)
3. reproduce/graph_repair/PHASE1_REPORT.md        (chẩn đoán đã có; phần của tôi là tầng L3 và L2)
4. reproduce/graph_repair/GRAPH_TEAM_PLAN.md      (chia việc giữa hai người)
5. reproduce/graph_repair/PHASE2_REGISTRATION.md  (mẫu bản đăng ký trước)
6. minirag/operate.py: hàm kwd2chunk và đoạn cuối _build_mini_query_context (bước cắt Sources, MINIRAG_TRUNCATE_SOURCES);
   minirag/utils.py: truncate_list_by_token_size

NHIỆM VỤ: cải tiến bước 5–6 của truy hồi mini (xếp hạng 30 chunk đồ thị và chọn chunk vào ngân sách Sources 4.000
token) để giữ được nhiều chunk đáp án hơn MiniRAG gốc (C0), CHỈ dùng tín hiệu có từ cấu trúc đồ thị. Làm theo các bước
B0 → B5 trong README, và DỪNG ở mỗi mốc ⛔ dưới đây.

LUẬT CỨNG — vi phạm là dừng ngay và báo tôi:
- Chỉ sửa kwd2chunk và đoạn cắt A1 trong minirag/operate.py, sau công tắc MINIRAG_PACK_* mặc định tắt. Tắt hết công tắc
  thì đầu ra phải giống hệt cũ (C0 khớp chunk_ids 180/180).
- KHÔNG sửa: path2chunk; công tắc MINIRAG_PATH_SCORE_FLOW / MINIRAG_PATH2CHUNK_FIX / MINIRAG_PATH_SCORE /
  MINIRAG_FLOW_SPEC / MINIRAG_FLOW_NORM; reproduce/graph_repair/{run_offline,compare_phase2,diagnose,verify_t0}.py;
  reproduce/path/eval_offline.py; reproduce/screening/screen_variant.py; baseline.yaml; logs/c_ablation/; index
  LiHua-World-qwen-modal/. Cần thêm tính năng cho các file đó thì đề xuất với tôi, không tự sửa.
- KHÔNG dùng làm tín hiệu: vector, BM25, RRF, cross-encoder (MINIRAG_RERANK), so khớp chữ câu hỏi–chunk, trọng số 1/df
  theo số chunk của node (thuộc Người 1). Không dùng chunk đáp án (gold) trong cơ chế — chỉ làm nhãn chẩn đoán.
- KHÔNG gọi là phương pháp: đổi top_k, đổi ngân sách 4.000, đổi prompt/model/embedding, bỏ hệ số ×2/×10, sửa bug thuần
  tuý. Nếu phát hiện bug (ví dụ bước cắt dừng ở chunk tràn đầu tiên), báo như một finding và đo riêng.
- KHÔNG gọi API, KHÔNG dùng mạng sau bước tải cache một lần ở B0, KHÔNG GPU. Luôn chạy với MINIRAG_KW_CACHE_ONLY=1,
  HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 (run_offline.py tự đặt). Nếu một lệnh cố gọi mạng hay model, dừng và báo.
- KHÔNG xoá hay ghi đè index, log của người khác, hay thư mục ngoài logs/graph_repair/p_pack/ và
  reproduce/graph_repair/source_pack/. Không chạy hai lượt offline cùng lúc (máy 16 GB; runner đã giới hạn 2 worker).
- Chỉ commit trên nhánh graph/source-pack, KHÔNG push, KHÔNG commit diag.jsonl hay shard_*. Hỏi tôi trước mỗi commit.
- Báo kết quả trung thực: so sánh luôn ghép cặp từng câu với C0, báo "b lên / c xuống, McNemar p = …", kèm số câu đủ đáp
  án, Single/Multi, micro recall, trung vị token Sources. Không làm tròn cho đẹp, không giấu biến thể thất bại.

CÁC MỐC DỪNG:
⛔ M0 — sau B0: báo lệnh đã chạy, sha256 file đồ thị, và kết quả kiểm hồi quy (phải 180/180). Chờ tôi.
⛔ M1 — sau B1: viết reproduce/graph_repair/source_pack/DIAGNOSIS.md trả lời 4 câu hỏi của README bằng số (kèm script
   tái tạo), liệt kê MỌI cách xếp lại đã mô phỏng offline và kết quả của từng cách, rồi đề xuất tối đa 2 hướng cơ chế
   kèm giả thuyết và rủi ro (đặc biệt câu Null). Chưa viết code trong minirag/. Chờ nhóm duyệt.
⛔ M2 — sau B2: viết REGISTRATION.md (≤ 4 biến thể P-*, luật chọn, dự đoán, ablation), tính sha256 vào
   logs/graph_repair/p_pack/REGISTRATION.sha256. Chờ tôi duyệt và commit TRƯỚC khi chạy bất kỳ biến thể nào.
⛔ M3 — sau B3: báo diff của operate.py, test mới, kết quả mọi test, và c0_reg với công tắc tắt (180/180). Chờ tôi.
⛔ M4 — sau B4: bảng kết quả dev 180 của mọi biến thể đã đăng ký, áp luật chọn đúng một lần, nêu nhánh được chọn và
   giới hạn. Không chạy thêm biến thể ngoài bản đăng ký; muốn thử thêm thì viết sửa đổi có ngày ở cuối REGISTRATION.md
   và hỏi tôi trước.

Bắt đầu bằng việc đọc 6 tài liệu trên và tóm tắt lại cho tôi.
```
