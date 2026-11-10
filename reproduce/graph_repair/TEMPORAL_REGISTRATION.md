# V_t — đăng ký trước khi chạy

Ngày 09/11/2026. Đóng băng SHA-256 tại `logs/graph_repair/temporal/REGISTRATION.sha256` trước mọi lượt chạy. Thiết kế: `TEMPORAL_DESIGN_ASTRA.md`; đối chứng: `CPAPER_REGISTRATION.md`, `PAPER_SETUP.md`. Mọi thay đổi sau đây cần phụ lục có thời điểm và kết quả đã xem.

## Nguồn gốc và giả thuyết

Ý tưởng nảy sinh khi xem **thống kê truy hồi của 435 câu ngoài dev**; do đó tập đó không còn hoàn toàn untouched để phát triển ý tưởng. Việc triển khai và sàng lọc dưới đây chỉ đọc dev 200, trong đó 180 câu có Evidence. Failure quan sát: C0 giữ đủ gold ở 75/180; nhóm có ngày chỉ 5/23. Giả thuyết: anchor ngày từ timestamp tài liệu, kết hợp đường tới entity, cứu Evidence bị xếp thấp trong ngân sách cố định. Đây là cơ chế cần kiểm nghiệm, chưa phải cải thiện accuracy được xác nhận.

## Cơ chế cố định

Parser xác định T(q): `YYYYMMDD`, `YYYY-MM-DD`, `YYYY/MM/DD`; tên tháng đầy đủ hoặc viết tắt với ngày theo cả hai thứ tự; tháng không ngày chỉ khi có năm hoặc giới từ `in/during/within/for/of`. Thiếu năm chỉ suy ra nếu corpus đúng một năm. Kiểm lịch hợp lệ, khử trùng, không thêm tháng khi đã có ngày cùng tháng. Bỏ qua relative, weekday, holiday và khoảng mở `before/after`; ngày tuyệt đối trong câu vẫn là anchor mềm. Không sửa keyword prompt. **Quyết định mơ hồ:** `Time:` đầu tài liệu là ngày nguồn duy nhất; parser không suy năm từ câu lân cận. Month-only không có ngày chỉ tạo node tháng. Câu có cả ngày và tháng riêng biệt giữ cả hai nếu không trùng tháng.

Đồ thị RAM: `G_T=(V_c∪V_e∪V_t, E_α∪E_β∪E_γ)`, `V_t=V_day∪V_month`. `E_γ` nối chunk với ngày và tháng của `Time:` trong full doc mà `full_doc_id` của chunk trỏ tới; `E_β` từ `source_id` entity. Không ghi index; không NEXT-day, không hierarchy. Qwen/Phi dùng cùng mã trên index riêng.

**C0:** với từng cặp keyword–seed `(u,s)` có `(s,c)∈E_β`, `h_q(c)=1+Σ max(0,ω_v(s|u))`, mỗi cặp tính một lần. `MINIRAG_TEMPORAL_H=1` ép `h=1` cho đối chứng metadata. Với mỗi `t∈T(q)`, `L_t` là ba chunk kề t xếp `(−h_q,−S_0,ID tăng)`; `B_t=2×(10 nếu L_t[0] thuộc vector30, ngược lại 1)`; `S_T(c)=S_0(c)+Σ_{t:c∈L_t}B_t h_q(c)`. Giữ mọi contribution cũ; ×10 áp cả ba chunk. Top 30 theo điểm, hòa giữ thứ tự chèn Counter cũ; chunk mới chèn theo seed thời gian tăng và thứ tự `L_t`. Giữ prefix-stop 4.000 token; nếu baseline Sources rỗng nhưng có time seed thì có thể trả Sources. `MINIRAG_TEMPORAL_EXPAND=0`: chỉ boost ứng viên đã có trong S_0, không thêm ID mới.

**C-paper:** kích hoạt đúng T(q), `V̂_s'=V̂_s∪T(q)`, `ω_v(t|date expression)=1`, answer nodes vẫn chỉ là entity. Duyệt đường đơn đúng 4 cạnh, top 10/cặp, cap 5.000 như C-paper. Eq. (2') tính `ω_e'(e)=Σ_{v∈V̂_s'∪V̂_a}1[v∈G'_{e,10}]` trên graph mở rộng, chỉ chọn cạnh E_α và giữ số lượng baseline. Eq. (3') `ω_p'=ω_v(seed)×[1+Σ_{E_α được chọn}ω_e'+Σ_{V̂_a}1+Σ_{E_γ}1]`; trọng số E_γ là 1. `A_T=N_γ(T(q))`; **Step 1 thay đổi** thành `C_graph' ∩ (V̂_c^vector30 ∪ A_T)`. Chunk temporal vẫn cần đường graph giữ lại; không append thẳng vào Sources. Step 2 `chunk+d_eβ` MiniLM, top 5/6.000, prompt và format giữ nguyên. `MINIRAG_TEMPORAL_EXPAND=0` giữ giao vector30 gốc. `MINIRAG_TEMPORAL_H=1` trong C-paper chỉ giữ nhánh timestamp trực tiếp và các đường baseline, bỏ temporal traversal/Eq. (2'–3'); metadata branch dùng cùng Step 2, là đối chứng của tương tác.

## Arms và quy tắc đọc

| Table 2 | C0 | C-paper |
|---|---|---|
| Full | C0+V_t | C-paper+V_t |
| −V_t | C0 đóng băng | C-paper đóng băng |
| −temporal–entity interaction | `h=1` | timestamp trực tiếp + đường baseline |
| −candidate expansion | chỉ boost chunk cũ | giao vector30 gốc |

Primary: **C-paper vs C-paper+V_t**. Secondary: **C0 vs C0+V_t**. Mọi nhánh cùng index riêng của Qwen/Phi, MiniLM, cache parser, prompt, judge và cấu hình sinh. Bất biến: `T(q)=∅` trả context giống baseline **từng byte**. Trước hết C0 tắt switch phải khớp 180/180 bản ghi đóng băng; sau đó dev-180 **một lượt** screening full-evidence, báo b/c/McNemar hai phía, token Sources, latency p50/p90, cap, Single/Multi. Không đổi parser, cap, hệ số theo screening. Kết quả mô phỏng đã biết: 75→91/180, 16 lên/0 xuống, p=0,00003052; 0/154 non-temporal đổi; `h=1` 86/180, Full so control 5/0, p=0,0625. Đây chỉ là retrieval, không suy accuracy.

Sau screening: kế hoạch accuracy **ít nhất 3 lượt sinh × 3 lượt judge**, ghép theo câu, Qwen **và** Phi. Báo acc/err/neither, b/c/p McNemar cho acc **và** err, độ ổn định giữa lượt, ma trận chuyển của Null/Single temporal, sửa nhiều phép so hai model; không coi lượt lặp là câu độc lập. Tiêu chí thắng đăng ký: acc tăng **và** err giảm ổn định. Dự đoán có thể tăng retention ngày; dấu err chưa rõ vì Null có ngày cũng trỏ tài liệu. C-paper có thể mất lợi ích tại cap đường hoặc Step 2. Không dự đoán Phi hơn Qwen. Không tuyên bố cải thiện Multi-hop, efficiency, graph hơn metadata/vector, giảm err, hay novelty của timestamp đơn thuần chỉ từ dev screen. Không gọi C-paper gốc là phương pháp mới, và không gọi bản C-paper+V_t là C-paper nguyên bản.

## Sửa đổi 1 — đo accuracy (10/11/2026)

Trước sửa đổi này đã xem **kết quả truy hồi dev 180** trong `TEMPORAL_RESULT_DEV.md`: C0 giữ đủ Evidence 75→91, 16 lên/0 xuống, p=3,1·10⁻⁵; C-paper 55→59, 4/0, p=0,125; câu không có anchor giữ context đúng từng byte 154/154. Chưa xem kết quả accuracy C0+V_t nào trên 435 câu. Thống kê truy hồi trên 435 từng góp phần hình thành giả thuyết, nên 435 không hoàn toàn untouched; công bố giới hạn này.

Phép đo thứ cấp C0 tập trung vào `L-C0` (switch tắt) và `L-T` (C0 + `MINIRAG_TEMPORAL=1`) riêng trên index Qwen2.5-3B và Phi-3.5 RoPE tĩnh đã đóng băng. Dùng 435 câu ngoài dev, seed sinh 101/202/303, `PYTHONHASHSEED=13`, keyword cache đúng baseline cùng model và seed, prompt và A1@4000 cũ. Hai arm của mỗi SLM sinh trong **cùng deployment Modal, cùng session**, file serving cũ. Trước GPU: L-C0 dựng lại phải khớp context baseline 435/435 từng seed; L-T chỉ được đổi context khi parser T(q) có anchor. Ghi danh sách ID parser fires và ID context đổi.

Judge giữ `gemini-3.5-flash-lite` ghim, prompt V1, 3 pass, seed 13, nhãn strict, retry/abstain như đợt Phi. Một bộ ba `(Question, Gold Answer, answer text)` giống **từng byte** giữa mọi arm/seed/model chỉ chấm một lần (3 pass); lưu manifest bộ ba duy nhất và ánh xạ ID gốc→ID duy nhất, công bố số lượt gọi tiết kiệm. Không gộp các seed/model thành câu độc lập. Phân tích riêng từng SLM × seed: acc/err/neither theo majority và mean±sd ba pass, b/c và McNemar chính xác hai phía **riêng acc và err**, nhóm temporal/non-temporal, Single/Null (Multi mô tả thêm). Quy tắc xác nhận acc: cả ba seed cùng chiều tăng, p<0,05 ở **mỗi** seed; báo quy tắc tương tự cho err theo chiều giảm. Để gọi là thắng theo đăng ký ban đầu cần cả acc tăng và err giảm ổn định. Nếu so hai model như một họ phép thử, báo hiệu chỉnh đa kiểm định; không gộp điểm hai model. Không diễn giải retrieval dev thành accuracy.

## Sửa đổi 2 (10/11/2026, 09:50) — thứ tự chạy; đã xem: cổng context Qwen s101/s202 (435/435, 41 câu đổi), chưa xem câu trả lời nào

Không đổi nhánh, biến hay luật đọc. Sinh câu trả lời của **mỗi SLM** bắt đầu ngay khi **cả 3 lượt của chính SLM đó** qua
cổng context, không chờ SLM kia (hai SLM vốn là hai deployment riêng; context Phi dựng trên CPU song song không ảnh
hưởng GPU). Lý do: tiết kiệm 2–3 giờ chờ. Điều kiện cho Phi giữ nguyên: đủ 3 cổng Phi rồi mới deploy Phi.

## Sửa đổi 3 (10/11/2026, 11:45) — ghép cặp bằng cùng mẫu sinh; đã xem: câu trả lời Qwen s101 (chưa chấm câu nào)

**Đã xem trước khi viết:** chỉ so chuỗi câu trả lời Qwen s101 giữa hai nhánh, không có phán quyết judge nào. Ở 394 câu
mà context L-T trùng từng byte với L-C0, chỉ **121/394** câu trả lời trùng nhau: sinh vLLM không tất định với cùng
prompt + seed (nghi do batching trên GPU). 41 câu có context đổi: 0/41 trùng.

**Phân tích chính (thay cho phép so 435 câu thô):** với câu mà context L-T trùng từng byte context L-C0 ở cùng lượt,
can thiệp không tác động theo định nghĩa → dùng **cùng một câu trả lời của L-C0 cho cả hai nhánh** (common random
numbers). Câu có context đổi dùng câu trả lời riêng của mỗi nhánh. Ước lượng chênh lệch không thiên lệch; chỉ bỏ nhiễu
lấy mẫu ở câu không bị can thiệp. Mẫu số vẫn là 435 câu mỗi lượt; McNemar acc và err, luật 3 lượt như cũ.

**Phân tích phụ, báo kèm:** phép so thô dùng câu trả lời riêng của L-T cho mọi câu (cần chấm thêm toàn bộ L-T).

**Judge:** chấm đủ L-C0 435 × 3 lượt (cả hai SLM); L-T chỉ cần chấm các câu context đổi cho phân tích chính; phân tích
phụ chấm phần còn lại khi còn quota. Chấm sớm 41 câu đổi của Qwen chỉ để xem trước, không dùng để quyết định gì.
