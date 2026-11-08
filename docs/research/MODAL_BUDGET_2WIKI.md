# Ngân sách Modal 2Wiki — 30/10/2026

## Credit tháng mới — đối chiếu 01/11/2026

Đã đọc CLI `modal billing summary --for 2026-10/2026-11 --json` sau ghi chú
chưa xác minh bên dưới: tháng10 metered18.36875559 USD, billed0; tháng11 hiện
metered0, billed0. Tổng usage được đối soát hiện khoảng18.37, còn khoảng6.63
trong trần gross25. Credit đã bù tiền thực trả tháng10; không tăng trần dự án.
Đăng ký DEV401-QA-C1-001: sinh401 answer từ context sẵn có, guard1800 giây,
rồi kiểm Billing lại. Chưa có hóa đơn cuối của đợt mới tại thời điểm ghi.

Người dùng báo giao diện lại hiển thị $30, chưa xác định đó là credit còn lại hay
Total usage của kỳ nào. Bảng giá chính thức https://modal.com/pricing xác nhận
Starter có $30 compute credit/tháng cho GPU/CPU/RAM. Không coi lời báo này là
bằng chứng bill đã dùng bằng 0 hoặc là cho phép tăng ngân sách thí nghiệm.
Giữ trần tổng $25 người dùng đã đặt; khoản usage cũ và khoản tiền thực trả sau
credit là hai đại lượng khác nhau. Cần đối soát kỳ Billing trước GPU tiếp theo.
Pha C1 context đã hoàn tất401/401 ở máy local, embedding offline và cấm gọi LLM; không
tiêu credit Modal. Các mốc phía dưới là snapshot lịch sử, không phải số dư live.

## Index hoàn tất — ảnh Total17,74 USD

Người dùng gửi manifest completed và ảnh Total17,74 (GPU16,80/CPU0,61/RAM0,33).
Còn7,26 trong trần25, có thể còn bill trễ/giữ ấm chưa phản ánh trong ảnh.
Không chạy index thêm. Chuyển smoke20 baselineC0 để đo QA trước lô dev401.
Chưa có số đo chi phí QA đủ để hứa mọi ablation/3 lượt sinh đều nằm trong số dư.
Chỉ dùng Gemini free tier, chưa chọn model ID hoặc gọi judge khi chưa có key.

## Đối soát16 USD, checkpoint10.496

Ảnh Total16,14 (Deployed apps16,13), còn8,86 so trần25. Local checkpoint/progress
đều10496, còn1161 tài liệu. Lượt cuối864/giờ => khoảng80,6 phút nữa nếu giữ tốc độ.
Theo interval Billing13,48→16,14 cho1760 đoạn, phần cuối khoảng1,75 USD,
tổng~17,89 trướcQA, còn~7,11. Không bảo đảm vì đoạn dài/graph/billing trễ.

Khoản8 USD choQA trước đây là dự phòng đề xuất, không phải hard cap của người
dùng. Cần ưu tiên index đầy đủ để có thể QA; đề xuất một lượt tối đa90 phút
với --max-runtime-seconds5400 --resume, không sửa source hoặc index cũ. Giữ
trần25; chưa khởi chạy GPU trong bước review. Sau index, đo smokeQA và chốt
khối lượng thực hiện trong số dư thực tế, không hứa tất cả ablation/lượt sinh
đều nằm trong ngân sách. Mốc16 đã được đối soát, không phải lệnh ngừng vĩnh viễn.

## Cập nhật checkpoint5.344, Total8,63 USD

Ảnh resource Total8,63 (Deployed apps8,62), còn16,37 so trần25. Nếu giữ8 USD
cho QA/dự phòng thì index còn8,37. Lượt vừa rồi tăng864 đoạn/60 phút, còn6313
đoạn (~7,31 giờ theo tốc độ lượt cuối). Dự toán sát phần dành cho index, không
tự chạy nhiều lượt hoặc cam kết trọn QA trong25. Giữ mốc16 để đối soát.

So hai ảnh tại checkpoint3136 và5344: tăng3,17 USD cho2208 đoạn; ngoại suy thô
6313 đoạn còn lại~9,06 USD, tổng~17,69 trướcQA. Không phải báo giá vì có bill
trễ, ngắt giữa chừng, startup/giữ ấm và độ dài đoạn khác nhau. Do đó khoản8 USD
QA là dự phòng mục tiêu, chưa được chứng minh sẽ giữ được. Theo dõi mỗi lượt.

## Cập nhật checkpoint3.136, Total5,46 USD

Ảnh mới resource Total5,46 (dòng Deployed apps5,45), tăng1,25 USD từ4,21 cho
960 đoạn thêm trong60 phút. Chi phí quan sát~1,30 USD/1000 đoạn, so~1,65 của
lượt30 phút trước; chưa phải benchmark cùng tải, có thể ảnh hưởng billing trễ.
Còn8.521 đoạn, ~8,88 giờ ở16 đoạn/phút. Nếu giữ nguyên mức tăng cuối thì index
còn~11,10 USD, tổng~16,56 trướcQA; cộng8 USD dự phòng thành~24,56. Margin nhỏ,
không bảo đảm nằm trong25 USD. Giữ mốc16 để đối soát trước khi chạy thêm.

Lượt vừa rồi không lỗi mạng, có16 request hủy do deadline và11 output length.
Vẫn ghi nhận giới hạn extraction, không đổi cap/prompt/source trong index chính.
Tiếp tục theo lượt60 phút khi Usage chưa chạm mốc; không tự động chạy nhiều lượt.

## Cập nhật checkpoint2.176, Total4,21 USD

Người dùng gửi ảnh mới31/10: resource Total4,21 USD, dòng Deployed apps4,20 USD.
Dùng4,21 để tính: còn20,79 USD trong25; giữ8 cho QA thì index còn12,79 USD.
Tăng0,79 USD so ảnh3,42 sau khi checkpoint tăng480. Lượt mới không lỗi mạng,
ba request bị hủy do hết giờ, ba output length. Thông lượng vẫn~480/30 phút.

Ngoại suy cùng mức tăng bill: còn9481/480×0,79≈15,60 USD, tổng~19,81 trướcQA.
Đây là phép tính điều kiện từ hai ảnh, không chứng minh đơn giá tăng hoặc mọi
0,79 USD đều thuộc đúng30 phút (có bill trễ/startup/giữ ấm). Không tiếp tục hứa
reserve8 chắc chắn đủ trong tổng25 nếu không cải thiện overhead hoặc đo QA.

Đề xuất lượt kế tiếp60 phút bằng --max-runtime-seconds3600, giữ --resume và
batch32/async16. Ít ngắt hơn có thể giảm lô phải làm lại và startup, không tăng
số model/container hoặc thay cơ chế retrieval. Chưa tự chạy lượt này. Tiếp tục
kiểm Billing sau lượt; tổng tiến gần16 USD thì đối soát trước khi chi thêm.
Không tự động hóa nhiều lượt không có kiểm tra bill vì runner chưa hard-cap USD.

Nguồn cơ chế tính phí startup/idle: https://modal.com/docs/guide/cold-start và
https://modal.com/pricing. Cấu hình local scaledown_window300 giây.

## Cập nhật 31/10, checkpoint1.696

Ảnh mới: Total3,42 USD (GPU3,24, CPU0,12, Memory0,06). Ngân sách còn21,58 USD;
giữ8 USD cho QA/dự phòng thì phần index còn13,58 USD. Chưa bảo đảm đủ toàn đợt
vì tốc độ, độ dài đoạn và bill có thể thay đổi. Giữ mốc dừng đối soát16 USD.
Lượt index mới tăng448 đoạn/30 phút, còn9.961 đoạn (~11,12 giờ nếu giữ tốc độ).
Lượt này có9 output length; chưa thay đổi điều kiện extraction để giữ index nhất quán.

## Billing mới nhất từ ảnh người dùng

Ảnh Usage breakdown sau checkpoint768 hiển thị **2,13 USD tổng**, trong đó
A10G2,03 USD, CPU0,07 USD và Memory0,04 USD (các dòng làm tròn riêng, dùng Total
của dashboard để tính ngân sách). Đây là số nhìn từ ảnh, chưa đọc API hoặc xác
minh độ trễ cập nhật billing.

- Tổng trần:25 USD. Còn22,87 USD so với ảnh hiện tại.
- Giữ8 USD cho QA/dự phòng, index còn khoảng14,87 USD.
- Chênh so mốc tự báo1,5 USD trước đó là0,63 USD, gồm các benchmark/giữ ấm và
  lượt index tiếp theo; không coi0,63 USD là giá chính xác riêng lượt30 phút.
- Có thể tiếp tục index cùng batch32/async16, cap4096 và timer1800 giây mỗi
  invocation. Checkpoint hiện tại768 đoạn, không deploy lại hoặc sửa source.
- Kiểm Usage sau khoảng1 giờ chạy thêm. Khi tổng Usage tiến đến16 USD thì
  dừng để đối soát; tránh tự dùng hết17 USD mới kiểm vì cần dự phòng bill trễ.
  Đây là ngưỡng vận hành để giữ tiền QA, không phải hard cap tự động của Modal.

Các số1,5 USD ở dưới là snapshot trước ảnh Billing mới, không phải số hiện tại.

Người dùng chốt tổng khoảng **25 USD**, báo đã dùng khoảng **1,5 USD** sau smoke,
pilot và đợt index đầu. Đây là số người dùng cung cấp, không phải billing đã đọc
từ API. Không suy ra 3 USD/giờ chỉ bằng 1,5 USD chia nửa giờ vì có các lượt trước.
Ngân sách còn lại sơ bộ **23,5 USD**, gồm cả index, QA và mọi chẩn đoán GPU.
Gemini vẫn dùng free tier và limiter hiện có; không bật API trả phí.

Giá công khai đối chiếu tại https://modal.com/pricing: A10 0,000306 USD/giây,
tương đương 1,1016 USD/giờ **chỉ GPU**; CPU, RAM và tài nguyên khác tính riêng.
Với ngoại suy 19,74 giờ index còn lại, GPU riêng khoảng 21,75 USD, cộng số đã
dùng là khoảng 23,25 USD trước CPU/RAM và QA. Đây chưa phải dự toán trọn gói.
Không resume toàn bộ theo tốc độ cũ chỉ vì số GPU riêng thấp hơn 25 USD.

## Chẩn đoán hiệu năng trong ngân sách

Một benchmark nhỏ tối đa 300 giây client trên **đúng 32 đoạn đầu đã checkpoint**,
batch32/async16, index `indexes/2wiki-throughput32-b32-c16`. Input phụ được lưu
ở `runs/2wiki/diagnostics/throughput32/`, không chứa câu hỏi hoặc gold mới.
Đây là test hạ tầng, không phải Proposed Method hay kết quả quality.
Checkpoint index chính 288 đoạn được giữ nguyên. Không gộp graph benchmark vào
index chính; chỉ dùng tốc độ/log để chọn cách thực thi tiếp.

Timer không phải hard monetary cap của provider: GPU có thể còn xử lý/hủy
request và giữ ấm sau khi client dừng. Không hứa trọn corpus hoặc QA nằm trong
25 USD khi chưa có thông lượng cải thiện và billing thực tế.

## Kết quả hai benchmark cùng 32 đoạn

| Lượt | Wall (giây) | Response OK | Length | Output token |
|---|---:|---:|---:|---:|
| Batch32/async16, có khởi động | 187,87 | 64/64 | 1 | 51.718 |
| Batch32/async16, GPU còn ấm | 111,54 | 64/64 | 2 | 47.878 |

Cả hai đạt 6 kiểm toàn vẹn. Lượt warm có 194 node/113 cạnh và 3 chunk không
được graph cite; khác graph lượt trước do sampling. Không lấy số node/cạnh để
kết luận chất lượng tăng. Hai output warm bị cắt vẫn là giới hạn extraction;
không thay cap/prompt trong index đang chạy để che vấn đề.

Thông lượng warm ~17,21 đoạn/phút, so tốc độ checkpoint lịch sử 9,6 đoạn/phút
trên đợt30 phút. Ngoại suy 11.369 đoạn còn lại ~11,01 giờ, riêng GPU ~12,13 USD.
Đây không phải benchmark cùng tải/độ dài/output được kiểm soát và không bảo đảm
full corpus giữ cùng tốc độ; graph lớn dần, cold start và độ dài tài liệu có ảnh
hưởng. Kết quả đủ chọn batch32/async16 làm ứng viên cho lượt30 phút tiếp theo.

Đề xuất giữ khoảng **8 USD cho QA và dự phòng**, không tiêu hết23,5 USD còn lại
cho index. CPU/RAM, chi phí chẩn đoán mới và phần giữ ấm chưa được đối soát bill.
Chạy thêm một lượt30 phút với --resume, batch32/async16; sau đó kiểm Billing và
số đoạn tăng thêm trước khi quyết định lượt dài hơn. Trần25 USD là tổng người
dùng cho phép, không phải số dư được API xác minh; chưa có cơ chế hard billing
cap của Modal trong runner.

Hai index chẩn đoán được giữ riêng. Index chính vẫn checkpoint288 đoạn, không
được ghi hoặc trộn graph trong suốt hai benchmark. Không đổi source index_run
hoặc manifest để resume; batch/async là tham số thực thi, được ghi riêng trong
events của mỗi invocation, không đổi corpus/model/cap đã đóng băng.

Lưu ý hạ tầng để kiểm chứng khi cần: script Modal chưa khai báo CPU request.
Modal mặc định request 0,125 CPU core, có thể burst, nên không tự kết luận đây
là bottleneck. Tài liệu chính thức về resources và vLLM cho thấy CPU thiếu có
thể làm giảm tốc; phải đo trước khi đổi deployment, không suy diễn thành finding.
https://modal.com/docs/guide/resources
https://docs.vllm.ai/en/stable/configuration/optimization/
