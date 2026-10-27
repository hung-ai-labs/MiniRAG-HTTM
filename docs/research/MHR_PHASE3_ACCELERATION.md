# Chạy MultiHop RAG Phase 3 với truy hồi dùng chung

Bộ công cụ này giảm tính toán lặp giữa C0/C1 và cho Gemini chấm seed trước trong khi CPU chuẩn bị seed sau. Thiết kế nghiên cứu vẫn là 2.156 câu test, hai cấu hình, seed sinh 101/202/303 và ba lượt chấm: 12.936 đáp án, 38.808 phiếu hợp lệ. Đây là thay đổi thực thi, không phải một phương pháp retrieval mới.

Mã nằm trong `reproduce/research/mhr_phase3/`. Chạy các lệnh dưới đây từ thư mục gốc repo, bằng Python của môi trường MiniRAG đã cài phụ thuộc. Các entry point dùng đường dẫn theo checkout, không phụ thuộc tên người dùng, ổ đĩa hay workspace Codex. Các đầu ra mặc định ở `runs/multihop_rag/`, đã được Git bỏ qua.

## Đồng đội bắt đầu từ đâu

```sh
git fetch origin
git switch --track origin/codex/mhr-phase3-acceleration
python -m unittest discover -s tests/research -p test_mhr_phase3.py -v
python -m reproduce.research.mhr_phase3.pipeline
```

Lệnh cuối chỉ tạo plan offline. `status=preparing` là bình thường nếu checkout chưa có validation riêng. Nó không xuất test, khởi động GPU hay gọi Gemini.

Để kiểm tra context thật, cần các artifact từ lượt dev đã đóng băng:

- Index `multihop_rag-qwen-full609` cùng `index_manifest.json` và các file được manifest ghi checksum.
- `dev400.csv` trong bộ split của repo.
- Cache `kw_s101.jsonl` của lượt dev.
- Hai thư mục `C0_s101` và `C1_s101`, mỗi thư mục có `contexts.jsonl` và `context.jsonl`.
- Model embedding `sentence-transformers/all-MiniLM-L6-v2` đã có trong cache máy. Worker đặt chế độ Hugging Face offline, không tự tải model hoặc gọi LLM.

Chép index và artifact dev từ máy đã chạy nghiên cứu, giữ nguyên checksum. Các file lớn và thông tin xác thực không được đưa lên nhánh này. Cách chuẩn bị dataset được ghi ở `dataset/MultiHop-RAG/README.md`.

## Kiểm tra tối ưu trên dev

Nếu artifact nằm ở các vị trí mặc định trong repo:

```sh
python -m reproduce.research.mhr_phase3.validate
```

Nếu artifact được lưu riêng, truyền đường dẫn của máy đang chạy:

```sh
python -m reproduce.research.mhr_phase3.validate \
  --index /path/to/multihop_rag-qwen-full609 \
  --keywords /path/to/dev400/kw_s101.jsonl \
  --reference /path/to/dev400
```

PowerShell có thể viết cùng lệnh trên một dòng. `--reference` trỏ tới thư mục cha chứa `C0_s101` và `C1_s101`.

Để thử một mẫu nhỏ trước, dùng một thư mục checkpoint riêng:

```sh
python -m reproduce.research.mhr_phase3.validate --limit 6 \
  --out runs/multihop_rag/phase3_smoke \
  --status runs/multihop_rag/phase3_smoke/STATUS.json
```

Validation chỉ mở khóa thực thi khi đủ 400 query dev, 800 context, không có sai khác. Context, prompt, thứ tự Sources, Entities và trạng thái thoát sớm phải khớp bản cũ. Chỉ các trường thời gian được bỏ khỏi so sánh log. Mẫu nhỏ không thể mở khóa test.

Code, phiên bản Python/package, index, cache từ khóa và artifact tham chiếu đều được ghi hash. Thay đổi các đầu vào này làm validation cũ mất hiệu lực. Khi thay code hoặc đường dẫn artifact, dùng một thư mục validation mới thay vì sửa manifest cũ. Mỗi máy/checkout thực hiện validation của chính nó.

## Chạy Phase 3

Sau khi validation đầy đủ thành công:

```sh
python -m reproduce.research.mhr_phase3.pipeline
python -m reproduce.research.mhr_phase3.pipeline --execute-test
```

`--execute-test` xuất bộ test đã đóng băng và gọi Qwen qua endpoint Modal cùng Gemini từ cấu hình cục bộ. Lệnh này phát sinh công việc GPU/quota, nên chỉ chạy khi đã có ngân sách và cấu hình endpoint/key đúng. Không có lệnh thực thi nào được chạy chỉ vì checkout nhánh hoặc chạy unit test.

Producer chuẩn bị keywords, context chung rồi đáp án C0/C1 của từng seed. Một consumer Gemini lâu dài chấm C0 rồi C1 của cùng seed trong khi producer chuyển sang seed tiếp theo. Consumer dùng prompt, parser, ba lượt chấm và limiter của backend hiện hành; bộ công cụ không tự tăng RPM/TPM khi có thêm key. Key mới được đọc khi tiến trình chấm khởi động. Quota thực tế cần được xem theo project.

Các đầu ra cần theo dõi:

- `runs/multihop_rag/phase3_acceleration/DEV_CONTEXT_VALIDATION.json`: tiến độ và kết quả đối chiếu context.
- `runs/multihop_rag/phase3_acceleration/EXECUTION_PLAN.json`: thiết kế và hash code.
- `runs/multihop_rag/phase3_acceleration/PHASE3_STATUS.json`: trạng thái thực thi.
- `runs/multihop_rag/test_phase3/JUDGE_STATUS.json`: tiến độ consumer chấm.
- `runs/multihop_rag/test_phase3/qa/s<seed>/<config>_s<seed>/`: context, đáp án và journal judge cho từng cấu hình.

Chạy lại cùng lệnh sẽ dùng checkpoint; phiếu judge hợp lệ không được chấm lại. Nếu một consumer cũ còn sống, runner từ chối mở consumer trùng. Lỗi hash hoặc journal hỏng cần được kiểm tra trước khi chạy tiếp, không xóa checkpoint để vượt kiểm tra. Trạng thái `raw_runs_completed_analysis_pending` chỉ xác nhận các lượt chạy và phiếu đã đủ, chưa phải kết luận thống kê hay báo cáo nghiên cứu hoàn tất.

## Tính đúng và phạm vi bằng chứng

Adapter tách nguyên các câu lệnh AST của `_build_mini_query_context` ngay trước nhánh `fusion`. Prefix đồ thị được tính một lần cho một query/seed; hai suffix tạo Sources riêng. Keyword parser vẫn chạy cho mỗi cấu hình. Giá trị dùng chung được sao chép trước khi hoàn tất context; không giữ cache qua query/seed khác.

Bản triển khai workspace trước khi đóng gói đã khớp 800/800 context trên toàn dev400, mất 5.621 giây wall time. Tổng thời gian worker cũ/mới có tỷ số 2,766. Đây là so sánh lịch sử khác tải máy, không phải benchmark cùng tải có kiểm soát và không phải mức tăng tốc Gemini hay toàn Phase 3. Tóm tắt đã bỏ đường dẫn riêng và dữ liệu câu hỏi nằm ở `artifacts/mhr_phase3_acceleration_validation_summary.json`. Tóm tắt đó không mở khóa runner của checkout mới.

Giữ Gemini `gemini-flash-lite-latest` và rubric V1 theo yêu cầu tiếp tục thử nghiệm. Nhãn người độc lập chưa có; mức đồng ý Gemini/Codex không phải độ chính xác judge. Bí danh `latest` có thể thay model phía sau, nên phải ghi giới hạn này. Không đổi model/rubric âm thầm giữa lượt chạy.

Khi phân tích, giữ vai trò RQ2/RQ5 và quy tắc trong `MULTIHOP_RAG_ROADMAP.md`: McNemar ghép cặp theo từng seed, báo cặp lên/xuống và CI bootstrap; tách biến động giữa seed sinh khỏi nhiễu judge. Thời gian tính toán dùng chung được báo riêng, không coi phần suffix đã cache là độ trễ retrieval độc lập của C1. Không xem điểm test để chọn seed, tham số hoặc thời điểm dừng.

Runner đầy đủ này dành cho MultiHop-RAG. Đồng đội làm dataset khác có thể tham khảo cơ chế `SharedContext`/`run_pairs`, nhưng phải dùng split, số câu, cấu hình và giao thức riêng; không áp các hằng số 400/2.156/254 của MultiHop sang 2Wiki.
