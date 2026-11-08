# Review smoke20 judge — 01/11/2026

## Smoke V2 đã hoàn tất

Output mới `runs/2wiki/judge/baseline-smoke-s101-fl35-v2`, rubric
2wiki-upstream-aliases-v2. Đủ60 response modelgemini-3.5-flash-lite, finishstop,
không incomplete/no_majority. Có21 attemptRateLimitError trước khi retry đạt.

- Cả3 lượt đều8 accurate /3 error /9 neither: 40%/15%/45%.
- Bốn câu đổi majority so V1: Modern Mothers/The Slaughter Rule error→accurate;
  Grand Coulee Dam, Sharaf Al-Dawla và Dressmaker From Paris error→neither.
- Không sửa tay nhãnV1, không sinh lại Qwen, không đổi câu hỏi/corpus.
- Không gọi thay đổi40% so35% là cải thiệnRAG hoặc chứng minh judge chuẩn hơn:
  đây là thay rubric về prompt dự án, mẫu20 nhỏ, không có nhãn người độc lập.
  Một số background sai vẫn là giới hạn khác với độ đúng đáp án đích.
- Giữ V2 cố định cho các cấu hình/lượt sau. Bước tiếp sinh baseline401dev,
  chưa mở test1599 để tinh chỉnh. Cần biết project của key để quản lý quota429;
  không tự đổi RPM/TPM hoặc thêm key nhằm né quota cùngproject.

## Kết luận sau đối chiếu tài liệu dự án

Người dùng hỏi căn cứ tài liệu thay vì tự chọn tiêu chí. Đối chiếu kế hoạch
EXECUTION_PLAN_QWEN_NEW_DATASETS.md §B4: phải giữ định nghĩa từ Step_2_evaluate.py,
thêm aliases và tăng version/chấm lại khi đổi rubric. PROTOCOL_MHR_REVIEW.md
(bản đề xuất tham chiếu) còn yêu cầu prompt gốc nguyên văn. Protocol2Wiki yêu
cầu aliases nhưng không đưa tiêu chí chấm toàn bộ dữ kiện nền.

Runner2Wiki trước đó do Codex thêm câu "Judge the whole answer, including
contradictions" không có trong prompt gốc. Đã sửa sai lệch triển khai bằng cách
đọc nguyên văn JUDGE_PROMPT qua AST và chỉ append accepted_aliases; version
`2wiki-upstream-aliases-v2`, manifest schema2. Không thêm quy tắc ưu tiên mới
cho mọi câu có background sai hoặc tự gán nhãn chắc chắn cho ca mơ hồ.

Mọi artifact V1 giữ nguyên. Cần chấm lại cùng20 đáp án vào thư mục mới
`runs/2wiki/judge/baseline-smoke-s101-fl35-v2`, không sinh lại Qwen hoặc sửa
CSV nhãn cũ. Chưa gọi inference V2 trong bước sửa code. Những đề xuất chọn
rubric ở cuối báo cáo là lịch sử review trước khi đối chiếu tài liệu, không còn
là yêu cầu người dùng phải tự chốt tiêu chí.

Nguồn: `runs/2wiki/judge/baseline-smoke-s101-fl35/`. Chỉ đọc artifact local;
không chấm thêm hoặc sửa nhãn gốc trong bước review.

## Vận hành

- 20 query ID khớp questions/gold/answers; đủ60 phán quyết thành công.
- 60 response đều gemini-3.5-flash-lite, finishstop;19 attempt RateLimitError
  được retry trước khi hoàn tất. Không đổi RPM/TPM hoặc tự tăng quota.
- Majority: accurate7/20 (35%), error7/20 (35%), neither6/20 (30%).
- Mean ba lượt: acc35,00±0,00; err33,33±2,89; neither31,67±2,89 (%).
- Có1 câu khác nhãn giữa các lượt (error/error/neither), không no_majority.
- Đây là20 câu dev cho smoke, không phải benchmark đại diện toàn2000 hoặc
  test nội bộ. Đồng thuận ba lượt không chứng minh judge đúng.

## Điểm cần làm rõ trước khi chấm lô lớn

Nhận định bên dưới là review của Codex, chưa phải nhãn người độc lập và chưa
được dùng để thay đổi CSV/summary hoặc công bố judge accuracy.

1. Câu người phối ngẫu của đạo diễn The Dressmaker From Paris: gold Jean Harlow.
   System xác định đạo diễn Paul Bern rồi nói không có thông tin về spouse.
   Judge trả error/error/error. Câu không đề xuất tên spouse sai; theo tiêu chí
   từ chối trên thông tin đích, đây là ứng viên neither rõ ràng để kiểm rubric.
2. Câu ông nội Sharaf Al-Dawla: system nói không xác định được cha của 'Adud
   al-Dawla. Judge error/error/neither. Cần cùng quy tắc ưu tiên cho câu từ chối
   có kèm dữ kiện nền, thay vì suy ra người chấm nào chắc đúng chỉ theo đa số.
3. Câu Modern Mothers / The Slaughter Rule: gold no, system kết luận no nhưng
   có phần giải thích quốc tịch cần kiểm chứng. Judge error cả3. Rubric hiện
   chấm whole answer including contradictions nên không tự đổi thành accurate
   chỉ vì kết luận yes/no trùng gold. Phải chốt phạm vi chấm.

Không nên gọi ba trường hợp này là bug mapping: kiểm input join theo query_id
đã đạt; khác biệt nằm ở diễn giải tiêu chí judge hoặc nội dung background.

## Đề xuất quy tắc để người dùng xem trước

Giữ accurate/error/neither và aliases. Làm rõ: nếu system nói không biết hoặc
không đủ thông tin cho chính trường được hỏi, không đề xuất đáp án đích khác,
thì xếp neither; việc nêu đúng các thực thể nền không tự biến nó thành error.
Nếu vẫn đề xuất đáp án đích sai thì chấm error. Cần chốt cách xử lý dữ kiện nền
sai trong một câu trả lời từ chối để không âm thầm đổi đại lượng đo.

Nếu người dùng chọn làm rõ, lưu rubric version mới, dùng output directory mới,
chấm lại cùng20 answer, giữ nguyên raw V1. Áp cùng rubric đã chốt cho mọi
cấu hình/lượt sau đó. Nếu chọn giữ V1, lưu các ví dụ này vào limitations; không
sửa tay một vài nhãn cho kết quả đẹp hơn. Câu hỏi làm rõ đã gửi qua chat;
chưa gọi inference hoặc thay rubric trước câu trả lời.
