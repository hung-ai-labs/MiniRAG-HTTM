# C6/HYBRID_NO_GRAPH dev401 seed101 — 02/11/2026

Đăng ký DEV401-CTX-C6-001 theo HANDOFF §S-07/2W-10; đối chứng C1/B2_FULL.
**Đã có401 context thật hợp lệ; không cần gọi Qwen lại trên cùng đầu vào C5.**

## Kiểm chứng context

- 401 ID đúng dev, mọi status ok. Log đủ401 query/context hash, no_graph=true,
  keyword_parser=false, graph_ids=[], graph_seeds/paths=0; Sources<=4000.
- Không có keyword cache hoặc requests.jsonl của pha CPU C6. Fixture đã poison
  graph methods; đường C6 chạy trước parser/get_types và chỉ dùng vector/BM25.
- Vector/BM25/ranked/kept ID lists C6 khớp C1 đủ401 câu.
- **Sources C6=C1 từng byte:401/401. Toàn context C6=C5 từng byte:401/401.**
  Entities chỉ header rỗng, không entity data rows.
- Kết quả kiểm ở runs/2wiki/modal/c6-dev-s101-c4/context_comparison.json.

Với tập này C1 không early-exit, nên bỏ graph/keyword không thay Sources, còn
prompt chỉ khác C1 ở dữ liệu Entities. Không suy rộng rằng graph không có vai
trò trên mọi dataset/query: các ca graph early-exit ở tập khác chưa được đo.

## Tái dùng generation có kiểm chứng, không gọi GPU trùng

Đã so **messages C6 với request Qwen thực tế đã gửi ở C5**, không chỉ so tên
file: đủ401 messages giống từng byte nội dung; Qwen model/serving declaration,
seed101/max_tokens1024 và điều kiện manifest ngoài source khớp nhau. Bởi vậy
401 answer C5 được tái dùng trong thư mục C6, không là lượt sinh độc lập.

Artifact C6_s101:

- answers.jsonl/answers.csv: byte copy từ C5 sau kiểm điều kiện, không sinh lại.
- answer_manifest.json: cấu hình C6/context hash.
- generation_reuse.json: nguồn/hashes, new_qwen_calls=0, scope không phải repeat.
- generation_reuse_checks.jsonl:401 context/messages hashes, finish_reason gốc.
- evaluation_reference.json: tham chiếu judge C5 cho cùng question/gold/answer,
  không tạo run judge giả hoặc chấm lại để né strict parser.

Không copy C5 requests thành requests C6 như thể đã tiêu thêm compute. Giữ
nguyên hạn chế generation gốc:4 timeout attempts và1 answer chạm1024 token.
Tái dùng cùng outcome không được đếm thêm như một lượt sinh/quan sát độc lập.

## Trạng thái đánh giá: vẫn partial

C5 judge snapshot1200/1203 ok, một query lỗi định dạng/quota ở cả3pass. C6 dùng
cùng answers và tham chiếu cùng judgments nên **vẫn partial**, không tự complete.
Một query khác có no_majority được giữ đúng hợp đồng metrics. Không sửa parser,
đổi model/prompt/rubric hoặc gán nhãn cuối để ép đủ.

Bản phân tích tạm C1–C5 trên400 cặp trong
C5_JUDGE_INCOMPLETE_DIAGNOSIS.md cũng chỉ mô tả các outcome được tái dùng C6;
không phải xác nhận độc lập C6 hoặc benchmark401 hoàn chỉnh.

## Hiệu năng mô tả và giới hạn

| Retrieval CPU (giây/query) | C1, đợt trước | C6 |
|---|---:|---:|
| Trung vị | 1,51 | 0,03 |
| p95 nearest-rank | 10,42 | 0,04 |

Khác thời điểm/cache/CPU contention; chưa phải phép đo tốc độ có kiểm soát cùng
phiên. Timing trên không gồm phase keyword hay startup/load index. C6 bỏ bước
keyword theo thiết kế và thực thi không parser call; loader framework vẫn khởi
tạo storage chung, không chứng minh tiết kiệm toàn bộ RAM hoặc không đọc GraphML.
Không đưa tỷ lệ speedup hoặc tiền tiết kiệm cụ thể vào kết luận cuối từ bảng này.

## Bước tiếp theo của dự án

Đã có kết quả/pointer cho các ablation B2 yêu cầu (C2/C4/C5/C6), nhưng C5/C6
đánh giá còn partial và cần ghi trong bảng tổng hợp; không đánh dấu P4 hoàn tất
toàn bộ cổng. Không mở MR_MINUS_* khi V-01 chưa định nghĩa, không mở test1599.

Tiếp theo tổng hợp quality/efficiency/limitations và review với nhóm trước khi
chốt hướng điều chỉnh hoặc lên các lượt sinh202/303 trong ngân sách. Vấn đề
strict output của judge cần nhóm thống nhất nếu muốn thay hợp đồng; mọi thay
đổi phải version/áp dụng nhất quán, không ghép điểm khác protocol. Không chạy
thêm GPU/Gemini trong bước kiểm chứng và tái dùng này.
