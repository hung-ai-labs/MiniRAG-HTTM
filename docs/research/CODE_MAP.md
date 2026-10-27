# Bản đồ code cho luồng 2Wiki

## Đã triển khai trong nhánh 2Wiki

- `reproduce/research/prepare_2wiki.py`: chuẩn hóa labeled dev; checksum nguồn, IDs, aliases, xử lý title lặp cùng nội dung; giữ và đánh dấu evidence index lỗi; không chọn corpus/split.
- `reproduce/research/measure_2wiki_pools.py`: pool nested seed 13; đếm token và gọi chính hàm chunking trích bằng AST để tránh import backend cài package tự động; số call chỉ là ước lượng tĩnh.
- `reproduce/research/analyze_2wiki_splits.py`: nhóm title gold, thử phân bố dev/test, chỉ xuất thống kê.
- `reproduce/research/audit_2wiki_duplicates.py`: Jaccard char5 chính xác, kiểm câu hỏi và thân đoạn gold; gộp nhóm để phân tích; không xuất nội dung test.
- `tests/research/test_2wiki_preparation.py`: 7 kiểm thử offline, gồm checksum toàn dữ liệu và gold separation; phần kiểm dữ liệu thật skip khi chưa có processed.
- `reproduce/research/metrics.py`: summarize CSV judge chung và compare các lượt sinh, xuất long per_question và metrics; kiểm tính lại, McNemar, paired bootstrap theo query; không import backend hoặc model.
- `tests/research/test_research_metrics.py`: 17 test dữ liệu giả: lỗi parse/API/missing, majority, IDs/types, exact binomial, bootstrap, checksum/tái tính, ba lượt sinh và khác judge.
- `docs/research/METRICS_2WIKI.md`: hợp đồng dữ liệu, cách tích hợp, mẫu lệnh, phần còn thiếu và kết quả kiểm thử.
- `reproduce/research/local_qwen.py`: client Ollama loopback-only, model digest pin, native options tường minh, log raw từng request và unload.
- `reproduce/research/local_canary.py`: index và QA hai tài liệu giả với Qwen local; CPU hf_embed từ cache, không dùng corpus thật.
- `reproduce/research/start_local_ollama.ps1`: khởi động server ẩn, loopback/cloud disabled/concurrency 1; tái dùng server đang chạy, không đổi env toàn hệ thống.
- `configs/research/2wiki/local_qwen.json`, `docs/research/LOCAL_QWEN_STATUS.md`: điều kiện Q4_K_M đã đo, kết quả smoke/canary và giới hạn.
- `tests/research/test_local_qwen.py`: 9 test mock HTTP, endpoint/model/digest, phase/caps/history/raw log và infra errors; tổng 33 test offline.
- `reproduce/research/materialize_2wiki_pool.py`: materialize pool đã đo và danh sách pilot; dùng toàn context gold+distractor, kiểm nguồn/pool identity, từ chối ghi đè, --check tái tính mọi byte; giữ IDs/gold trong processed và chỉ public counts/hashes.
- `docs/research/env/2wiki_selected_pool2000_seed13.json`: lựa chọn pool 2.000 theo tin nhắn nhóm, hashes corpus/pilot; split chưa khóa, index chưa chạy.
- `reproduce/research/local_index_pilot.py`: runner pilot cố định200 theo lô tối đa10 mặc định, log raw, commit sau persist, kiểm identity/store hashes khi resume, snapshot bất biến cuối stage, --verify không gọi model; từ chối torn write thay vì sửa index tại chỗ.
- `reproduce/research/summarize_local_index.py`: tổng hợp log stage thành counts, latency/token/truncation và dự toán có giới hạn, không xuất câu hỏi/test text.
- `tests/research/test_local_index_pilot.py`: 5 kiểm path guard, resume identity, torn stores, vector links và stats; tổng offline38.
- `docs/research/LOCAL_PILOT_STAGE10.md`: số đo thật 10/200 đoạn đầu, 7 kiểm đạt, checkpoint và phát hiện output lặp/cap.

## Code nền đang có

- `minirag/operate.py`: extraction, chunking và retrieval; chưa sửa.
- `minirag/bm25.py`: BM25 chunk, giữ tokenizer đã chốt.
- `reproduce/modal_slm.py`: template vLLM trên Modal, chưa deploy cho 2Wiki.
- `reproduce/Step_2_evaluate.py`: rubric cũ để tham khảo, chưa dùng chấm 2Wiki.

## Tham chiếu nhận từ nhánh MultiHop, chưa tích hợp

- `docs/research/PROTOCOL_MHR_REVIEW.md`: protocol tham chiếu ở commit `790e0171a9e4e7c542aabc41993f48a37bff41ca`.
- `docs/research/env/serving_qwen_mhr_reference.json`: model/vLLM/sampling và mức độ suy luận provenance.
- Nhánh đó có `llm_trace.py`, `index_run.py`, `qa_run.py`, `phased_qa.py`, `judge_run.py`; cần review/parameterize cho 2Wiki trước sử dụng.

## Chưa triển khai hoặc còn cổng chung

- Metrics Evidence Recall/efficiency/early-exit cần schema logger; rubric aliases và ba ablation B2 theo handoff. Phần metrics judge/so sánh ghép cặp đã có, chờ người còn lại review.
- Fixture index/retrieval/QA/judge/resume và kiểm chéo S-09. Test chuẩn bị dữ liệu không thay các kiểm này.
- Cấu hình run chính thức, corpus/split/index manifests và backup.

## Quy tắc tích hợp

- Thay đổi code chung cần người còn lại review; không sửa minirag mặc định khi chưa thống nhất protocol.
- `baseline.yaml` đóng băng; không ghi index LiHua hoặc thư mục luồng MultiHop.
- Mọi run model sau này cần config/index/split hashes, raw request/context/answer/judge và events; hiện chưa có run model.
