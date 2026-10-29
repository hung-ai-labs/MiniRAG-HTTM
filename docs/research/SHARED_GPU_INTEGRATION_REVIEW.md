# Review tích hợp runner GPU vào 2Wiki

Ngày kiểm tra: 29/10/2026. Chỉ kiểm offline; không gọi Modal/Gemini.

## Nhánh và trạng thái

- Nền 2Wiki: `0d7a18cce17d8623e0aba901e1eea866fc70cd2c`.
- PR chung: [#1](https://github.com/hung-ai-labs/MiniRAG-HTTM/pull/1), head `77ae1afd4c5f36ae675718246a40c3db0849ebd1`.
- Tại thời điểm kiểm tra, PR còn Draft/open, chưa merge; `origin/dev` vẫn ở `9c59062`.
- Ghép trên nhánh riêng `research/2wiki-shared-gpu`, không có xung đột. Nhánh `research/2wiki-qwen` giữ nguyên.
- Không merge PR chung, không sửa `dev`/`main`, không gửi review/comment thay nhóm.

## Đã kiểm

- Python 3.13.5; toàn bộ `tests/research`: **78 passed** (38 test 2Wiki + 40 test runner chung), 33,03 giây trong lượt chạy hoàn tất.
- Test dùng LLM/embedding giả, mock HTTP; đặt `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` trong tiến trình test.
- Kiểm tương đương prompt/answer với MiniRAG, pha CPU không gọi LLM, limiter trả slot sau lỗi/hủy, checkpoint/resume và kế hoạch CLI 2Wiki.
- `git diff --cached --check` đạt.
- Không thay nội dung adapter local, chuẩn hóa dữ liệu, metrics, config local hoặc `baseline.yaml` so với `0d7a18c`.
- Không sửa/xóa index hoặc checkpoint local. Không sinh answer, chấm judge hay công bố metrics benchmark mới.

## Phát hiện cần xử lý trước khi chạy thật

Các điểm dưới đây được phát hiện bằng đọc code; bộ test đang có chưa bao phủ hết các trường hợp này. Chưa sửa code chung trong nhánh tích hợp, cần thống nhất với người giữ runner.

1. **Resume index không so endpoint.** `index_run.py` ghi `endpoint_sha256` vào manifest nhưng `IDENTITY_KEYS` chỉ gồm hash docs, hash tập doc, settings và source. `run_index()` chỉ so các khóa này trước resume. Vì vậy đổi endpoint nhưng giữ nguyên serving declaration có thể tiếp tục cùng index. Cần đối chiếu endpoint khi resume và thêm test từ chối endpoint khác.
2. **Index thiếu khóa chống ghi đồng thời.** `qa_run.py`/`phased_qa.py` có `run_lock`, còn `index_run.py` chưa giữ khóa trong quá trình kiểm identity, reconcile, insert và lưu checkpoint. Hai lượt `--resume` đồng thời có thể ghi cùng index. Cần khóa toàn bộ phiên ghi và test tiến trình thứ hai bị từ chối.
3. **Trace chưa đủ request thô để audit theo yêu cầu 2Wiki.** `llm_trace.py` lưu hash của messages, model/cap/seed và kết quả/usage nhưng không lưu chính messages. QA còn bỏ `response_text` ở sink; answer/keyword có lưu ở file khác, nhưng trace chưa nối đầy đủ từng HTTP attempt với query ID và request/context thô. Cần thống nhất schema lưu nội dung request cùng ID/phase/attempt, bảo đảm không ghi key/header/URL bí mật.

Đây là nhánh tích hợp để review, chưa xác nhận sẵn sàng cho benchmark hoặc chạy GPU trả phí.

## Giữ điều kiện thí nghiệm

- Index Q4_K_M/Ollama local và index Modal/bf16 là hai điều kiện khác nhau. Không resume index local bằng runner Modal.
- Bộ runner chung đã chạm `minirag/utils.py`; local pilot cũ pin hash toàn bộ source MiniRAG. Resume pilot cũ trên nhánh tích hợp có thể bị từ chối đúng theo guard. Tiếp tục pilot bằng checkout nguồn cũ; không sửa manifest để vượt guard.
- Chưa chốt split internal dev/test, exact Gemini Flash judge ID, aliases/rubric, serving deployment thực tế và các ablation còn thiếu.
- Giữ các thiếu hụt protocol trong `PROTOCOL_2WIKI_REVIEW.md`. Không coi file serving tham chiếu MHR là xác minh deployment 2Wiki.

## Bước tiếp theo

Người giữ runner xử lý các phát hiện trên PR chung; sau khi PR được review/merge vào `dev`, fetch và tích hợp bản chính thức, chạy lại bộ test khi code thay đổi. Khi protocol/serving đã chốt và người dùng cho phép chi phí, mới chạy smoke 2Wiki nhỏ trên index Modal mới trước pilot lớn. Hướng dẫn lệnh nằm ở `SHARED_GPU_RUNNERS_2WIKI.md`; các placeholder chưa phải cấu hình chạy thật.
