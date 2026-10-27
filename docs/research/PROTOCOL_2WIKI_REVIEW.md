\# Review protocol từ phía 2Wiki



Nguồn tham chiếu: nhánh research/mhr-qwen,

commit 790e0171a9e4e7c542aabc41993f48a37bff41ca.



\## Chấp nhận cho bước chuẩn hóa offline

\- Python 3.13.5.

\- Nguồn câu hỏi: dev chính thức có nhãn.

\- Đầu ra: docs.jsonl, queries.jsonl, gold.jsonl, questions.csv, manifest.json.

\- Đáp án, aliases và evidence chỉ nằm phía đánh giá.

\- Chưa chọn pool N, chưa chia internal\_dev/internal\_test.

\- docs.jsonl lúc này là kho đoạn ứng viên, chưa phải corpus được duyệt để index.



\## Cần chốt trước các bước liên quan

\- 2Wiki giữ Gemini Flash theo yêu cầu ban đầu; ID thực tế chưa xác minh.

\- Rubric cần hỗ trợ aliases và thống nhất hợp đồng nhãn.

\- Runner index/QA cần tham số hóa cho 2Wiki.

\- Trần output đề xuất: index 4096, QA 1024; kiểm lại bằng pilot 2Wiki.

\- Nơi backup và ngân sách chờ nhóm chốt.



Đây là ghi chú review kỹ thuật, không thay chữ ký phê duyệt của nhóm.
