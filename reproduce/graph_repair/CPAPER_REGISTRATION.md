# C-paper — đăng ký trước khi chạy dev 180

Ngày 09/11/2026. Nguồn: `PAPER_SETUP.md` (§3.1–3.2, tr. 37123–37126; A.3/B, tr. 37134/37136), `PAPER_CODE_AUDIT.md`, `GRAPH_TEAM_PLAN.md`. Chỉ đã đọc GraphML để đếm đường; **chưa chạy C-paper hay xem outcome dev/blind**. Bản này đóng băng bằng `logs/graph_repair/cpaper/REGISTRATION.sha256`; sửa đổi sau này phải ghi phụ lục riêng, thời điểm và kết quả đã xem.

## Vai trò và đối chứng

C-paper là **baseline thứ hai để khảo sát độ trung thành với bài báo**, không phải Proposed Method. Đối chứng C0 là code công bố + answer-type fix + A1@4000, `top_k=60`, index Qwen đóng băng. C-paper dùng cùng index, embedding MiniLM, parser cache, câu hỏi, không index lại, không SLM/API. Đổi nhiều cơ chế cùng lúc nên so C-paper–C0 không quy hiệu quả cho từng cơ chế; các công tắc con là ablation về sau.

## Quyết định đã chốt

| Điểm mở | Quyết định cố định | Cơ sở / giới hạn fidelity |
|---|---|---|
| Đồ thị | Dựng trong RAM từ GraphML: entity + chunk `source_id`, cạnh Eα entity–entity và Eβ entity–chunk. Không ghi index. | §3.1, tr. 37123. Đường đi có thể qua chunk. |
| d_eβ | Tách `description` theo `<SEP>` song song `source_id`; lệch số phần thì dùng toàn bộ description cho từng Eβ của node. | §3.1, tr. 37123; Qwen khớp khoảng 90%. Không có prompt d_eβ riêng. |
| V̂_c | `chunks_vdb.query(original_query, top_k=30)` (`top_k/2` của C0), dùng ID trả về, giữ ngưỡng vector hiện có. | §3.2.2, tr. 37126 không ghi số; cố định cùng truy vấn vector và kích thước code, không chọn theo kết quả. |
| Seed V̂_s | Với **mỗi** query entity: top 60 `entity_name_vdb.query(entity)` và top 30 `chunks_vdb.query(entity)`; đưa entity gắn chunk vào danh sách, lấy điểm lớn nhất từ hai phép cosine, giữ 60 entity sau sắp điểm giảm/tên tăng. | §3.2.1, tr. 37124 nói entity names và chunk content; cùng MiniLM, không truy vấn model mới. Quan hệ chunk→entity dựng từ GraphML. |
| “Pair” | Cặp `(query entity, seed entity)`; không gộp seed trùng trước khi top-k. | §3.2.2, tr. 37125. Đây là khác biệt với dict seed của code. |
| V̂_a | Chỉ node trong **hợp V̂_s** có `entity_type` khớp `answer_type_keywords`, chuẩn hoá quote/case như bản vá G1. | §3.2.1, tr. 37124–37125: chọn từ tập khởi đầu. |
| Êα / Eq. (2) | Ứng viên là Eα trên mọi đường đơn đã duyệt (không phải Eβ); tính omega trên **đồ thị dị thể** k=10, lấy số cạnh bằng `goodedge` của truy vấn vector code, hoà theo cặp tên entity. | Eq. (2), tr. 37125; A.3 tr. 37134 suy k=10. Số Êα bài không ghi: giữ kích thước của code/EQ2. Giới hạn duyệt cũng giới hạn ứng viên. |
| Đường đi / Eq. (3) | Đường đơn **đúng 4 cạnh** từ seed, tính `Score(seed) × (1 + Σ omega(Eα trên đường) + số V̂_a trên đường)`, giữ top 10 **mỗi cặp**, hoà theo tuple tên đường. Không có đường 4 cạnh ⇒ tập đường rỗng. | Eq. (3), tr. 37125: length-n; A.3 tr. 37134 suy k=10,n=4. Dùng lại `paper_edge_score.omega`/`paper_path_score.select_paper_paths`, không đổi mặc định EQ2/EQ3. |
| Chặn bùng nổ đường | Duyệt DFS theo tên node tăng, **tối đa 5.000 đường hoàn tất dài đúng 4 cạnh mỗi cặp**, rồi xếp Eq. (3) trên tập đã duyệt. | Đo GraphML dưới đây: không thể bảo đảm top 10 toàn cục cho hub. Đây là giới hạn fidelity minh bạch, không tuyên bố tương đương thuật toán. Không chỉnh cap sau khi thấy kết quả. |
| V_c^q và Step 1 | Hợp chunk kề mọi entity trên đường giữ lại (kể cả seed); giao cứng với V̂_c. Nếu <5, trả đúng số còn lại, kể cả 0; không bù từ ngoài giao. | §3.2.2 Step 1, tr. 37126. |
| Step 2 | Với mỗi chunk qua Step 1, ghép content rồi **mọi** mô tả d_eβ của chunk (thứ tự entity tăng), bỏ mô tả trùng; cosine MiniLM với original query. | §3.2.2 Step 2, tr. 37126 nói associated edge descriptions, không giới hạn theo kept paths. Mọi Eβ là cách hiểu trực tiếp nhất. |
| Step 3 / ngân sách | Điểm Step 2 giảm, hoà ID chunk tăng; tối đa 5 chunk, tổng token **không quá 6.000**, xét theo thứ tự và bỏ chunk vượt ngân sách để thử chunk kế. Đếm bằng tokenizer code. | §4.1/B tr. 37126/37136. Không cắt giữa chunk. |
| Context | Bảng Entities = V̂_a, Relationships = Êα, Sources = chunk chọn; CSV và prompt hiện có. Entity/relationship descriptions cắt theo ngân sách context hiện có. | §3.2.2 tr. 37126. `only_need_context` trả cùng format. |
| Công tắc con | `MINIRAG_CPAPER_CHUNK_NODES`, `MINIRAG_CPAPER_EDGE_DESC`, `MINIRAG_CPAPER_INTERSECTION`, `MINIRAG_CPAPER_EQ2`, `MINIRAG_CPAPER_EQ3` (mặc định 1 khi paper mode). Tắt chunk nodes: đường entity-only nhưng vẫn đọc `source_id` làm liên kết chunk; tắt edge desc: Step 2 content-only; tắt intersection: dùng V_c^q; tắt Eq2: chọn Êα theo vector code với trọng số 1; tắt Eq3: giữ mọi đường trong cap. | Ablation kiểu −R_chunk/−R_edge, §4.4 tr. 37128. Công tắc độc lập, không tái định nghĩa C0. |

## Đếm đường offline trước đăng ký

`cpaper_path_counts.py` chỉ đọc `E:\Project\MiniRAG\LiHua-World-qwen-modal\graph_chunk_entity_relation.graphml`; JSON ghi tại `logs/graph_repair/cpaper/path_counts.json`, có SHA-256 của GraphML và 16 hub. Đếm **chính xác** đường đơn dài **tối đa** 4 cạnh để đo tải duyệt bảo thủ (cấu hình C-paper chỉ giữ đường dài đúng 4 cạnh), bắt đầu ở mỗi trong 1.556 entity: 507 chunk node, 1.509 Eα, 3.851 Eβ. Trung vị **19.323**, p90 **301.541**, max **2.151.009**; 16 hub bậc entity cao nhất có khoảng **370.557–2.151.009** đường. Phép **đếm** toàn bộ seed mất 10,222 s trên máy này, nhưng hiện thực hoá/chấm điểm/sắp đường cho 60 seed × tối đa 5 query entity sẽ lớn hơn nhiều. Giới hạn 5.000/cặp giới hạn ≤1,5 triệu đường/câu; dự kiến vài đến vài chục giây/câu, **ước lượng chưa benchmark**. Báo thực tế p50/p90 sau chạy.

## Phép thử đăng ký

Chạy C0 regression trước: `chunk_ids` phải khớp `logs/c_ablation/graph/C0/C0_records.jsonl` **180/180** hoặc dừng. Sau đó C-paper trên đúng dev 180 có Evidence. Biến chính: số câu giữ **đủ mọi gold chunk** trong Sources cuối. Ghép cặp theo câu, báo b (C0 thiếu→C-paper đủ), c (C0 đủ→C-paper thiếu), McNemar chính xác hai phía và p; không dùng ngưỡng điểm. Phụ: số gold chunk giữ (micro), Single/Multi, median Sources tokens, retrieval time p50/p90 và số path bị cap. Không dùng retention suy ra accuracy; dev 180 chỉ sàng lọc vì đã dùng trong nghiên cứu trước. Xác nhận chất lượng/accuracy cần 435 ngoài dev và nhiều lượt sinh/chấm theo AGENTS.md §3, chỉ sau khi blind run hiện tại xong.

**Dự đoán trước:** C-paper có thể giữ nhiều câu đủ Evidence hơn C0 vì Step 2 cosine đưa chunk sát câu hỏi lên trước; ablation vector-only của nhóm đã mạnh hơn C0. Ngược lại giao cứng top 30 và giới hạn 5 chunk có thể làm mất gold ở Multi, nên không dự đoán chắc dấu McNemar. Sources token sẽ thấp hơn trần 6.000 và số chunk ≤5; thời gian truy hồi sẽ tăng do duyệt đường và embedding Step 2. Không hiệu chỉnh dự đoán/cap theo dev.

## Không được tuyên bố

Không gọi C-paper là đóng góp khoa học, không nói khôi phục chính xác bản nội bộ của tác giả hay tái hiện bảng paper (khác judge, index, cap đường và các tham số paper bỏ ngỏ). Không nói Eq. (2), Eq. (3), chunk nodes riêng lẻ gây cải thiện từ so sánh tổng hợp. Không nói graph thắng vector-only, cải thiện Multi-hop hay accuracy chỉ từ Evidence Recall. Không đổi `baseline.yaml`, index, hay mở kết quả blind để chọn thiết kế.

**Nhãn trong công cụ dùng chung:** `eval_offline.py` nhận paper mode qua biến môi trường và context thực tế áp top 5/6.000, nhưng trường `sources_budget` của report đang ghi cố định 4.000 và chữ “A1@4000” trong report không đúng cho C-paper. Không sửa công cụ dùng chung tại worktree này; thay đổi nhỏ nhất trên nhánh chung là đặt nhãn ngân sách theo `MINIRAG_PAPER_MODE` (6.000 khi bật) và đổi nhãn metric thành “Sources retention”. `compare_cpaper.py` dùng bản ghi `chunk_ids`/`sources_tok` trực tiếp nên không lệ thuộc nhãn đó.
