# C3 relation-lift QA: đăng ký trước khi gọi API

2026-11-09. Chạy dev 200; C0/C1/C3 theo `20261109-p0-relation-lift`.
Không chạy lại retrieval/evidence. Tái dùng đúng context đã kiểm chứng của
`logs/p0_paths/20261109_dev200`, kiểm tra toàn bộ hash của proof/manifest,
index, parser và dữ liệu trước/sau. Chỉ chạy generation và judge.

Cùng Gemini free-tier `gemini-flash-lite-latest`, public endpoint, limiter
13 RPM / 3000 TPM mặc định không chỉnh; không gọi Modal hoặc API trả phí.
Đây là Qwen graph/parser + Gemini generation, không phải benchmark SLM cuối.
Một lượt sinh mới, provider default sampling, max_tokens=1024, cùng prompt
RAG hiện có, response_type mặc định. Không tái dùng đáp án các study cũ.
Chỉ chia sẻ prediction khi cùng question/context/round; judge verdict khi
cùng question/prediction/pass. API lỗi không được tính thành error/neither.

Ba lượt judge độc lập, prompt và nhãn accurate/error/neither từ Step_2_evaluate,
max_tokens=16. Thứ tự question cố định xáo seed 1308; xoay thứ tự arm;
judge không thấy tên arm. Interleave generation và judge lượt đầu theo từng
question, sau đó chạy pass 2/3 theo thứ tự xáo riêng. Checkpoint từng output.

So sánh chính: C3 vs C0, C3 vs C1; McNemar chính xác trên nhãn majority của
ba judge (tie=neither), chỉnh Holm hai phép so. Báo acc/err/neither mean ±
sd judge, thêm Single/Multi/Null; báo riêng từng pass. Nếu thiếu thì chỉ báo
cohort chung đủ ba arm của mỗi pass, ghi partial và không gọi là kết quả
200 câu. Không chọn mẫu/dừng theo kết quả; quota ngày cạn thì dừng và resume.

Giữ algorithm/profile/context cố định; không chỉnh hệ số sau khi xem QA.
Một lượt sinh không đủ chứng minh cải tiến cấu hình; nếu có tín hiệu cần
lặp sinh và xác nhận held-out SLM trước khi kết luận cho paper.
