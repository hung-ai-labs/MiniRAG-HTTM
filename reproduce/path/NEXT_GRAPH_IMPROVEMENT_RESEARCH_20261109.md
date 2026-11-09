# Cải tiến tiếp MiniRAG sau C1/C3: chẩn đoán trước, cơ chế đồ thị sau

Ngày: 09/11/2026. Trạng thái: **findings và đề xuất nghiên cứu có điều kiện**.
Không sửa runtime, không đổi profile, không chạy thêm API, không đăng ký hay
triển khai lại hướng reranker đã đóng. Lượt QA C0/C1/C3 đang chạy là study riêng.

## 1. Quyết định nên làm ngay

Ưu tiên kiểm từng ca của **16 cặp evidence không có trong pool C1 lẫn dense
top-30** và **11 cặp chỉ có trong pool C1**. Chưa nên tiếp tục thử các hệ số
nhân điểm path. Chưa đủ cơ sở chọn một công thức mới làm proposed method.

Mục tiêu là tìm lỗi cấu trúc mà similarity thuần không xử lý được: liên kết sai
sự kiện, mất nguồn quan hệ, thiếu cầu nối hoặc merge thực thể sai. Nếu không
tìm thấy lỗi như vậy, kết quả hợp lệ là một finding về pipeline, không phải
ép ra một phương pháp đồ thị để vượt baseline trên dev đã xem nhiều lần.

## 2. Nguồn và mức độ kiểm chứng

| Nguồn | Đã làm gì | Được phép kết luận |
|---|---|---|
| `minirag/operate.py::kwd2chunk` | Đọc code đang có | C1 không nhân affinity ở bước gộp chung |
| Frozen C1 inputs và replay | Replay độc lập bằng hàm production, giữ dtype và thứ tự | Khớp 200/200 graph top-30 |
| Phễu, graph-only và neither | Đếm lại trên gold cố định, không embedding/generation | Các số ở mục 3 được kiểm chứng độc lập |
| Scratch `cf.py`–`cf5.py` do người dùng cung cấp | Đọc nguồn, chưa chạy lại tất cả phản thực tế | Bảng mục 4 là số được cung cấp, chưa coi là một lượt tái lập độc lập |
| C3 relation-lift | Đọc report/ablation của study trước | C3 chưa chứng minh vượt C1 hoặc affinity-only |
| Cơ chế provenance ở mục 8 | Phác thảo, chưa triển khai/đo | Chỉ là giả thuyết cho bước sau audit |

Artifacts kiểm tra mới, không chạy retrieval:

- `logs/path_funnel/20261109/verified_funnel.json`.
- `logs/path_funnel/20261109/cases_to_review.jsonl`: 27 cặp, có question,
  gold chunk ID, nội dung và vị trí mất; **tất cả chưa được thẩm định nhãn**.

Nguồn scratch ở `/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/650cf207-3971-4870-a61d-727a3a230102/scratchpad/`.
Đường dẫn tạm này không phải artifact bền vững; trước khi công bố phải đưa
script, input hashes, cấu hình và output vào một study riêng của repo.

## 3. Phễu evidence đã kiểm chứng

Dev 200 gồm 180 câu có evidence, 207 cặp query/evidence-chunk. Một câu có thể
đóng góp nhiều cặp; **27 cặp không đồng nghĩa 27 câu hoặc 27 lỗi độc lập**.

```text
207 cặp chuẩn
  │
  ├── 38 không có trong pool top-3/seed
  │      ├── 22 có trong dense top-30
  │      └── 16 cũng không có trong dense top-30
  │
  └── 169 có trong pool C1
          ├── 8 không vào graph top-30
          └── 161 có trong graph top-30
                  ├── 35 mất sau A1@4000
                  └── 126 giữ được
```

Trong 169 cặp có trong pool, **11 không có trong dense top-30**. Đây là tính
bổ sung về ứng viên, chưa phải lợi ích QA hay bằng chứng suy luận multi-hop.
Dense có thể tìm các cặp này ở độ sâu lớn hơn 30; không viết “dense không tìm được”.

Con số 161 là trần coverage của **tập graph top-30 hiện có**. Scratch oracle
chỉ giữ các gold chunk, chưa áp lại ngân sách lên toàn bộ thứ hạng oracle;
vì vậy cần kiểm tổng token gold/câu trước khi gọi 161 là kết quả đạt được ở
4.000 token. Dù đạt được, oracle vẫn dùng nhãn và không phải thuật toán runtime.

## 4. Các phản thực tế được cung cấp

| Phản thực tế | Cặp /207 | Câu đủ /180 | McNemar so C1 |
|---|---:|---:|---|
| C1 | 126 | 102 | Mốc |
| Cộng seed × affinity | 133 | 109 | 7 lên /0 xuống; p≈0,016 |
| Xếp pool C1 theo affinity | 141 | 116 | 21/7; p≈0,013 |
| Bỏ seed dưới knee | 111 | 89 | 11/24; p≈0,041 |
| Chia điểm cho số entity của chunk | 126 | 102 | 8/8 |
| Max thay cộng seed | 120 | 96 | Không có cặp lệch trong bản tóm tắt |
| Bỏ qua chunk tràn rồi xét tiếp | 128 | 104 | Chưa đủ số ghép cặp để kết luận |
| Dense thuần | 148 | 122 | 29/9 |
| RRF(pool-affinity, dense) | 149 | 123 | Chưa có kiểm định ghép cặp so dense |

Các p này là exploratory, chưa hiệu chỉnh toàn bộ số phép thử. Không chọn
một dòng p<0,05 làm bằng chứng xác nhận sau khi đã thử nhiều biến thể.
Một cặp tăng của RRF so dense không đủ kết luận lợi ích của đồ thị.

Trước tái lập chính thức cần giữ dtype, tie-break và định nghĩa boost đúng
production: scratch dùng `j==0`, còn code dùng so sánh equality; chuyển seed
score sang Python float cũng có thể đổi tie rất sát. Replay baseline khớp
200 câu là kiểm tra tốt nhưng không tự bảo đảm mọi phản thực tế đã tương đương.
RRF trong scratch có thể xếp cả union dài hơn 30; phải ghi đúng cap áp lên
danh sách nào để không gọi nhầm mọi dòng là cùng graph top-30.

## 5. Cơ chế đang làm mất thứ hạng

Với C1, điểm gộp có thể mô tả bằng:

```text
Global_C1(c) = tổng đóng góp seed-score và boost của những entry chọn c
```

Affinity chỉ tham gia chọn ba chunk/seed. Khi bỏ side-channel điểm ở C1,
`kwd2chunk` không còn biết chunk nào có affinity cao hơn. Nhiều entry cùng
ủng hộ một chunk có thể lấn át một số ít entry phù hợp hơn. Không nên hiểu
các phiếu này là bằng chứng độc lập: các seed/path có thể chia sẻ cùng hub,
cùng nguồn và cùng sự kiện.

Scratch báo median 105 seed/câu; với các gold bị cap, affinity median 0,40
so với 0,30 của chunk đứng trước, nhưng support median 3 so với 5. Đây là
tín hiệu phù hợp giả thuyết đếm trùng, **chưa cô lập nhân quả** vì seed score,
boost, độ dài và sự phụ thuộc giữa nguồn cùng thay đổi.

Lưu ý về chunk `…4fc1ba`: `cf3.py` đếm nó trong **global top-3** ở 33/180 câu,
không phải đếm số lần nó được chọn trong top-3 của từng seed. Hai thống kê
này cần phân biệt khi trình bày finding hub.

Ba điều không nên suy rộng:

1. Phễu là vị trí mất, không phải phân rã tác dụng can thiệp. Đổi top-3/seed
   cũng có thể đổi tổng phiếu, graph top-30 và phần bị cap; không chỉ tác động 38+8.
2. Pool có 169/207 vẫn thiếu 38 cặp và có nhiều chunk nhiễu. Chưa thể nói
   “đồ thị giỏi chọn ứng viên” theo nghĩa vượt dense hoặc có precision cao.
3. Các phép thử đã thất bại không chứng minh mọi hiệu chuẩn tương lai hết dư địa.
   Kết luận đúng là chưa có cơ chế graph-specific vượt các đối chứng mạnh.

## 6. Đặt C3 mới vào bức tranh này

C3 relation-lift giữ cùng ID/thứ tự ứng viên C1 nhưng truyền trọng số
`affinity × F/B` vào gộp chung. Vì vậy C3 đã tác động vào điểm nghẽn global,
không chỉ vào local selection. Tuy nhiên nó vẫn cộng đóng góp qua seed;
chuẩn hóa mỗi seed không loại bỏ sự phụ thuộc **giữa nhiều seed**.

| Study C3 đã chạy | Cặp /207 | Câu đủ /180 |
|---|---:|---:|
| C1 | 126 | 102 |
| C3 relation-lift | 132 | 108 |
| Không relation signal | 133 | 109 |
| Affinity-only | 133 | 109 |

C3 vs C1: 9 lên/3 xuống, p=0,146. Quan hệ chưa thêm lợi ích đo được. Vì vậy
không diễn giải chẩn đoán mới thành “chỉ cần nối affinity là cứu được C3”.
Lượt QA mới giữ nguyên; không sửa công thức hoặc thay context giữa lượt đo.

## 7. Bước nghiên cứu tiếp theo: audit 27 cặp

Đọc question, gold answer, evidence annotation, chunk và nguồn path/cạnh.
Không dùng một mô hình judge mới để tự quyết định gold đúng hay sai.

| Trường cần điền | Mục đích |
|---|---|
| Pair ID, question/type, chunk ID | Truy vết, loại trùng câu |
| Nhãn gold có thật sự cần để trả lời? | Phân biệt evidence chuẩn với bằng chứng thay thế hợp lệ |
| Dense rank đầy đủ, affinity, token length | Phân biệt top-30 miss và semantic miss |
| Seed nào mang chunk vào, query entity tương ứng | Xác định graph-only đến từ đâu |
| Path, answer-type count, edge votes | Kiểm tra cơ chế P0 có giúp thật không |
| Source của từng cạnh, câu văn chứng minh quan hệ | Tránh coi source chứa entity là source chứng minh quan hệ |
| Cầu nối entity/quan hệ có hợp lệ không? | Tách multi-hop thật và đi qua hub |
| Thời gian, vai trò, cuộc hội thoại/sự kiện | Tìm nối nhầm cùng tên qua sự kiện khác |
| Nhãn nguyên nhân và mức chắc chắn | Không ép mọi ca vào cùng một giả thuyết |

Taxonomy tối thiểu: nhãn/alternate evidence; seed mapping; thiếu entity/edge;
mất provenance; nối sai sự kiện; đúng graph nhưng mất ranking/cap;
chunk/semantic mismatch; chưa đủ bằng chứng.

Hai nhóm chỉ là case study ưu tiên. Muốn kết luận nguyên nhân tổng quát phải
đối chiếu cả các ca thành công và ca hai retriever cùng tìm được, không chỉ
đọc những ca thuận cho giả thuyết. Một thành viên khác nên kiểm lại nhãn khó.

## 8. Hướng thiết kế có điều kiện: path có chứng cứ nguồn và sự kiện

**Chỉ mở nếu audit thấy nhiều path nối quan hệ đúng hình thức nhưng không
cùng ngữ cảnh, hoặc mất thông tin source–relation.** Đây là thay đổi biểu diễn
và chứng cứ của path, khác việc xếp lại chunk theo từ khóa/affinity thuần.

Một vấn đề code đáng kiểm: `_merge_nodes_then_upsert` và
`_merge_edges_then_upsert` ghép description và source_id theo các phép set/sort
riêng. Không được mặc định description thứ i ứng với source thứ i. C1 đang có
heuristic đối chiếu hai danh sách này; độ đúng của liên kết cần đo, không suy
ra từ việc số phần tử bằng nhau. Đây mới là quan sát tĩnh, chưa đo số ca hỏng.

Biểu diễn cần khảo sát:

```text
relation witness = (head, relation, tail, source_chunk,
                    supporting_text, event/time/role nếu có và kiểm chứng được)
```

Giữ mỗi witness gắn đúng nguồn thay vì chỉ một cạnh với hai danh sách đã merge.
Tận dụng extraction cache có nguồn trước; nếu không đủ dữ liệu, phải tạo
index phiên bản riêng bằng cùng model/embedding, không sửa index đóng băng.
Không thể suy ngược chắc chắn các witness đã mất từ hai danh sách không còn alignment.

Pipeline đề xuất để thảo luận, **chưa phải protocol được phép chạy**:

```text
Query parser, seed/type mapping gốc
       ↓
Mọi path gốc + P0 + semantic edge search/vote gốc
       ↓
Liên kết từng hop với witness có nguồn
       ↓
Kiểm tính tương thích cầu nối giữa các witness
       ↓
Điểm path có hỗ trợ provenance → nguồn node/cạnh
       ↓
Local selection → scorednode2chunk → dense/boost → kwd2chunk → cap → generation
```

Một họ công thức để diễn đạt giả thuyết là
`q_prov(p) = q0(p) × R(p) × W(p)`, trong đó `W` đo hỗ trợ của chuỗi witness
đúng nguồn/ngữ cảnh. **Chưa định nghĩa W đủ để triển khai**: cần audit xác định
ràng buộc nào quan sát được, cách xử lý unknown và lỗi extraction. Không dùng
gold ở runtime; không tự chọn trọng số/threshold sau khi xem dev.

Không yêu cầu mọi cạnh cùng một source_id: multi-hop hợp lệ thường nối nhiều
tài liệu. Không phạt chỉ vì thiếu timestamp; thiếu metadata phải được phân biệt
với mâu thuẫn có chứng cứ. Nếu audit chỉ phát hiện thiếu cạnh/seed mapping thì
phải sửa đúng tầng đó; không dùng W để “chữa” quan hệ chưa tồn tại.

Điểm khác với C3 hiện tại: C3 đo độ giống ngữ nghĩa từng cạnh đã merge; hướng
này hỏi **chuỗi quan hệ có được những nguồn cụ thể hỗ trợ một cách tương thích
hay không**. Hiệu quả và novelty đều chưa được chứng minh.

## 9. Đối chứng cần có nếu nhóm quyết định mở hướng mới

Đây là yêu cầu thiết kế cho tương lai, không đăng ký reranker bị cấm:

- C0, C1 và C3 hiện hành giữ nguyên để tách tiến bộ tích lũy.
- Dense thuần và affinity-only trên pool C1: bắt buộc để không quy lợi ích
  embedding thành lợi ích đồ thị; cùng ngân sách/tokenizer/model.
- Cơ chế mới bỏ phần provenance/compatibility, chỉ sửa lưu nguồn: tách bug fix
  với thuật toán. Không đồng thời đổi quá nhiều tầng rồi gọi một ablation là đủ.
- Xáo nguồn/witness có kiểm soát, giữ được các phân bố quan trọng: nếu kết quả
  không đổi thì chưa chứng minh thuật toán cần cấu trúc thật. Xáo có thể đổi
  support nên phải báo rõ đại lượng nào được bảo toàn, không coi là phép chứng minh tuyệt đối.
- Nếu đổi index: baseline cũng chạy trên index mới để tách lợi ích index
  khỏi scorer; thêm ablation index cũ/mới khi khả thi.

Đo pool → top-30 → Sources, cả pair retention và full-evidence/question,
graph-only/neither recovery, nguồn nhiễu Null, số path/seed/vector reads,
retrieval latency/memory và token. QA báo acc/err/neither, kiểm định ghép cặp,
lặp sinh và ba lượt judge; không chọn hệ số từ tập xác nhận.

Không lấy 435 câu ngoài dev làm tập chỉnh tiếp: nhóm đã đo nhiều kết quả trên
tập này. Tập xác nhận phải thực sự chưa dùng để lựa chọn phương pháp, hoặc
ghi rõ nó chỉ là external validation đã từng quan sát; cần benchmark/dataset
khác và split được đóng băng trước khi thử.

Nếu không thắng đối chứng affinity-only/dense, hoặc xáo đồ thị không làm mất
lợi ích, không viết “đồ thị giúp suy luận”. Một kết quả phủ định vẫn có giá trị.

## 10. Ràng buộc và tài liệu liên quan

`ROADMAP.md`, mục “Why deterministic reranking was closed”, chốt 20/09:
“không viết reranker, không tiền đăng ký reranker, không chạy sinh/giám khảo
cho hướng này”. Đổi tên thành “sửa bên trong C1” không tự tạo ngoại lệ.
Tài liệu này chỉ chẩn đoán; không đề nghị triển khai pool-affinity thành runtime
hoặc lập protocol cho hướng đã đóng. Nếu nhóm muốn mở lại thì phải quyết định
rõ phạm vi trước; yêu cầu hiện tại chỉ là nghiên cứu và viết tài liệu.

Đối chiếu literature từ nguồn gốc:

- [MiniRAG v1, §2.2.2](https://arxiv.org/html/2501.06713v1): đã kết hợp cấu trúc
  path với similarity ở bước chọn chunk. Thêm affinity vào code không tự là novelty.
- [HippoRAG 2](https://arxiv.org/abs/2502.14802): nghiên cứu graph retrieval với
  tích hợp passage sâu hơn và sử dụng LLM trực tuyến. Đây là đối chiếu về thiết kế,
  không chứng minh rằng thêm PPR hoặc model lớn sẽ cứu MiniRAG; không sao chép
  cấu hình khác model/ngân sách để gọi là cải tiến được kiểm soát.

Tóm lại về việc cần giao nhóm: giữ lượt QA đang có, thẩm định 27 cặp và các ca
đối chứng, đo lỗi nguồn/sự kiện, rồi mới chọn một giả thuyết có thể bị bác bỏ.
Không hứa vượt C0/C1/dense từ bảng chẩn đoán này.
