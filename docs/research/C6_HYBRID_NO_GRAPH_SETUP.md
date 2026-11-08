# C6 = HYBRID_NO_GRAPH — chuẩn bị 02/11/2026

Theo HANDOFF_2WIKI_QWEN.md §S-07/2W-10, cấu hình này được so với C1/B2_FULL.
Đăng ký DEV401-CTX-C6-001 trong EXPERIMENT_HISTORY.md. C5 vẫn incomplete ở
một query; chuẩn bị C6 độc lập không có nghĩa C5 đã hoàn tất.

## Cấu hình

- `C6`: mini + `MINIRAG_NO_GRAPH=1`, RRF(vector top30,BM25 top30), k60.
- Query gốc đi trực tiếp vào vector và BM25; nhánh chạy trước get_types và
  keyword parser. Không gọi phương thức graph/entity/relationship retrieval;
  graph rỗng không ngăn tạo context.
- Bảng Entities chỉ còn CSV header; cùng rag_response và Sources cap4000.
  Không sửa top-k, BM25 tokenizer/k1/b/stopwords, embedding hoặc prompt.
- Trace có vector_ids/bm25_ids/ranked_ids/chunk_ids, context hash, tokens,
  timing; graph_ids=[], graph_seeds/paths=0, no_graph=true, keyword_parser=false.
- Pha keyword explicit cho C6 skip không gọi inference; pha context không
  yêu cầu hoặc đọc keyword cache. Cờ NO_GRAPH được xóa khi về cấu hình cũ.
- Loader MiniRAG hiện vẫn khởi tạo storage chung/đọc snapshot. Không nhận là
  tối ưu startup/memory hoặc toàn bộ framework không load GraphML; hiệu ứng
  đang kiểm là bỏ các thao tác retrieval/parser của đồ thị.

## Kiểm thử

30 test phased/acceleration đạt với fake LLM/embedding. Kiểm bổ sung C6 gồm:
phased prompt/answer giống đường MiniRAG; poison các graph stores để báo lỗi
nếu bị gọi; context vẫn tạo, không gọi LLM/parser; full QA chỉ có một answer
call; log retrieval tồn tại; Sources/context giống C5 trong fixture khi đầu vào
vector/BM25 giống nhau; chuyển về C1 xóa NO_GRAPH. Test riêng pha keywords skip
được bổ sung và chạy cùng các test C6 trước bàn giao. Không gọi API/GPU.

Fixture không thay đối chiếu toàn401 context thật, review người khác hoặc xác
nhận thống kê; chưa công bố hiệu quả chất lượng/chi phí C6.

## Lệnh tiếp theo

```powershell
.\.venv\Scripts\python.exe reproduce/research/run_c6_dev_contexts.py --execute
```

Chỉ CPU/local embedding với HF/Transformers offline; LLM bị cấm ở context phase.
Output mới `runs/2wiki/modal/c6-dev-s101-c4/C6_s101/`. Source extension được ghi
amendment riêng, các điều kiện manifest khác phải giống C1; không sửa index hoặc
manifest/kết quả cũ. Không đọc test1599.

Chờ `contexts: {'ok': 401}` rồi kiểm vector/BM25/Sources so C1 và toàn context/
prompt so C5. Nếu giống hoàn toàn, ghi khả năng tái dùng generation để tránh
tốn GPU trùng; không tự coi là một lượt sinh độc lập hoặc sao chép nhãn C5
chưa hoàn tất. Pha này chưa sinh đáp án, chấm Gemini hoặc gọi Modal compute.
