# C4 = B2_NO_VECTOR, dev401 seed101

Theo HANDOFF_2WIKI_QWEN.md §1.5 và §2W-10, ablation sau bỏ BM25 là bỏ vector,
so với B2_FULL/C1. Đăng ký DEV401-CTX-C4-001 trong EXPERIMENT_HISTORY.md.

- C4 mới: `mode=mini`, `MINIRAG_CHUNK_FUSION=bm25`. Sources lấy nguyên thứ tự
  BM25 top30, qua cùng Sources cap4000. Không đổi k1/b/tokenizer/stopwords.
- Giữ parser, đường truy hồi đồ thị và bảng Entities; graph không có node/cạnh
  vẫn early exit. Vector query trong đường chung vẫn được tính, nhưng không dùng
  xếp Sources. Không gọi đây là cấu hình không đồ thị hoặc bằng chứng tiết kiệm CPU.
- C3 vẫn naive, C0/C1/C2 và C_orig giữ mapping cũ. C4 chạy qua phased_qa thông
  thường, chưa tích hợp vào paired-context acceleration C0/C1.
- Mở rộng nhánh core làm source hash thay đổi: dùng output mới và
  source_amendment.json; không sửa manifest hay resume lại run cũ với source mới.
  Các script cũ đòi hash chính xác có thể từ chối chạy lại, đúng với guard bảo vệ
  provenance. Không xóa manifest để vượt guard. Judge source/rubric không đổi.

## Kiểm thử và giới hạn

`python -m pytest tests/research/test_phased_qa.py tests/research/test_2wiki_acceleration.py -q -p no:cacheprovider`

26 passed, dùng index fixture cùng LLM/embedding giả, không gọi API. Kiểm C4
phased prompt/answer khớp đường MiniRAG, thứ tự BM25 vẫn đúng khi vector đảo thứ
tự, giữ early exit; có C0/C1/C2/C3/C_orig và paired C0/C1 hồi quy. Chưa thay thế
việc so401 Entities/graph/vector lists với context C1 thật sau lần chạy này.

## Lệnh tiếp theo: CPU contexts

Tại gốc repo:

```powershell
.\.venv\Scripts\python.exe reproduce/research/run_c4_dev_contexts.py --execute
```

Entry point nạp keyword cache C1 đã có, kiểm401 ID, so manifest ngoại trừ source
amendment, bật HF/Transformers offline, chạy một CPU worker và cấm LLM. Output
`runs/2wiki/modal/c4-dev-s101-c4/C4_s101/`. Nếu bị ngắt, chạy lại đúng lệnh;
checkpoint context đã lưu được giữ, code/inputs thay đổi bị từ chối. Không gọi
keyword/answer/judge hay dùng test1599. Lệnh có thể ít in tiến độ; chờ
`contexts: {'ok': 401}` rồi kiểm dữ liệu trước khi đăng ký GPU answer.
