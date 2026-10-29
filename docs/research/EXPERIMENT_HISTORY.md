# Lịch sử chuẩn bị và thí nghiệm

## PREP-001 — Môi trường và dữ liệu

- Nhánh `research/2wiki-qwen`, nền `9c59062a9cfaaab47b4e8b303829ce0d00624e91`.
- Python 3.13.5; import/embedding 384 chiều đã kiểm; package list và editable metadata trong env/.
- Archive khớp checksum; dev 12.576 câu có nhãn; test answer rỗng; aliases là JSONL.
- Ignore dữ liệu sinh/index/run/venv; S-02 chờ người còn lại review và quyết định backup index.

## PREP-002 — Chuẩn hóa và phát hiện dữ liệu nguồn

- Hoàn tất chuẩn hóa offline sau ghi chú review schema tại `PROTOCOL_2WIKI_REVIEW.md`.
- 54.957 đoạn ứng viên, 12.576 câu; chưa chọn corpus.
- Sửa kiểm tra title quá chặt: 523 lượt title lặp trong 463 câu đều cùng nội dung, không phải xung đột.
- Phát hiện 70 sentence index ngoài đoạn ở 70 câu; giữ nhãn gốc, fact null và mapping_status rõ ràng; không sửa đáp án hoặc loại câu.
- Chuẩn hóa version 2; mọi checksum trong processed/manifest.json, kiểm `--check` thành công.

## PREP-003 — Đo pool và split ứng viên

- Seed 13, sort _id rồi shuffle; dùng cả gold và distractor.
- N=200/500/1.000/2.000: chunk 1.535/3.446/6.388/11.661; nominal call index 3.070/6.892/12.776/23.322.
- Split gold-title connected components, ứng viên test 20%; cân bằng loại câu không dùng answer/judge.
- Kết quả 160/40, 400/100, 800/200, 1.599/401; không title gold chung. Mọi số là ứng viên, chưa khóa N hoặc split.

## PREP-004 — Audit gần trùng và kiểm chứng (26/10/2026)

- Cố định ngưỡng Jaccard char 5-gram >= 0,85 trước chạy audit; normalization NFKC + casefold + bỏ dấu câu/gộp khoảng trắng.
- So câu hỏi và thân đoạn gold bỏ title; join chính xác, prefix filter kiểm bằng exhaustive fixture.
- Cả bốn pool có 0 cặp vượt ngưỡng; không thay đổi nhóm/split ứng viên. Chưa kiểm paraphrase ngữ nghĩa và gần trùng mọi distractor.
- Báo cáo `env/2wiki_near_duplicate_audit_seed13.json`, chỉ thống kê và hash, không test text/IDs.
- 7 test offline đạt; toàn bộ năm file chuẩn hóa tính lại khớp byte. Chưa gọi LLM hoặc benchmark.
- Báo cáo review: `PREPARATION_REVIEW_2WIKI.md`. Chưa commit/push hoặc gửi báo cáo cho người khác.

## PREP-005 — Metrics judge và so sánh ghép cặp (26/10/2026)

- Đọc contract per_question.csv từ judge_run.py ở commit protocol tham chiếu; không thay rubric hay gọi judge.
- Triển khai metrics.py với summarize/compare; đếm ba nhãn, parse_failed/judge_failed/missing, majority/no_majority, bảng theo loại câu, mean/sd giữa lượt judge; xuất mỗi query × lượt sinh × lượt chấm.
- McNemar exact đếm lên/xuống theo query_id; bootstrap resample query, giữ các lượt sinh trong query. Tách sd giữa lượt sinh và giữa lượt judge.
- Từ chối query trùng/lạ, sai type/majority, checksum bị sửa và so khác index/split/rubric/judge nếu manifest có đủ. Khi không có provenance đầy đủ, đánh dấu false, không tự chứng nhận run.
- 17 test metrics dữ liệu giả đạt; chạy chung tests/research: 24 passed. Không dùng answer thật hoặc API, không tạo kết quả benchmark.
- Efficiency/Evidence Recall và early-exit/generation failures chưa có nguồn log phù hợp: báo null, cần tích hợp trước đánh dấu S-06 hoàn tất.

## PREP-006 — Chuyển sang local theo yêu cầu người dùng (26/10/2026)

- Phát hiện Ollama 0.40.10 và Qwen2.5:3b Q4_K_M đã có; không tải/cài lại. Chạy server loopback cloud disabled, parallel 1; không đổi .env hoặc env toàn hệ thống.
- Smoke LOCAL_OK, context 32k và 100% GPU xác minh qua native /api/ps, 3.367.879.311 byte VRAM.
- Canary01 dừng trước index do dataclasses deepcopy SSLContext của bound method; giữ logs/index rỗng. Sửa wrapper bằng closure, không sửa core.
- Canary02 index hai doc giả, tạo hai chunk/3 node/2 cạnh; sáu request extract/glean/parser/answer đều Qwen local, 1.189 token sinh, không lỗi/chạm trần. Answer chứa địa danh fixture Riverton.
- Lưu raw requests, context/generation, retrieval, cache keyword, events, runtime và checksum index. Đã unload model và xác nhận GPU 0 MiB. Server còn chạy nền.
- Thêm adapter/launcher/config/report và 9 test HTTP mock; tổng 33 passed. Chưa có benchmark/judge 2Wiki.
- Local Q4_K_M khác bf16/vLLM của MultiHop; mọi đối chứng 2Wiki sau này cần cùng digest/settings và index local. Không chứng nhận HF revision tương đương từ tên model.

## PREP-007 — Nhóm chọn pool 2.000 câu

- Người dùng gửi ảnh tin nhắn nhóm: nguồn có khoảng 12k câu, chạy 2k trước. Diễn giải chọn pool 2.000 câu hỏi, đã thông báo rõ trước khi chuẩn bị.
- Materialize theo đúng phép lấy mẫu đã đo (sort _id, shuffle seed 13), corpus ID `2wiki-n2000-s13-4267adcf3ef6`.
- 2.000 câu: compositional 796, comparison 480, bridge_comparison 481, inference 243. Hợp cả context gold và distractor: 11.657 đoạn, 11.661 chunk đo offline, nominal 23.322 call index.
- Tạo pilot_docs.jsonl gồm 200 đoạn lấy mẫu độc lập gold relevance bằng seed 13; chưa chạy index.
- Lưu docs/queries/gold/questions, corpus_manifest/pilot_manifest trong processed/pools/n2000_seed13/ được ignore. Public report chỉ counts/hashes, không full ID/test text.
- Split 80/20 vẫn là đề xuất, chưa khóa; không tự mở internal_test. Đề xuất 500 trước đó bị thay thế bởi lựa chọn mới.

## PILOT-001 — Lô đầu 10/200 đoạn thật, local Q4_K_M

- Người dùng đồng ý tiếp tục sau materialize pool2000. Chạy có giới hạn --max-new-docs10 để đo và kiểm checkpoint trước mở rộng.
- Runner mới không sửa minirag, bảo vệ đường dẫn/index cũ; identity/docs/model/source hashes, raw từng request, commit từng doc và checkpoint bất biến cuối lô. Nếu torn write thì từ chối sửa tại chỗ.
- 5 test mới đạt, tổng38 trước chạy model.
- Đã index 10 doc/10 chunk: 20/20 request Qwen local, 77 node/32 cạnh, 7/7 kiểm toàn vẹn đạt; --verify sau chạy vẫn đạt, không phát sinh request model.
- Sinh 12.921 token trong 182,161 giây request; tổng per-doc184,186 giây. Có 1 extraction cap4096 (5% request), 409 segment ## nhưng chỉ48 segment duy nhất và có COMPLETE. Đây là chẩn đoán rawtext, chưa thay stop/cap hoặc làm sạch đồ thị.
- Dự toán sơ bộ pilot200 khoảng61,4 phút tổng, full11657 khoảng59,6 giờ. Chưa chạy toàn corpus, chưa QA/judge, chưa nói chất lượng B2.
- Run/checkpoint/raw/index và báo cáo đã lưu, model được unload. Chi tiết LOCAL_PILOT_STAGE10.md.

## Chờ trước mở rộng pilot/benchmark 2Wiki

- Protocol/rubric/schema/logger/runner chung, S-08 và S-09; metrics judge chờ review, phần retrieval/efficiency và ablation chưa hoàn tất.
- Gemini Flash exact ID/project/quota; nhóm review điều kiện Qwen Q4_K_M local. Client Python 3.13.5; server native Ollama đã kiểm, không còn phụ thuộc Python server Modal.
- V-01/MR_FULL, V-02 cách paper dựng corpus vẫn chưa xác minh đủ.
- N=2.000 đã chọn; đã chạy lô kỹ thuật10 đoạn theo đồng ý tiếp tục của người dùng. Trước mở rộng cần review vòng lặp/cap và thời gian máy local; backup, split và cổng QA/benchmark chung vẫn còn mở.

## INFRA-001 — Review và thử tích hợp runner chung (29/10/2026)

- Nền 2Wiki `0d7a18c`, PR #1 head `77ae1af`; ghép không xung đột trên `research/2wiki-shared-gpu` riêng. PR vẫn Draft/chưa merge vào dev tại thời điểm kiểm tra.
- Python 3.13.5, toàn bộ 78 test research offline đạt. Giữ code chuẩn hóa/metrics/local adapter/config và index/checkpoint local.
- Chưa gọi Modal/Gemini hoặc chạy benchmark. Ba phát hiện cần xử lý trước live run: resume index phải so endpoint, khóa chống hai writer, lưu request thô và nối ID/attempt. Chi tiết `SHARED_GPU_INTEGRATION_REVIEW.md`.
