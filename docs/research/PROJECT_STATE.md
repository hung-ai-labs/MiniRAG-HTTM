# Trạng thái benchmark 2WikiMultiHopQA

Cập nhật 26/10/2026. Nhánh `research/2wiki-qwen`, commit nền `9c59062a9cfaaab47b4e8b303829ce0d00624e91`.
Handoff/kế hoạch gốc: `c45ac1f458e07c7d750404043048ae2dc0e2a2bc`; protocol tham chiếu MultiHop: `790e0171a9e4e7c542aabc41993f48a37bff41ca`.

## Đã kiểm chứng offline

- Python client 3.13.5; import và embedding local 384 chiều đã được người chạy kiểm.
- Archive 2Wiki đúng checksum, đã giải nén. Chỉ dùng dev chính thức có nhãn; test chính thức có answer rỗng.
- `prepare_2wiki.py`: 12.576 câu, 54.957 đoạn ứng viên; mọi output có checksum và tái tính byte bằng `--check` thành công.
- 463 câu có title lặp, 523 lượt lặp nội dung giống nhau; giữ câu hỏi, gộp tài liệu.
- 70 supporting fact có sentence index ngoài đoạn: giữ nhãn gốc và đánh dấu mapping thiếu, không đoán hoặc loại câu.
- Đã đo pool 200/500/1.000/2.000 với seed 13 và thiết kế split ứng viên theo thành phần title gold.
- Audit Jaccard char 5-gram >= 0,85 trên câu hỏi và thân đoạn gold: 0 cặp ở cả bốn pool. Chưa bao phủ paraphrase ngữ nghĩa hoặc gần trùng mọi distractor.
- `tests/research/test_2wiki_preparation.py`: 7 passed; kiểm dữ liệu đầy đủ, checksum, ID/gold separation và không xuất nội dung test trong audit.
- `metrics.py` đã triển khai cho CSV judge chung: chuyển sang từng query × lượt sinh × lượt chấm, kiểm majority, ba nhãn và lỗi, bảng loại câu, McNemar chính xác, bootstrap theo query giữ các lượt sinh. 17 test metrics và 7 test dữ liệu đạt (24 tổng); dữ liệu metrics hoàn toàn giả.
- `.gitignore` bao phủ runs, indexes, processed và .venv; bộ bốn file trạng thái có sẵn, chờ người còn lại review S-02.

## Local đã chạy theo yêu cầu mới

- Ollama native 0.40.10 + Qwen2.5-3B-Instruct GGUF Q4_K_M có sẵn; không tải model hoặc gọi cloud.
- Smoke context 32.768, 100% GPU RTX 4050, khoảng 3,37 GB VRAM; model digest được khóa.
- Canary hai tài liệu giả: 2 chunk, 3 node, 2 cạnh; 6 request local gồm 2 extract/2 glean/1 parser/1 answer, không lỗi hoặc chạm trần. Answer có đúng Riverton của fixture.
- Giữ artifact canary lỗi SSLContext và canary đã sửa; chỉ sửa wrapper, không sửa minirag core. Không coi canary là benchmark 2Wiki.
- Sau chạy model được unload, GPU 0 MiB; Ollama nền vẫn ở loopback. Cấu hình tại `configs/research/2wiki/local_qwen.json`.
- 9 kiểm thử adapter local đạt, tổng `tests/research` là 33 passed. Chi tiết `LOCAL_QWEN_STATUS.md`.

## Chưa khóa hoặc chạy

- Người dùng đã gửi tin nhắn nhóm chọn pool 2.000 câu từ dev chính thức. Đã materialize corpus `2wiki-n2000-s13-4267adcf3ef6`: 11.657 đoạn, 11.661 chunk đã đo, 23.322 call index tĩnh trước retry/cache.
- Danh sách pilot 200 đoạn được chọn bằng seed 13 từ corpus, không chọn theo gold relevance. Đã chạy lô đầu 10/200 đoạn thật: 20 request local thành công, 77 node/32 cạnh, 7 kiểm toàn vẹn đạt. Checkpoint bất biến docs-0010 đã lưu. Toàn bộ ID/gold nằm trong processed/pools/n2000_seed13/ được ignore; public report chỉ có counts/hashes.
- Split 80/20 vẫn là ứng viên (1.599 dev / 401 test), chưa khóa split hoặc xuất câu internal_test. Chưa index toàn corpus hoặc sinh/chấm answer benchmark 2Wiki. Đề xuất N=500 trước đó đã được thay bằng lựa chọn N=2.000 của nhóm.
- Lô10 có 1/20 output chạm cap4096 và nhiều segment lặp; raw đã lưu, chưa đổi cap/prompt/stop. Dự toán sơ bộ pilot200 khoảng 61 phút, toàn corpus khoảng 59,6 giờ local. Báo cáo `LOCAL_PILOT_STAGE10.md`; không coi mốc10 là pilot hoàn tất.
- Bộ offline hiện 38 passed (thêm 5 test runner checkpoint/path/verify/stats). Runner resume từ chối torn write, giữ index và snapshot; recovery sang thư mục mới chưa tự động hóa.
- Chưa triển khai đầy đủ fixture chung S-08, kiểm chéo S-09 và ba ablation B2. Metrics judge có sẵn; Evidence Recall, latency/tokens và số early-exit/infra của generation còn chờ schema logger, hiện ghi null chứ không suy đoán. Không coi 24 test offline là hoàn tất các cổng chung.
- Chưa tích hợp code chung từ nhánh MultiHop hoặc sửa mặc định MiniRAG.

## Cần nhận/chốt trước pilot

- PDF đúng phiên bản/hash và nguồn dựng corpus paper; hiện chỉ gọi thiết kế 2Wiki là chuyển đổi benchmark của nhóm.
- Protocol review hai phía, rubric nhận aliases, schema log đầy đủ và runner tham số hóa 2Wiki.
- Giữ Gemini Flash theo yêu cầu; exact model ID/project/quota chưa xác minh, chưa gọi API.
- Local Q4_K_M có digest/sampling/endpoint đã xác minh bằng smoke; khác điều kiện Modal bf16 và không có HF revision được chứng minh tương đương. Nhóm cần review điều kiện local cho mọi nhánh 2Wiki. Output index 4096, QA 1024 đã thử fixture, cần pilot 2Wiki thật.
- Client giữ Python 3.13.5; server local là Ollama native, không cần Python 3.12 hoặc vLLM trên Windows.
- N=2.000 đã chọn; còn tỷ lệ split, mức chênh loại câu chấp nhận, backup chung, ngân sách/tải máy và trần pilot.

## Giới hạn môi trường

- Không cài graspologic do tương thích Python 3.13; runner sử dụng phải được kiểm trên fixture.
- pip freeze lỗi mã hóa đường dẫn Git worktree; lưu pip list --format=freeze và metadata editable riêng trong env/.
- `baseline.yaml` và các index LiHua giữ nguyên.

## Nơi lưu và báo cáo

- `docs/research/PREPARATION_REVIEW_2WIKI.md`: kết quả tổng hợp, giới hạn và cổng pilot.
- `docs/research/env/`: bản ghi môi trường và ba báo cáo pool/split/gần trùng.
- `dataset/2WikiMultiHopQA/processed/`: năm file chuẩn hóa; gitignored, chưa backup chung.
- Chưa có run benchmark QA/metrics. Có technical runs và pilot stage10 dữ liệu thật trong `runs/2wiki/local/`, index pilot `indexes/2wiki-local-q4km-pilot200-n2000-s13/` và index fixture `indexes/2wiki-local-q4km-synthetic-canary02/`. Backup chung chưa được kiểm chứng; checkpoint local không thay backup ngoài máy.
