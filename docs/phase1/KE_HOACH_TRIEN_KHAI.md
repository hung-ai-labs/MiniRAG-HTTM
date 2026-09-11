# Kế hoạch triển khai — từ 10 nhược điểm sang code chạy được

Tài liệu để **anh đọc rồi quyết định làm hay không**, không phải lệnh thi hành.
Mỗi hạng mục có: sửa gì (kèm `file:line`), vì sao, đo thế nào, tốn bao nhiêu,
hỏng thì hỏng ở đâu, và khuyến nghị nên/không nên.

Nguồn: [`NHUOC_DIEM_VA_GIAI_PHAP.docx`](NHUOC_DIEM_VA_GIAI_PHAP.docx) ·
[`MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md`](MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md)
· Cập nhật 11/09/2026

---

## 0. Ba điều đã thay đổi kể từ khi viết docx

Đọc phần này trước, vì nó làm lệch thứ tự ưu tiên cũ.

**Nhược điểm 1 đã sửa và đã đo xong.** Kết quả không như kỳ vọng trong docx:

| | Δacc | McNemar | p |
|---|---:|---|---:|
| Gemini | +2,17 | 9 lên / 4 xuống | 0,267 |
| Qwen2.5-3B | +3,50 | 22 lên / 17 xuống | 0,522 |

Cùng chiều dương trên hai model độc lập, nhưng **không lượt nào đạt ý nghĩa thống kê**.
Docx dự đoán đây "nhiều khả năng là nguyên nhân chính khiến Multi-hop chỉ đạt 42,86%" —
dự đoán đó **sai**. Sửa xong Multi-hop của Gemini còn *giảm* (42,86 → 36,51), của Qwen
tăng (42,86 → 47,62). Hai chiều ngược nhau trên n = 21, nghĩa là nhiễu.

Bản thân con bug thì chắc chắn: 5 kiểu lấy từ chính `get_types()` khớp **0 node** khi
chưa vá, **49 node** khi đã vá. Cơ chế hỏng thật, chỉ là **sửa nó không cứu được điểm**.

> **Hệ quả cho kế hoạch:** đừng giả định nhược điểm nào cũng cho +5 điểm khi sửa. Mặc
> định phải là "có thể không đổi gì cả". Vì thế mỗi hạng mục dưới đây có thêm mục
> *Nếu không ăn thua thì sao* — vì đó là kết quả dễ xảy ra nhất.

**n = 200 quá nhỏ.** Hai lượt McNemar vừa rồi đều chết vì cỡ mẫu. Với tỷ lệ đổi ý
quan sát được, dev set 200 câu chỉ bắt được hiệu ứng từ khoảng **+7 điểm trở lên**.
Mọi thứ dưới mức đó sẽ ra p > 0,05 dù có thật. Xem mục 4.

**Đường găng không nằm ở đây.** Failure Taxonomy T4–T6 của Tài vẫn chưa bắt đầu, mà
bước 1 của công thức đóng góp là *Observed Problem có dữ liệu*. Kế hoạch này chạy
song song được, nhưng không thay thế được phần đó.

---

## 1. Ba quy tắc áp cho mọi thí nghiệm bên dưới

**Một biến mỗi lần.** Sáu hạng mục không cần index lại, rất cám dỗ gộp chung một
lượt cho tiết kiệm. Gộp là mất trắng: điểm có đổi cũng không biết do cái nào.

**Ngưỡng kết luận 3 điểm.** Sàn nhiễu judge đo trên chính baseline: sd 1,53, biên độ
dao động 3,00. Dưới 3 điểm mà chỉ chạy một lượt thì không nói được gì.

**Không ghi đè `./LiHua-World-gemini/`.** Mọi thí nghiệm cần index lại phải dùng thư
mục mới. Index baseline là mốc so sánh duy nhất, và đã từng mất một lần vì `rm -rf`.

Thêm một quy tắc mới rút từ lượt vừa rồi: **mọi công tắc phải bật/tắt bằng biến môi
trường**, theo đúng kiểu `MINIRAG_ANSWER_TYPE_FIX` (`networkx_impl.py:179`). Nhờ nó
mà đo được cả hai biến thể từ một checkout, không phải sửa file qua lại giữa hai lượt
rồi tự nghi ngờ mình đã sửa đúng chưa.

---

## 2. Cụm A — không cần index lại

Chạy ngay trên index có sẵn. Mỗi vòng: ~200 lời gọi sinh + 600 lời gọi chấm,
khoảng **1,5 giờ** trên Gemini free tier, **0 đồng**.

### A1 · Cắt token bảng Sources *(nhược điểm 2)*

**Vấn đề.** Bảng Entities bị cắt ở 500 token (`operate.py:1364`, gọi
`truncate_list_by_token_size`). Bảng Sources — phần văn bản gốc, chiếm phần lớn
context — **không đi qua bước cắt nào**. Tham số `max_token_for_text_unit` mặc định
4000 được khai báo nhưng **không dùng ở đâu trong mode `mini`**.

**Vì sao đáng làm.** Đây là bất đối xứng gần như chắc chắn ngoài ý muốn, chỉ ra được
bằng code chứ không phải suy đoán. RAGAS đo `context_precision 0,316` — hai phần ba
chunk nhét vào prompt là rác. Với SLM cửa sổ 8k thì p90 context đã 6.830 token, tức
đã chạm trần; lượt Qwen từng **tràn context ở tài liệu 91/442** chính vì chuyện này.

**Sửa gì.** Sau `operate.py:1390` (chỗ dựng `text_units_section_list`), áp
`truncate_list_by_token_size` lên danh sách chunk trước khi `list_of_list_to_csv`,
dùng chính `query_param.max_token_for_text_unit`. Bọc trong `MINIRAG_TRUNCATE_SOURCES`
để tắt/bật.

**Đo thế nào.** Quét 1000 / 2000 / 4000 token. **Đo RAGAS `context_precision` chứ
không chỉ đo accuracy** — đó mới là chỉ số phản ánh trực tiếp vấn đề. Kèm số token
context trung vị/p90 trước sau, và độ trễ truy vấn.

**Chi phí.** 3 cấu hình × 1,5 giờ + RAGAS ~100 câu. Khoảng nửa ngày, 0 đồng.

**Nếu không ăn thua thì sao.** Nhiều khả năng accuracy đứng yên. Vẫn đáng làm, vì
kết quả thật sự cần là **cùng accuracy với ít hơn một nửa token** — đó là phần
Efficiency, thứ bảng kết quả hiện chưa có dòng nào. Và nó là điều kiện cần để lượt
SLM cuối kỳ không tràn context.

**Ranh giới câu chữ.** *Bổ sung bước cắt token* là sửa khiếm khuyết thiết kế chỉ ra
được bằng code → viết vào báo cáo được. *Dò ra con số 2000 là tốt nhất* là tinh chỉnh
tham số → thuộc ô cấm, chỉ để ở phần phân tích.

**Khuyến nghị: NÊN LÀM.** Rẻ nhất, rủi ro thấp nhất, và bắt buộc phải có trước lượt SLM cuối.

---

### A2 · Cắt tỉa và chấm điểm lại đường đi *(nhược điểm 4)*

**Vấn đề.** Một truy vấn sinh **22.879 đường đi 2 hop** từ 138 thực thể khởi đầu.
Chỉ 971 đường (4,2%) nhận được phiếu cạnh. Số hop đóng cứng bằng 2
(`operate.py:1290`), không có bước cắt tỉa nào trước khi chấm. Riêng `LIHUA` sinh
2.001 đường, `ADAMSMITH` 760 đường.

Tệ hơn: `cal_path_score_list` (`utils.py:404`) chỉ **đếm** số node đúng kiểu trên
đường đi. Một đường đi qua ba node đúng kiểu nhưng lạc đề vẫn thắng đường đi qua một
node đúng chính xác. Không có trọng số nào theo điểm cosine hay theo bậc node.

**Vì sao đáng làm.** Đây là **ứng viên Proposed Method thuyết phục nhất hiện có**.
"Path re-weighting" nằm đúng trong danh sách cơ chế hợp lệ của nhóm, bằng chứng định
lượng đã có sẵn, và nó cho cả hai cột Quality lẫn Efficiency.

**Sửa gì.** Ba việc tách rời, đo riêng từng cái:

1. **Cắt tỉa trước khi chấm** — giới hạn số đường mỗi node khởi đầu, giữ node có
   cosine cao. Chạm `operate.py:1288–1291`.
2. **Chấm theo trọng số thay vì đếm** — `utils.py:404`, nhân điểm mỗi node đích với
   cosine của nó thay vì `count_elements_in_tuple` trả về số nguyên.
3. **Beam search theo hop** — mở rộng có chọn lọc từng hop thay vì bung hết 2 hop rồi
   mới lọc. Đây là thay đổi nặng nhất, làm sau cùng nếu (1) và (2) có tín hiệu.

**Đo thế nào.** acc/err/neither như thường lệ, **cộng thêm**: số đường đi sinh ra,
thời gian truy vấn trung vị, và tỷ lệ đường đi được dùng. Bảng kết quả phải có dòng
Efficiency, nếu không thì chưa đủ 5 bước của công thức đóng góp.

**Chi phí.** 3 biến thể × 1,5 giờ. Nhưng phần code nặng hơn hẳn A1 — ước lượng
1–2 ngày viết và kiểm.

**Nếu không ăn thua thì sao.** Vẫn còn nguyên giá trị: *"cắt 96% khối lượng tính toán,
accuracy không đổi, độ trễ giảm X%"* là một kết quả hoàn chỉnh, đúng khuôn Efficiency.
Đây là hạng mục **không thể thất bại hoàn toàn** — khác hẳn A1 và A3.

**Rủi ro.** Cắt tỉa quá tay sẽ giết đúng nhóm Multi-hop, nhóm cần đường dài nhất. Phải
đo riêng theo loại câu, đừng chỉ nhìn tổng.

**Khuyến nghị: NÊN LÀM, và đây là hạng mục quan trọng nhất tài liệu này.**

---

### A3 · Cơ chế từ chối khi thiếu bằng chứng *(nhược điểm 5)*

**Vấn đề.** Prompt có câu *"If you don't know the answer, just say so"* nhưng trong
code **không có bất kỳ ngưỡng tin cậy nào**. Nhóm Null err 31,67%, gần gấp đôi Single
(16,77%). Thêm 175 tài liệu nhiễu vào corpus thì accuracy giảm 8,34 điểm mà error
**tăng** 4,17 — hệ thống trả lời sai tự tin hơn, chứ không im lặng hơn.

**Vì sao đáng làm.** Với ứng dụng trợ lý cá nhân trên thiết bị — đúng bối cảnh MiniRAG
nhắm tới — bịa tự tin tệ hơn im lặng, vì người dùng không có cách nào biết.

**Sửa gì.** Trong `_build_mini_query_context`, trước khi gọi model sinh: nếu chunk tốt
nhất dưới ngưỡng cosine, trả `PROMPTS["fail_response"]` thay vì sinh. Thêm kiểm tra
nhất quán: nếu các chunk lấy về không cùng nói về một sự kiện, coi là thiếu bằng chứng.

**Đo thế nào.** Đây là hạng mục **bắt buộc đọc cả ba cột**. Mục tiêu là err nhóm Null
giảm, **chấp nhận acc không tăng** — điểm chuyển từ `error` sang `neither`, không phải
sang `accurate`.

**Chi phí.** 2 ngưỡng × 1,5 giờ.

**Vấn đề lớn nhất: n = 20.** Nhóm Null chỉ có 20 câu trong dev set. Một câu đổi ý là
±5 điểm. **Không thể kết luận gì trên 20 câu.** Bắt buộc chạy trên đủ 637 câu (Null
n = 64) thì mới có nghĩa. Xem mục 4.

**Nếu không ăn thua thì sao.** Rủi ro thật là nó ăn thua *quá đà*: ngưỡng đặt cao thì
hệ thống từ chối cả câu trả lời được, `neither` phình lên, acc tổng tụt. Nhớ rằng Qwen
đang có `neither` 12,50 — nó đã rất ít chịu im lặng; đẩy ngược lại quá tay thì mất
điểm ở Single.

**Khuyến nghị: NÊN LÀM, nhưng chỉ sau khi mở rộng lên 637 câu.** Làm trên 200 câu là
tốn quota để thu về một con số không diễn giải được.

---

### A4 · Trần cứng 5 thực thể *(nhược điểm 6)*

**Vấn đề.** `operate.py:1431` và `:1445` đều cắt `entities_from_query[:5]`, hằng số
trong code. Câu Multi-hop theo định nghĩa nhắc nhiều thực thể hơn.

**Làm bước kiểm tra rẻ trước khi quyết định.** Đếm xem trong 200 câu dev thực tế có
bao nhiêu câu bị chạm trần 5. Dữ liệu này **lấy được miễn phí từ log lượt đã chạy** —
không tốn thêm lời gọi nào.

- Nếu **dưới 10%** câu chạm trần → trần không phải nguyên nhân, **bỏ hạng mục này**,
  dồn sức sang A2.
- Nếu **trên 25%**, và tập trung ở nhóm Multi → đáng làm, đưa trần thành tham số.

**Khuyến nghị: LÀM BƯỚC ĐẾM TRƯỚC.** Tốn 15 phút, quyết định luôn được nên bỏ hay làm.
Đây là hạng mục duy nhất có thể loại bỏ bằng dữ liệu sẵn có.

---

### A5 · Quét ngưỡng và top_k *(nhược điểm 3)*

**Vấn đề.** `top_k = 60`, `cosine_better_than_threshold = 0,2`. Trace thật với "Li Hua":
`LI HUA 0,924 · LIHUA 0,653 · LALIGA 0,415 · CINQUE TERRE 0,344`. Từ node thứ ba đã
hoàn toàn lạc đề nhưng vẫn lọt vì trên 0,2.

**Vì sao vẫn làm dù nằm trong ô cấm.** "Đổi Top-K đơn thuần" là cải tiến giả — không
được gọi là Proposed Method. Nhưng nó là **bằng chứng cho Observed Problem** của A1 và
A2: cho thấy nhiễu vào từ đâu, và tại sao cắt tỉa là cần thiết.

**Khuyến nghị: LÀM Ở MỨC TỐI THIỂU.** Một lượt quét ngưỡng 0,2 / 0,4 / 0,5, lấy số
đưa vào phần phân tích. Đừng đầu tư hơn, và **tuyệt đối không đặt nó vào mục Proposed
Method** — hội đồng sẽ bắt đúng chỗ này.

---

## 3. Cụm B — phải index lại, gộp một lần *(nhược điểm 7 + 8 + 9)*

**Đây là quyết định lớn nhất trong tài liệu**, nên tách riêng.

**Vấn đề.** Đồ thị Gemini 770 node có:
- **27 nhóm trùng lặp / 57 node.** `LIHUA` bậc 300 và `LI HUA` bậc 20 là **hai node
  riêng biệt**. `ADAMSMITH` (49) vs `ADAM SMITH` (3). `CHAESONG-HWA` (88) vs
  `CHAE SONG-HWA` (2). Nhân vật chính bị chẻ đôi, đường multi-hop đứt ngay chỗ chẻ.
- **67 thành phần liên thông**, 59 node cô lập — nằm ngoài tầm với của
  `get_neighbors_within_k_hops` vĩnh viễn, không truy vấn nào chạm tới.
- **29 node rác** từ regex tham lam `re.search(r"\((.*)\)", record)` (`operate.py:297`).
- Mô tả thực thể phình: dài nhất **89.170 ký tự** ghép từ 748 mảnh, vì
  `_handle_entity_relation_summary` (`operate.py:57`) là **mã chết** — chỉ còn trong
  comment ở dòng 150 và 209.

**Vì sao đáng làm.** Hợp nhất thực thể là Designed Mechanism hợp lệ, mượn đúng một cơ
chế từ GraphRAG mà không thay kiến trúc. Và nó là nhược điểm **duy nhất có thể đo được
mà không cần judge**: số thành phần liên thông, số node cô lập, số nhóm trùng — đo
trực tiếp trên đồ thị, không dính sàn nhiễu 3 điểm.

**Sửa gì.** Khoá chuẩn hoá trước `get_node` (`operate.py:127`): hạ chữ thường, bỏ ký tự
không phải chữ/số. Regex đổi sang không tham lam. Chặn `entity_type` về đúng 4 loại
khai báo ở `prompt.py:5`. Bật lại hai lời gọi summary đang bị comment.

**Chi phí — đọc kỹ chỗ này.** Không phải một lượt index:

| Việc | Chi phí |
|---|---|
| Index lại Gemini (đồ thị 770 node) | ~1.006 lời gọi, ~1,5 giờ, 0 đồng |
| Index lại Qwen trên Modal (đồ thị 1.556 node) | ~50 phút, ~0,5 USD |
| QA + judge cho **cả hai** | ~3 giờ |
| Dung lượng | thêm ~30 MB, hai thư mục mới |

**Phải index lại cả hai**, vì bảng kết quả hiện có cả dòng Gemini lẫn dòng Qwen; chỉ
làm một bên thì mất tính so sánh. Tổng khoảng **một ngày làm việc**.

**Rủi ro cao hơn cụm A.**
- Gộp nhầm: `MR. SMITH` có thể là người khác thật. Docx đã đề xuất đúng — với trường
  hợp nhập nhằng thì giữ danh sách rà thủ công, **đừng gộp tự động**.
- Bật lại summary **có thể kéo recall xuống**: tóm tắt là mất thông tin. Phải đo cả
  hai chiều, và đây là lý do nên để nó thành công tắc riêng chứ không bật cứng.
- Đồ thị mới **không so sánh trực tiếp được** với 4 cấu hình đã đo. Nó mở một cột
  mới trong bảng, không sửa cột cũ.

**Nếu không ăn thua thì sao.** Chỉ số cấu trúc **chắc chắn sẽ đẹp lên** — gộp
`LIHUA`+`LI HUA` thì số thành phần liên thông giảm, đó là toán học chứ không phải may
rủi. Câu hỏi thật là accuracy có theo không. Kinh nghiệm từ A1: **đừng cược là có**.

**Khuyến nghị: LÀM, nhưng SAU cụm A, và chỉ khi còn thời gian.** Lý do xếp sau dù docx
để P1: nó tốn gấp năm lần cụm A, và Failure Taxonomy của Tài có thể chỉ ra chỗ khác
đáng sửa hơn. Nếu lịch gấp, cụm A + A2 là đủ để có một Proposed Method hoàn chỉnh.

---

## 4. Việc phải làm trước tất cả: mở rộng lên 637 câu

Đây là hạng mục **không có trong docx** nhưng theo tôi là quan trọng nhất, vì nếu
không làm thì mọi thí nghiệm trên đều cho ra p > 0,05 bất kể sửa đúng hay sai.

**Bằng chứng.** Hai lượt McNemar đã chạy: p = 0,267 và p = 0,522. Cả hai đều chết vì
cỡ mẫu, không phải vì hiệu ứng bằng 0. Với tỷ lệ đổi ý quan sát được, dev set 200 câu
chỉ đủ sức bắt hiệu ứng **từ khoảng +7 điểm trở lên**.

**Cỡ mẫu theo nhóm mới:**

| Nhóm | Dev 200 | Đủ 637 |
|---|---:|---:|
| Single | 159 | 507 |
| Multi | 21 | **67** |
| Null | 20 | **64** |

Multi và Null mới là chỗ có vấn đề, mà cả hai đang ở n ≈ 20 — biên độ ±5 điểm cho mỗi
câu đổi ý. Mọi kết luận về hai nhóm này hiện đều không đứng vững.

**Chi phí.** 637 câu: QA ~2,5 giờ, judge 1.911 lời gọi ~2,5 giờ. **Khoảng 5 giờ, chạy
qua đêm, 0 đồng.** Script đã resume được nên hết quota thì sáng chạy tiếp.

**Khuyến nghị: LÀM ĐẦU TIÊN.** Rẻ hơn mọi hạng mục khác, không cần viết dòng code nào,
và nó quyết định mọi thí nghiệm sau có diễn giải được hay không. Chạy cho baseline
Gemini trước, để có mốc 637 câu.

---

## 5. Cụm C — dọn lãng phí *(nhược điểm 10)*

`operate.py:373–381` gọi `entity_vdb.upsert` **hai lần cùng khoá**, chỉ khác một dấu
cách — nhân đôi chi phí nhúng vô ích. `entities_vdb` truyền vào
`_build_mini_query_context` nhưng **không dùng lần nào** (754 vector, 1,6 MB, nhúng hai
lần, chỉ phục vụ mode `light`). Cache LLM không bao giờ được ghi: `minirag.py:301`
truyền `hashing_kv` vào, `gemini.py:270` và `openai.py:109` đều `kwargs.pop` rồi bỏ —
file cache đúng **2 byte**.

Cả ba đều là hành vi **upstream**, không phải do nhóm sửa.

**Khuyến nghị: GHI VÀO BÁO CÁO, CHƯA SỬA.** Không ảnh hưởng chất lượng. Sửa cache thì
tiết kiệm quota các lượt sau, nhưng đó là tối ưu hạ tầng, không phải nghiên cứu. Đáng
một đoạn trong phần *quan sát về chất lượng cài đặt*.

---

## 6. Thứ tự đề xuất, và bảng quyết định

Khác thứ tự trong docx ở hai chỗ: mở rộng 637 câu chen lên đầu, và cụm B lùi xuống sau.

| # | Việc | Index lại | Công | Giá trị nếu thành | Giá trị nếu thất bại |
|---|---|---|---|---|---|
| 1 | **Mở rộng 637 câu** | Không | 5 giờ máy, 0 code | Mọi p-value sau đó có nghĩa | — (không thể thất bại) |
| 2 | **A4 đếm trần 5 thực thể** | Không | 15 phút | Biết nên làm A4 hay bỏ | — |
| 3 | **A1 cắt token Sources** | Không | Nửa ngày | context_precision + Efficiency | Vẫn có dòng Efficiency |
| 4 | **A2 cắt tỉa đường đi** | Không | 1–2 ngày | **Proposed Method chính** | Vẫn có Efficiency |
| 5 | **A5 quét ngưỡng** | Không | Nửa ngày | Bằng chứng Observed Problem | — |
| 6 | **A3 cơ chế từ chối** | Không | 1 ngày | err nhóm Null giảm | Có thể làm tụt acc |
| 7 | **Cụm B gộp đồ thị** | **CÓ** | ~1 ngày | Designed Mechanism thứ hai | Chỉ số cấu trúc vẫn đẹp |
| 8 | Cụm C dọn lãng phí | Một phần | 1 giờ | Tiết kiệm quota | — |

**Nếu chỉ có thời gian cho ba việc:** 1 → 3 → 4. Đủ để có một Proposed Method hoàn
chỉnh theo 5 bước, kèm cả Quality lẫn Efficiency.

**Nếu chỉ có thời gian cho một việc:** số 1. Không viết dòng code nào mà cứu được toàn
bộ phần thống kê của báo cáo.

---

## 7. Những chỗ tôi nghĩ kế hoạch này có thể sai

Ghi ra để anh cân nhắc, không phải để tự bảo hiểm.

**Tôi đang suy ra nguyên nhân từ code, chưa từ dữ liệu lỗi.** Cả 10 nhược điểm đến từ
đọc code và thống kê đồ thị, không phải từ việc phân loại các câu trả lời sai. Failure
Taxonomy của Tài có thể chỉ ra rằng phần lớn lỗi đến từ chỗ không có trong danh sách
này. **Đó là lý do T4–T6 là đường găng, và kế hoạch này không thay thế nó.**

**A1 đã sai một lần theo đúng kiểu này.** Docx khẳng định nhược điểm 1 "nhiều khả năng
là nguyên nhân chính khiến Multi-hop chỉ đạt 42,86%". Lập luận từ code rất chặt, kết
quả thực nghiệm không xác nhận. Các hạng mục còn lại được lập luận bằng đúng phương
pháp đó, nên có cùng kiểu rủi ro.

**Ước lượng công là ước lượng.** A2 ghi "1–2 ngày" là cho phần viết code; phần gỡ lỗi
khi cắt tỉa làm hỏng nhóm Multi thì chưa tính.

---

## 8. Anh cần quyết định

1. **Chạy 637 câu cho baseline Gemini ngay đêm nay?** — 5 giờ, 0 đồng, không cần code.
2. **A2 có phải là Proposed Method của nhóm không?** — nếu có thì tôi dựng khung đo
   Efficiency trước, vì bảng kết quả hiện chưa có cột nào cho nó.
3. **Cụm B: làm hay bỏ?** — một ngày công và ~0,5 USD, đổi lấy Designed Mechanism thứ
   hai và các chỉ số cấu trúc không dính sàn nhiễu.
4. **A3 có chờ 637 câu không?** — tôi đề nghị có; làm trên n = 20 là tốn quota để thu
   về con số không diễn giải được.
