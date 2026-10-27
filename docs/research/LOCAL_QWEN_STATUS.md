# Qwen local — kiểm chứng 26/10/2026

Theo yêu cầu chạy local, đã sử dụng Ollama có sẵn, không cài thêm runtime hoặc tải model. Không gọi Gemini, Modal hoặc API trả phí.

## Điều kiện đã đo

- Python client 3.13.5; server Ollama native 0.40.10, không dùng Python 3.12 trên Modal.
- Model qwen2.5:3b, Qwen2.5-3B-Instruct, GGUF Q4_K_M; digest cố định trong `configs/research/2wiki/local_qwen.json`.
- RTX 4050 Laptop 6GB; smoke xác nhận model nằm hoàn toàn trên GPU, size_vram = size = 3.367.879.311 byte; context_length 32.768.
- Sampling gửi tường minh: temperature 0,7; top_p 0,8; top_k 20; repeat_penalty 1,05; seed 101. Output index 4096, keyword/answer 1024.
- Adapter chỉ nhận `http://127.0.0.1:11434`, tắt proxy/redirect và từ chối model/digest khác; không đọc API keys hoặc có fallback cloud.
- Server mới bind loopback, cloud disabled, parallel=1; không đổi biến môi trường toàn hệ thống hoặc `.env`.
- Embedding dùng đúng `minirag.llm.hf.hf_embed` hiện có, all-MiniLM-L6-v2 CPU 384d, weights từ cache offline. Kiểm embed trước đó bằng SentenceTransformer không thay implementation benchmark.

## Kết quả chạy thật

1. `runs/2wiki/local/runtime_smoke/20261026_01/`: sinh LOCAL_OK, context 32k/full GPU xác minh qua /api/ps. Smoke adapter phiên bản đầu; hash script lịch sử được giữ trong manifest.
2. `runs/2wiki/local/technical_canary/20261026_01/`: lần canary lỗi trước indexing do dataclasses.asdict deepcopy bound method chứa SSLContext. Giữ nguyên artifact; sửa bằng closure trong wrapper, không sửa minirag core.
3. `runs/2wiki/local/technical_canary/20261026_02/`: canary thành công, index hai tài liệu giả vào `indexes/2wiki-local-q4km-synthetic-canary02/`.

Canary thành công có 2 doc / 2 chunk / 3 node / 2 cạnh; 6 request = 2 extract + 2 glean + 1 kw_parse + 1 answer, tất cả Qwen local, không request lỗi và không response chạm trần. Sinh 1.189 token, tổng thời gian request 22,425 giây; index 22,320 giây. Đây là số đo trên fixture rất nhỏ, không dùng dự toán toàn 2Wiki.

Retrieval dùng B2 vector_bm25, GROUP_BASE flags A1/answer-type fix. Đầu ra có địa danh Riverton đúng fixture. Một kiểm contains không phải phán quyết benchmark hoặc judge. QA canary gọi aquery only_need_context, sau đó dùng nguyên rag_response template qua cùng adapter; chưa chứng minh tương đương hoàn toàn runner QA khi có hậu xử lý.

Mọi messages/kwargs/phase/chunk_id/query_id/raw response/latency được ghi sau mỗi request. Context đầy đủ và answer trong generation.json, retrieval rank log và keyword cache riêng, events và checksum file index trong manifest. Không xuất câu internal_test.

Sau canary, adapter unload model: /api/ps rỗng, nvidia-smi 0 MiB. Ollama server vẫn chạy nền ở loopback, idle không giữ model. Không xóa index hoặc artifact lỗi.

## Phạm vi khoa học và bước tiếp

Local Q4_K_M là điều kiện khác bf16/vLLM của MultiHop. Không ghép trực tiếp các con số; baseline/B2/ablation 2Wiki phải cùng model digest/options và index do chính model local dựng. Không khẳng định GGUF tương ứng chính xác HF revision tham chiếu chỉ từ tên model.

Judge vẫn Gemini Flash theo yêu cầu ban đầu; chạy Qwen local không chuyển judge sang Qwen. Chưa gọi judge.

Chưa index dữ liệu 2Wiki thật, chưa khóa N hoặc split. Cần hoàn tất protocol/rubric/logger/runner chung, backup và quyết định pool trước pilot chính thức. Canary hai tài liệu không thay thế pilot 200 đoạn hoặc benchmark.

## Chạy lại kỹ thuật (thư mục mới)

```bat
powershell -NoProfile -File reproduce\research\start_local_ollama.ps1
.venv\Scripts\python.exe -X utf8 reproduce\research\local_qwen.py --out runs\2wiki\local\runtime_smoke\new_run
.venv\Scripts\python.exe -X utf8 reproduce\research\local_canary.py --out runs\2wiki\local\technical_canary\new_run --index indexes\2wiki-local-q4km-synthetic-new_run
```

Không chạy lại vào thư mục có sẵn. Cấu hình JSON là snapshot điều kiện đã đo; adapter hiện dùng các constants tương ứng, chưa phải runner benchmark nhận mọi trường JSON động.
