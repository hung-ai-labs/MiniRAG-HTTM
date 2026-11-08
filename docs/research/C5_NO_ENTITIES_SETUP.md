# C5 = B2_NO_ENT, dev401 seed101

Theo HANDOFF_2WIKI_QWEN.md §S-07 và §2W-10, bỏ dữ liệu trong bảng Entities,
giữ khung bảng và header CSV; **Sources phải giống C1/B2_FULL từng byte**.
Đây không phải ablation −Redge hoặc HYBRID_NO_GRAPH.

## Thực hiện

- C5=mini/vector_bm25 + MINIRAG_DROP_ENTITIES=1. Cờ mặc định tắt; runner xóa cờ
  khi chuyển sang cấu hình cũ. Core giữ early exits và đường retrieval phía trước.
- Entry point derive từ401 context C1 đã đo, không chạy lại parser, embedding,
  đồ thị, vector/BM25 hoặc model. Thay phần Entities bằng CSV header rỗng đúng
  định dạng core; lưu hash Sources C1/C5 cho từng query và kiểm byte-identical.
- Đây là thay đổi dữ liệu context đưa vào cùng prompt, không sửa system prompt,
  top-k, token cap Sources, Qwen/seed/index/embedding hoặc rubric.
- Source extension được ghi riêng; không sửa manifest, context, answer hoặc
  kết quả C0/C1/C2/C4. Không resume lại các run cũ bằng source mới.
- Dữ liệu timing retrieval bản derive để null; không diễn giải copy context là
  cải tiến tốc độ truy hồi. Chưa có QA/judge C5 hoặc dữ liệu test1599.

## Kiểm thử

- 28 tests phased/acceleration đạt sau thêm C5, fake LLM và embedding, không API.
- Kiểm bổ sung hai test C5 đạt sau thêm đối chiếu derive: context derive khớp
  đường MiniRAG C5 từng byte; Sources C1/C5 giống nhau; không có entity rows;
  chuyển C5→C1 phục hồi context gốc. Fixture không thay review độc lập S-07.

## Lệnh chạy tiếp

```powershell
.\.venv\Scripts\python.exe reproduce/research/run_c5_dev_contexts.py --execute
```

Chạy tại gốc repo. Output mới `runs/2wiki/modal/c5-dev-s101-c4/C5_s101/`:
contexts.jsonl, context.jsonl, sources_identity.jsonl và sources_identity_summary.json.
Mỗi trace ghi nguồn derive và hash context tham chiếu; timing mới null.

Lệnh hoàn tất phải báo `contexts: {'ok': 401}; Sources byte-identical to C1: 401/401`.
Sau đó kiểm dữ liệu trước khi đăng ký/sinh401 answer C5 và Gemini chấm ba lượt,
so với C1. Không truyền --execute cho bước GPU nào trong entry point này.
