**Nên triển khai pilot này, nhưng chưa thể cam kết “acc tăng và err giảm”.** Dev cho tín hiệu truy hồi rõ: **75→91/180 câu giữ đủ gold**, nhưng phần vượt đối chứng metadata mới **5 câu, p=0,0625**. Chưa có kết quả generation, Phi hoặc C-paper.

Tôi chỉ đọc dữ liệu dev và index nguồn; không sửa file, chạy retrieval/index, hay gọi mạng/API.

**Kết quả dev đã chạy**

Dùng [c0_sim.py](E:/Project/MiniRAG/.worktrees/dialogue-role/reproduce/graph_repair/sim/c0_sim.py), DIAG, gold chunks và timestamp qua `full_doc_id`. Simulator tái tạo Sources C0 **180/180**, đúng thứ tự.

Trong 200 câu:

- **26 câu có ngày:** 21 Single, 2 Multi, 3 Null.
- **3 câu chỉ có tháng:** đều Multi.
- **171 câu không có ngày/tháng được parser hỗ trợ.** Không tính “April Fool’s” là tháng truy hồi.

| Nhóm có Evidence | n | C0 giữ đủ gold | Cơ chế đề xuất |
|---|---:|---:|---:|
| Có ngày | 23 | 5 — 21,74% | 21 — 91,30% |
| Chỉ tháng | 3 | 0 | 0 |
| Không ngày/tháng | 154 | 70 — 45,45% | 70 — 45,45% |
| **Toàn bộ** | **180** | **75 — 41,67%** | **91 — 50,56%** |

Nhóm **không có ngày**, kể cả tháng: C0 đạt **70/157=44,59%**.

Timestamp Evidence khớp ngày hỏi: **21/23 khớp toàn bộ**, **22/23 khớp ít nhất một Evidence**. Hai ngoại lệ là Multi; một câu hỏi ngày không xuất hiện trong Evidence. Cả **3/3 câu tháng** khớp toàn bộ tháng Evidence. Vì vậy không dùng ngày như bộ lọc loại trừ cứng.

So C0: **16 lên / 0 xuống, McNemar hai phía p=0,00003052**. Sources thay đổi ở 25 câu temporal; **0/154 câu không temporal thay đổi**. Với 17 Null không temporal ngoài log, no-op được bảo đảm bằng nhánh chương trình, chưa kiểm bằng context thực tế.

Sources tokens trung bình **3.617→3.609**, trung vị **3.692→3.692**, tối đa **4.000**. Đây không phải bằng chứng cải thiện efficiency hay accuracy.

**Cơ chế hình thức**

Mở rộng Eq. (1):

\[
G_T=(V_c\cup V_e\cup V_t,\ E_\alpha\cup E_\beta\cup E_\gamma),
\qquad V_t=V_{\text{day}}\cup V_{\text{month}}.
\]

\[
(c,t)\in E_\gamma
\iff \operatorname{date}(\operatorname{doc}(c))\in\operatorname{interval}(t).
\]

Mỗi chunk nối ngày và tháng của **timestamp tài liệu**, không phải ngày sự kiện được nhắc trong nội dung. Dựng overlay trong RAM từ kho tài liệu/chunk; \(E_\beta\) lấy từ `source_id` của entity. Không gọi SLM, không index lại; cùng quy tắc cho Qwen/Phi, còn topology entity vẫn thuộc graph riêng của từng model.

Không thêm NEXT-day hoặc hierarchy: chưa có giả thuyết thực nghiệm cần chúng; chúng tạo đường nối không liên quan. Appendix C mô tả tính tiến triển thời gian, nhưng không chứng minh mọi ngày liền nhau có quan hệ ngữ nghĩa. Nguồn: §3 và Appendix C của :codex-file-citation{path="E:/Project/MiniRAG/miniRAG1.pdf" purpose="source"}.

Parser xác định \(T(q)\):

- Nhận `YYYYMMDD`, `YYYY-MM-DD`, `YYYY/MM/DD`, tên tháng đầy đủ/viết tắt với ngày, hai thứ tự ngày–tháng.
- Tháng không ngày phải có năm hoặc ngữ cảnh `in/during/within/for/of`.
- Thiếu năm: chỉ suy ra khi corpus có đúng một năm.
- Kiểm ngày hợp lệ; khử trùng; không thêm seed tháng trùng ngày đã nhận.
- Không giải relative expressions, weekday, holiday hoặc khoảng mở `before/after`; ngày tuyệt đối bên trong vẫn là **anchor mềm**.
- \(T(q)=\varnothing\): gọi nguyên baseline, không đưa overlay vào traversal hay scoring.

Không sửa keyword prompt.

**Tích hợp C0 — chính công thức đã mô phỏng**

Gọi \(S_0(c)\) là tổng contribution C0 trong DIAG. Với cặp keyword–seed \((u,s)\), dùng cosine hiện có:

\[
h_q(c)=1+
\sum_{\substack{(u,s)\\(s,c)\in E_\beta}}
\max(0,\omega_v(s\mid u)).
\]

Số 1 biểu diễn đường trực tiếp \(t\to c\); tổng biểu diễn các đường \(t\to c\to s\). Mỗi cặp keyword–seed tính một lần.

Với mỗi \(t\in T(q)\), lấy \(L_t\): **ba** chunk kề \(t\), sắp theo \(h_q\) giảm, \(S_0\) giảm, ID tăng. Đặt:

\[
B_t=2
\begin{cases}
10,&L_t[0]\in V_{\text{vector30}},\\
1,&\text{ngược lại},
\end{cases}
\]

\[
S_T(c)=S_0(c)+
\sum_{t\in T(q)}\mathbf1[c\in L_t]B_t h_q(c).
\]

Giữ nguyên mọi contribution cũ. ×10 áp cho **cả ba chunk**, đúng hành vi vòng lặp C0. Không thêm hệ số cần tuning.

Lấy top-30 theo \(S_T\), giữ thứ tự hòa cũ của Counter; chunk mới chèn theo seed thời gian tăng rồi thứ tự \(L_t\). Dùng nguyên prefix-stop 4.000 token. Nếu baseline không có Sources nhưng time seed có chunk, nhánh thời gian vẫn được phép trả Sources.

**Tích hợp C-paper**

Theo [registration hiện tại](E:/Project/MiniRAG/.worktrees/c-paper/reproduce/graph_repair/CPAPER_REGISTRATION.md), chỉ kích hoạt các time node thuộc \(T(q)\):

\[
\hat V_s'=\hat V_s\cup T(q),\qquad
\omega_v(t\mid\text{date expression})=1.
\]

Giữ answer nodes thuộc entity. Duyệt đường đơn **đúng bốn cạnh**, top-10 mỗi cặp, cap 5.000 như baseline; không padding đường ngắn.

Mở rộng Eq. (2) trên graph đang kích hoạt:

\[
\omega_e'(e)=
\sum_{v\in\hat V_s'\cup\hat V_a}
\mathbf1[v\in G'_{e,10}],\quad e\in E_\alpha.
\]

Giữ số cạnh \(E_\alpha\) được chọn như C-paper. Với cạnh temporal, đặt \(\omega_\gamma=1\). Eq. (3):

\[
\omega_p'(p\mid u)=\omega_v(s\mid u)
\left[
1+\sum_{e\in p\cap\hat E_\alpha'}\omega_e'(e)
+\sum_{v\in p\cap\hat V_a}1
+\sum_{e\in p\cap E_\gamma}1
\right].
\]

Như vậy thời gian tham gia seed, traversal và điểm đường.

Đặt \(A_T=N_\gamma(T(q))\). Tập graph candidate gồm chunk trên đường giữ lại và chunk kề entity trên những đường đó. Step 1 trở thành:

\[
C_{\text{cand}}=
C_{\text{graph}}'
\cap
(\hat V_c^{\text{vector30}}\cup A_T).
\]

**Đây là mở rộng semantic mapping, không phải giữ nguyên Step 1 của baseline.** Không thể vừa giữ vector top-30 bất biến vừa cứu chunk ngoài nó. Giao cứng vẫn tồn tại: chunk temporal phải được đường graph giữ lại hỗ trợ; không tự động append vào Sources. Chunk cô lập không có đường dài bốn cạnh vẫn có thể mất.

Giữ Step 2 MiniLM với `chunk+d_eβ`, top-5/6.000, prompt và format context. Không thêm mô tả temporal vào prompt. Phải đăng ký thay đổi này rõ ràng, không gọi Ours là C-paper “nguyên bản”.

**Phản biện metadata và Table 2**

Nút ngày tự nó không tạo novelty. Phần graph cần chứng minh là **tương tác temporal–entity ảnh hưởng lựa chọn/điểm**, ngoài lợi ích tra timestamp.

Đối chứng đã chạy đặt \(h=1\), giữ nhánh metadata, boosts và packing: **86/180**, so full **91/180: 5 lên / 0 xuống, p=0,0625**. Vì vậy chưa được viết “graph interaction vượt metadata”. Đối chứng này cũng thay đổi độ lớn vote; cần thêm comparator metadata ưu tiên ngày với cùng ngân sách trước khi quy hiệu quả cho topology.

Ba dòng ablation dưới dòng Full:

| Dòng Table 2 | Can thiệp |
|---|---|
| −\(V_t\) | Trở lại baseline tương ứng |
| −temporal–entity interaction | C0: \(h=1\). C-paper: nhánh timestamp trực tiếp + đường baseline, bỏ temporal traversal/Eq. (2–3) |
| −candidate expansion | Chỉ tăng điểm ứng viên cũ; C-paper giữ giao vector top-30 nguyên bản |

Báo acc/err/neither, full-evidence, Sources tokens, latency p50/p90 và tỷ lệ chạm cap. Không suy graph contribution từ Full thắng baseline.

**Err, novelty và triển vọng**

Ba Null có ngày trên dev đều trỏ tới ngày có tài liệu: lần lượt **1, 1, 2 chunk**. Có đúng ngày không đồng nghĩa có đáp án; cơ chế có thể tăng trả lời sai tự tin. Đo riêng ma trận chuyển trạng thái acc/err/neither của temporal Null và Single; kiểm McNemar trên chỉ báo **err**, song song với acc. Không thêm verifier hay cơ chế từ chối.

Novelty khả dĩ chỉ là **temporal grounding xác định kết hợp đường dị thể của MiniRAG dưới SLM/ngân sách cố định**. Temporal KG, temporal GraphRAG và chat-memory retrieval đã là các hướng có trước; không thể nhận novelty cho “thêm timestamp”. Theo giới hạn không mạng, tôi chưa đối chiếu chi tiết TimeR4, T-GRAG, TG-RAG, MemoryBank/LongMemEval để khẳng định khác biệt thuật toán hay ưu tiên công bố.

Với khoảng 8% coverage ngày, trần ảnh hưởng toàn tập rất thấp; dev có coverage lớn hơn nên không ngoại suy mức tăng 8,89 điểm retention. Giả thuyết làm việc cho cả Qwen/Phi: acc có thể tăng vài điểm; **dấu err chưa xác định**. C-paper còn có thể mất lợi ích ở path cap hoặc Step 2. Chưa có cơ sở dự báo Phi hơn/kém Qwen.

Không thể đưa xác suất thắng từng ô như một ước lượng thực nghiệm. Minh họa có điều kiện: 20 cặp lệch accuracy, xác suất chiều tốt 0,75 ⇒ power khoảng **61,7%**; 10 cặp lệch err, chiều tốt 0,70 ⇒ **14,9%**. Xác suất cùng thắng không vượt 14,9% trong kịch bản ấy; đây không phải dự báo hai model.

MultiHop-RAG chỉ nên là mở rộng riêng: publish date không nhất thiết là event date; phải kiểm giả thuyết grounding trước.

**Đăng ký khuyến nghị**

| Quyết định | Chốt cho implementer |
|---|---|
| Primary Table 1 | C-paper/Ours × Qwen/Phi; C0 là đối chứng phụ, không đổi primary sau kết quả |
| Nguồn ý tưởng | Công khai phát hiện từ thống kê 435; dev dùng screening; không gọi 435 hoàn toàn untouched |
| Cơ chế | Parser, overlay và công thức trên; không tuning sau screening |
| Bất biến | Index riêng mỗi SLM; cùng judge, embedding, prompt, generation settings; budget theo baseline |
| Regression | Không temporal: context phải giống từng byte; hiện Sources đã kiểm 154/154 |
| Xác nhận | Ít nhất 3 lượt sinh × 3 lượt judge; ghép theo câu, không coi lượt lặp là mẫu độc lập |
| Tiêu chí thắng | acc↑ **và** err↓; báo b/c/p cho cả hai, độ ổn định qua lượt; hiệu chỉnh hai model |
| Giới hạn tuyên bố | Chưa có bằng chứng giảm err, cải thiện Multi hoặc graph vượt metadata |
| Bước tiếp | Pilot dev generation và C-paper/Phi; khóa bản đăng ký trước khi mở thêm kết quả ngoài dev |