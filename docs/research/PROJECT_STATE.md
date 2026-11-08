# Trạng thái benchmark 2WikiMultiHopQA

## C6 context hoàn tất; tái dùng C5 generation được kiểm chứng — 02/11/2026

- C6 đủ401 context ok, logs không parser/graph retrieval. Candidate/ranked/kept
  lists và Sources khớp C1 401/401; full context C6=C5 401/401.
- Messages C6 khớp401 Qwen requests gốc C5, cùng model/serving/seed101/QA1024.
  Tái dùng401 answer, new_qwen_calls0, không đếm là repeat độc lập. Nguồn/hashes
  ở C6_s101/generation_reuse.json và generation_reuse_checks.jsonl.
- Evaluation pointer dùng judge C5, vẫn partial1200/1203; không tạo judge run
  hoàn chỉnh giả hoặc thay strict parser. C5 lỗi một query giữ nguyên.
- Report C6_DEV401_CONTEXT_AND_REUSE_REVIEW.md; latency .03/.04s median/p95
  so C1 1.51/10.42s chỉ mô tả khác đợt. Chưa mở test1599/MR_MINUS_* hoặc chạy
  thêm GPU/Gemini. Cần tổng hợp/review trước điều chỉnh hoặc lặp lượt sinh.

## Đã triển khai C6/HYBRID_NO_GRAPH — 02/11/2026

- C6 mini/NO_GRAPH1: query gốc→vector+BM25→RRF→Sources4000, Entities header-only.
  Bỏ keyword parser/graph methods và graph early-exit, vẫn ghi retrieval log.
  Keyword phase skip, context không yêu cầu cache; default-off/xóa khi đổi config.
- Suite30 phased/acceleration tests đạt, thêm kiểm keyword skip và chạy lại nhóm
  C6; fixture poison graph, không LLM ở context, answer-only full QA, log và
  so C5 context. Chưa chạy401 context corpus thật, chưa kết luận hiệu quả.
- Entry run_c6_dev_contexts.py --execute chỉ CPU/offline embedding, output mới
  runs/2wiki/modal/c6-dev-s101-c4; amendment riêng, không sửa run/index cũ.
  Sau context kiểm Sources/C5 prompt để tránh generation trùng nếu byte-identical.
- C5 vẫn incomplete; không đổi parser hoặc gán nhãn cuối. Chưa GPU/judge C6
  hay mở test1599. Xem C6_HYBRID_NO_GRAPH_SETUP.md.

## C5 judge còn một query lỗi lặp — 02/11/2026

- Snapshot1200/1203 phiếu ok; ba phiếu lỗi cùng query8cc029e708c311ebbd8dac1f6bf848b6.
  Gemini trả giải thích thay một nhãn nên parse_failed lặp; quota làm phát sinh
  judge_failed. Resume nhiều lần chưa giải quyết được định dạng.
- Giữ strict parser/model/rubric/log; không tự lấy chữ cuối, không sửa nhãn hoặc
  đánh dấu complete. C5 vẫn incomplete; không khuyến nghị resume vô hạn.
- Có báo cáo tạm400 cặp đầy đủ, loại query incomplete rõ ràng theo metrics.py,
  không sửa split. Accuracy42 lên/40 xuống, p=0,912157; một no_majority giữ riêng.
  Xem C5_JUDGE_INCOMPLETE_DIAGNOSIS.md và
  runs/2wiki/analysis/c1-c5-dev-s101-fl35-v2-partial-1200. Chưa test1599.

## QA C5/B2_NO_ENT hoàn tất, có1 output chạm trần — 01/11/2026

- C5 đủ401 ID đúng dev, không rỗng, context_status ok401. Trace405 attempts:
  401 response Qwen/seed101,4 timeout; finish stop400/length1. Lưu
  runs/2wiki/modal/c5-dev-s101-c4/C5_s101/qa_verification.json.
- Giữ cap QA1024 và mọi answer nguyên trạng cho judge; không sinh lại chọn lọc
  hoặc đổi cap để cứu câu length. Chưa chấm C5; dùng output
  runs/2wiki/judge/c5-dev-s101-fl35-v2, cùng rubric/model/3 passes C1.
  Chưa mở test1599.

## Context C5/B2_NO_ENT đã kiểm đủ — 01/11/2026

- Người dùng derive C5 xong401/401; đã kiểm đủ401 ID, mọi Sources nguyên byte
  và hash trùng C1, bảng Entities chỉ CSV header không có data rows.
- Manifest ngoài source khớp C1; timing retrieval derive để null. Đăng ký
  DEV401-QA-C5-001 trước GPU. Output runs/2wiki/modal/c5-dev-s101-c4/C5_s101.
- Bước tiếp sinh401 answer C5, cùng Qwen/seed101/QA1024/concurrency4. Chưa
  sinh/chấm C5; đối chứng là C1. Usage hai tháng trước C5 khoảng19.22/25 USD,
  billed0; còn bill trễ/workload khác cần lưu ý. Chưa mở test1599.

## Chuẩn bị C5/B2_NO_ENT — 01/11/2026

- Theo handoff§S-07/2W-10: Entities chỉ còn CSV header, Sources C1 giữ từng byte.
  C5 mới, không phải −Redge hoặc HYBRID_NO_GRAPH. Giữ default off; xóa cờ khi
  chuyển cấu hình để không rò sang C1. Source extension dùng output/amendment mới.
- Đã có run_c5_dev_contexts.py --execute derive từ C1, không retrieval/embedding/
  LLM; lưu401 Sources hashes, timing retrieval null, không nhận là speedup.
- 28 tests phased/acceleration đạt; hai test C5 có kiểm derive khớp core đã
  chạy lại đạt. Chưa derive toàn dev thật hoặc GPU/judge C5/test1599. Xem
  C5_NO_ENTITIES_SETUP.md; người dùng chạy lệnh context tiếp theo.

## Judge C4/B2_NO_VECTOR hoàn tất — 01/11/2026

- Sau resume đủ1203 phiếu ok; mean accurate32,25±0,14 /error25,94±0,25 /
  neither41,81±0,29%. Majority130/104/167 so C1=147/101/153.
- C4 so C1:29 sai→đúng/46 đúng→sai, net−17, McNemar exact p=0,063950;
  query-bootstrap CI95 delta majority[-8,48;0,00] điểm. Xu hướng giảm chưa được
  xác nhận ở0,05; không kết luận tương đương hoặc vector vô ích. Một lượt sinh.
- Báo cáo C1_C4_DEV401_ABLATION_REVIEW.md; metrics
  runs/2wiki/analysis/c1-c4-dev-s101-fl35-v2. Theo handoff tiếp B2_NO_ENT cần
  triển khai/kiểm Sources nguyên byte C1; chưa chạy thêm GPU/test1599.

## QA C4/B2_NO_VECTOR hoàn tất — 01/11/2026

- Đã kiểm401 answer/401 ID duy nhất đúng dev, không thiếu/lạ/rỗng;
  context_status ok401. Trace401 request Qwen/Qwen2.5-3B-Instruct/stop/seed101,
  không lỗi hoặc length. Output runs/2wiki/modal/c4-dev-s101-c4/C4_s101.
- Judge C4 chưa khởi chạy tại lần kiểm tra này; hướng dẫn dùng output mới
  runs/2wiki/judge/c4-dev-s101-fl35-v2, model/rubric v2 và ba lượt như C1.
  Sau judge so C4 với C1/B2_FULL. Chưa mở test1599.

## Đã chuẩn bị C4/B2_NO_VECTOR — 01/11/2026

- Cập nhật: C4 đã có401 context ok; đã kiểm401 Entities và graph/vector/BM25
  candidate lists khớp C1, ranked C4=bm25_ids, Sources<=4000. Manifest ngoài
  source/cache khớp, source amendment đúng. Proxy655/996 title hits, đủ143 câu
  so C1=672/996/154; không suy accuracy. Đăng ký DEV401-QA-C4-001, bước tiếp
  người dùng chạy answer C4; chưa GPU/judge C4 ở lần kiểm tra này.

- C4=mini/bm25 Sources; giữ C3 naive. Theo handoff, đây là ablation tiếp so C1.
  Thêm nhánh mới, không chỉnh BM25/top-k/prompt hoặc mapping cũ. Source hash đổi:
  dùng output mới/source_amendment, không ghi lại manifest hay resume run cũ.
- 26 test phased/acceleration fake LLM/embedding đạt. Đã có entrypoint CPU
  run_c4_dev_contexts.py --execute, cache401 và identity guard. Context corpus
  thật đã hoàn tất và đối chiếu như cập nhật trên.
- Chưa GPU/judge C4 hoặc test1599. Xem C4_BM25_ONLY_SETUP.md.

## C2 ablation hoàn tất, so C1 chưa có chênh accuracy đáng tin — 01/11/2026

- C2 đủ401 answer và1203 phiếu judge ok sau resume, giữ cùng rubric/model/index.
  Mean accurate36,66±0,25 /error29,18±0,25 /neither34,16±0,00%.
- Majority C2=146/118/137, C1=147/101/153. C2 so C1:47 sai→đúng/48 đúng→sai,
  net−1, McNemar p=1; query-bootstrap CI95[-4,99;+4,24] điểm. Error tăng quan sát
  net17 nhưng p=0,145487. Không kết luận BM25 có ích/vô ích hoặc tương đương.
- Report C1_C2_DEV401_ABLATION_REVIEW.md; metrics
  runs/2wiki/analysis/c1-c2-dev-s101-fl35-v2. Chưa ước lượng nhiễu giữa lượt sinh.
  Bước ablation tiếp trong handoff là B2_NO_VECTOR (chưa triển khai), cần kiểm/
  đăng ký trước chạy, không nhầm với C3 naive. Chưa mở test1599.

## Context C2/B2_NO_BM25 hoàn tất — 01/11/2026

- Cập nhật QA C2:401/401 answer hợp lệ, ID khớp dev, không rỗng;401 response
  Qwen/stop/seed101, không request lỗi hoặc length. Chưa chấm C2 tại lần kiểm
  tra này; output judge dự kiến runs/2wiki/judge/c2-dev-s101-fl35-v2.

- Người dùng chạy entrypoint C2, đã kiểm401/401 context ok, ID đúng dev; manifest,
  cache, Entities và graph/vector candidate lists khớp C1. Ranked C2=vector_ids.
- Supporting-title proxy C2=628/996 (63,05%), đủ document130 câu; C1=672/996,
  đủ154. C1→C2:2 thiếu→đủ /26 đủ→thiếu. Không suy chất lượng answer từ proxy.
- Đăng ký DEV401-QA-C2-001 trước GPU. Bước tiếp người dùng sinh401 answer C2,
  cùng Qwen/seed101/QA1024/concurrency4; đã hoàn tất như cập nhật trên.
  Output runs/2wiki/modal/c2-dev-s101-c4/C2_s101. Không mở test1599.

## C1 judge hoàn tất; so C0 chưa có bằng chứng cải thiện — 01/11/2026

- C1 đủ1.203 phiếu ok; mean3 judge accurate36,66 /error25,27 /neither38,07%.
  Majority147 đúng/101 error/153 neither so C0=142/99/160.
- Ghép401 query_id:51 sai→đúng /46 đúng→sai, net+5, McNemar exact p=0,684859.
  Query-bootstrap CI95 delta majority[-3,49;+5,99] điểm. Không kết luận C1 tốt
  hơn hoặc tương đương. Đây chỉ seed101, ba judge không thay lượt sinh lặp.
- Báo cáo C0_C1_DEV401_QA_REVIEW.md; metrics/paired answers tại
  runs/2wiki/analysis/c0-c1-dev-s101-fl35-v2. Bước tiếp theo rà cặp lên/xuống,
  rồi ablation theo handoff nếu đăng ký/ngân sách cho phép; chưa mở test1599.

## Judge dev401 hoàn tất; kiểm tra retrieval C1 — 01/11/2026

- C1/B2 seed101 đã sinh đủ401/401 đáp án; ID khớp dev, không rỗng, context_status
  ok401. Trace401 Qwen response/stop, không request lỗi hoặc length. Pha answer
  exit0 sau641,02 giây, kết thúc05:52:19 UTC. Chưa khởi chạy judge C1 tại lần
  kiểm tra này. Output: runs/2wiki/analysis/c1-context-dev401-s101/C1_s101.

- Baseline C0 seed101 đã đủ 1.203 phiếu hợp lệ, ba lượt cho 401 câu dev.
  Mean judge: accurate35,33±0,29 / error25,02±0,29 / neither39,65±0,00 (%).
  Majority142 accurate /99 error /160 neither. Đây vẫn chỉ một lượt sinh.
- Đã rà 37 mẫu lỗi bằng agent, chưa phải human adjudication hoặc taxonomy nhân
  quả sáu giai đoạn hoàn chỉnh. Chi tiết: BASELINE_DEV401_FAILURE_REVIEW.md.
- Log của259 error/neither cho thấy200 câu thiếu supporting document ở Sources;
  67 câu có tài liệu thiếu nhưng vector candidate đã tìm được. Đây là proxy
  theo tài liệu, không chứng minh bằng chứng đủ để trả lời hoặc tăng accuracy.
- DEV401-CTX-C1-001 đã đăng ký trong EXPERIMENT_HISTORY.md trước khi chạy:
  tạo context C1/B2 vector_bm25 trên dev401 từ keyword seed101 sẵn có, một
  worker, embedding offline, không LLM/GPU. Run mới:
  runs/2wiki/analysis/c1-context-dev401-s101. Đã hoàn tất401/401 context ok.
  Manifest/cache khớp C0; Entities và candidate graph/vector khớp401/401.
  Supporting-title recall proxy60,34%→67,47%; đủ supporting document137→154,
  32 lên/15 xuống (proxy McNemar p=0,01862). Inference23→22, không tăng mọi nhóm.
  Đã sinh đủ C1 như cập nhật trên; chưa chấm, chưa có accuracy C1.
  Xem C1_DEV401_CONTEXT_REVIEW.md cho kết quả retrieval trước QA.
- Giữ nguyên index, baseline.yaml, answers/judge và protocol đăng ký QA cũ.
  Chưa mở test1599. Người dùng báo Modal hiển thị lại$30; chưa đối soát kỳ usage,
  không tự nâng trần thí nghiệm$25. Xem MODAL_BUDGET_2WIKI.md.

## Baseline dev401 QA hoàn tất — 01/11/2026

- BaselineC0/seed101/concurrency4/worker1 có401/401 answer, ID/gold khớp đúng
  internal_dev. Không answer rỗng, context/answer status đềuok.
- 802 response Qwen2.5-3B, finishstop; không request lỗi hoặc length trong trace.
- Plan chấm1203 phiếu bằng gemini-3.5-flash-lite/rubric2wiki-upstream-aliases-v2
  đã kiểm offline, output mới runs/2wiki/judge/baseline-dev-s101-fl35-v2.
  Chưa gọi judge trong bước review, chưa mở test1599. Cần Billing mới trước
  các lượt GPU tiếp theo; key Gemini do người dùng xác nhận các project khác nhau.

## Judge smoke20 V2 đạt — 01/11/2026

- Người dùng xác nhận keyGemini thuộc các project khác nhau. Giữ pool/limiter
  hiện có, không tự tăng RPM/TPM; quota/free-tier còn lại chưa được API xác minh.

- Đủ60 response gemini-3.5-flash-lite/stop, ba lượt cùng8 accurate/3 error/9
  neither.21 RateLimitError được retry; không incomplete/no_majority.
- Các trường hợp từ chối review trước đổi sangneither; giữ nguyên artifactV1.
  Không coi40% smoke là benchmark hoặc cải thiệnRAG. RubricV2 giữ cố định.
- Đã chuẩn bị plan baseline401dev C0/seed101/concurrency4/worker1 tại
  runs/2wiki/preparation/20261101/qa_dev401_plan.json, chưa gọi GPU trong review.
- Đang hỏi các key cùngproject hay khácproject để điều phối quota khi chấm
  1203 phiếu dev; không tự chỉnh limiter. Chưa mở test1599.

## Rubric đã đối chiếu tài liệu — 01/11/2026

- Theo câu hỏi người dùng, kiểm kế hoạch§B4, scriptgốc và protocolthamchiếu.
  Runner do Codex thêm "whole answer" ngoài promptgốc; đã khôi phục nguyên văn
  JUDGE_PROMPT chỉ appendaliases, version2wiki-upstream-aliases-v2/schema2.
- Không đổi modeljudge, index hoặc Qwenanswers; không ghi đè/sửa labelsmokeV1.
  Bước kế tiếp chấm lại60 phiếu cùng20 answer vào output mới*-fl35-v2.
- Chưa gọi inference V2 ở bước sửa. JUDGE_SMOKE20_REVIEW.md ghi căn cứ và giới hạn.

## Judge smoke20 hoàn tất — 01/11/2026

- Đủ60 phiếu, response model gemini-3.5-flash-lite;19 RateLimitError được retry.
- Majority7 accurate /7 error /6 neither; mean3 lượt acc35,00/err33,33/neither31,67.
  Một câu không đồng thuận. Không coi20 câu là benchmark toàn2000.
- Review có câu từ chối bị chấmerror và trường hợp kết luận đúng nhưng giải
  thích sai/không chắc. Chưa sửa nhãn/rubric hoặc chấm thêm. Đang hỏi người dùng
  chọn làm rõ rubric rồi rerun smoke, hoặc giữ V1 và ghi hạn chế.
- Chi tiết review (nhận định Codex, chưa là nhãn người độc lập):
  JUDGE_SMOKE20_REVIEW.md. Giữ nguyên mọi artifact V1.

## Smoke QA20 hoàn tất — 01/11/2026

- BaselineC0 seed101 đã có20/20 answers.jsonl, khớp20 ID/gold của smoke dev;
  mọi context/answer statusok, không answer rỗng.
- 40 response đềuQwen/Qwen2.5-3B-Instruct, finishstop, không request lỗi.
- Đã lập plan chấm60 phiếu bằng gemini-3.5-flash-lite, chưa gọi judge ở bước
  kiểm tra. Output dự kiến runs/2wiki/judge/baseline-smoke-s101-fl35.
- Smoke chỉ kiểm vận hành, không dùng20 câu làm accuracy toàn2.000 hoặc test.

## Kiểm tra key judge — 01/11/2026

- Người dùng điền8 keyGemini duy nhất; 7/8 trả200 khi đọc metadata của
  gemini-3.5-flash-lite. GEMINI_API_KEY_1 vẫnAPI_KEY_INVALID, đã comment trong
  .env (giữ giá trị để sửa/khôi phục), không đổi keyModal hoặc limiter.
- Không gọi inference; quota/project/free-tier billing chưa được xác minh.
  Số key không chứng minh quota vì quota theo project. Metadata report nằm ở
  runs/2wiki/preparation/20261101/gemini_keys_metadata.json.
- SmokeQA20 chưa có keyword/context/answer output tại thời điểm kiểm tra;
  cần chạy Qwen smoke trước khi chấm60 phiếu bằng Gemini.

## Judge model đã chọn — 01/11/2026

- Người dùng chốt gemini-3.5-flash-lite thay alias latest/yêu cầu Flash cũ.
  ID stable xác minh qua docs Google. CLI2Wiki pin đúng model này; không sửa
  judge của dataset khác hoặc baseline.yaml, không fallback sang model khác.
- Metadata check bằng key local trả400 API_KEY_INVALID. Chưa xác minh quyền
  project/quota, chưa gọi inference. Cần key Gemini AI Studio hợp lệ.
- Giữ nguyên registration RUN_2WIKI_DEV20_TEST80.md để tránh thay hash khi QA
  chuyển pha. Hướng dẫn chấm mới: JUDGE_2WIKI_3_5_FLASH_LITE.md.

## Index hoàn tất, chuẩn bị QA — 01/11/2026

- Manifest completed, 6/6 verification đạt: 11.657 docs, 11.661 chunks,
  58.193 node, 38.166 cạnh.418 chunk không được graph cite (3,58%), text/vector
  vẫn đủ; chưa kết luận nguyên nhân từng chunk hoặc chất lượng retrieval.
- Verify checksum nguồn và bản sao dữ liệu độc lập ở
  runs/2wiki/backups/index-final-20261101 đạt,401.740.560 byte. Đây là backup
  cục bộ data+manifest, chưa phải off-device hoặc backup toàn trace.
- Trace toàn index: 24.213 attempts,24.135 response OK đều Qwen;129 length.
  65 cancellation,9 timeout,2 connection error,2 server error. Có redo khi resume;
  số attempt không phải số prompt duy nhất hoặc số đoạn có lỗi.
- Ảnh Billing Total17,74 USD; còn7,26 so trần25, chưa tính usage/bill trễ sau ảnh.
- Đã chuẩn bị smoke20 chỉ từ dev và gold/aliases khớp20 ID, plan baselineC0
  seed101 concurrency4/worker1. Chưa chạy QA/Gemini trong lượt chuẩn bị này.
- Handoff: runs/2wiki/preparation/20261101/index_handoff.json; QA chỉ dùng
  snapshot từ index hoàn tất, không gọi index_run --resume nữa.

## Đối soát mốc16 USD — checkpoint10.496, 31/10/2026

- Ảnh resource Total16,14 USD (Deployed apps16,13), còn8,86 trong trần25.
- Checkpoint/progress cùng10.496, không torn progress, không có tiến trình
  index đang chạy khi review. Còn1161 đoạn, ~80,6 phút theo lượt cuối864/giờ.
- Theo hai ảnh13,48→16,14 cho8736→10496 đoạn, phần cuối ngoại suy~1,75 USD;
  tổng đến index xong~17,89, còn~7,11 cho QA/dự phòng, không bảo đảm.
- Đề xuất một lượt resume tối đa90 phút (5400 giây), giữ source/cap/model.
  Mốc16 là ngưỡng đối soát, không thay trần25. Không tự gọi GPU trong review.
- Nếu hoàn tất, chỉ dùng QA khi status completed và mọi verification đạt;
  đo smoke QA nhỏ trước khi cấp toàn bộ ngân sách còn lại.

## Checkpoint/Billing mới nhất — 31/10/2026, 14:49 giờ Việt Nam

- Checkpoint5.344/11.657 đoạn (45,84%); progress unique docs khớp5344, không có
  dòng lỗi/torn cuối progress. Không còn tiến trình index khi review.
- Resume từ4480, tăng864 đoạn/60 phút; còn6313, ngoại suy~7,31 giờ nếu giữ tốc
  độ lượt này. Trace1792 response thành công, 1780 stop/12 length, không request
  lỗi. Các response của lô chưa progress không được tính thành checkpoint.
- Ảnh resource Total8,63 USD (Deployed apps8,62). Còn16,37 USD trong25;
  nếu giữ8 cho QA/dự phòng thì index còn8,37. Giữ mốc16 để đối soát.
- Có thể tiếp tục một lượt60 phút cùng --resume và kiểm Billing sau lượt;
  chưa gọi cloud/sửa index trong review. Không dùng partial index để QA chính thức.

## Checkpoint/Billing mới nhất — 31/10/2026, 11:49 giờ Việt Nam

- Đã checkpoint3.136/11.657 đoạn (26,90%), tăng960 trong lượt60 phút; còn8.521,
  ngoại suy16 đoạn/phút ~8,88 giờ. Lượt mới1.959 attempts: 1.943 responseOK
  (1.932 stop, 11 length), 16 CancelledError ở deadline; không lỗi mạng khác.
- Ảnh resource Total5,46 USD, Deployed apps5,45; dùng Total. Tăng1,25 USD cho
  960 đoạn so ảnh4,21: quan sát~1,30 USD/1000 đoạn, trước đó~1,65 USD/1000.
  Không phải so sánh cùng tải/coldstart; bill có thể cập nhật trễ.
- Còn19,54 USD trong25. Nếu mức tăng cuối giữ nguyên: index còn~11,10 USD,
  tổng index/đã chi~16,56; cộng8 dự phòngQA~24,56, sát trần và chưa bảo đảm.
- Có thể tiếp tục từng lượt60 phút cùng --resume; giữ mốc đối soát16 USD,
  không tự chạy thêm cloud trong review, không sửa index/cap/source.

## Checkpoint/Billing mới nhất — 31/10/2026, 10:38 giờ Việt Nam

- Đã checkpoint2.176/11.657 đoạn (18,67%), tăng480; còn9.481 đoạn (~9,88 giờ
  nếu giữ16 đoạn/phút). Lượt mới1.024 attempts: 1.021 response OK (1.018 stop,
  3 length), 3 CancelledError ở deadline; không lỗi mạng khác.
- Ảnh Billing Total4,21 USD (Deployed apps4,20 là dòng riêng, dùng Total).
  Tăng0,79 USD so ảnh3,42; còn20,79 USD so trần25, index còn12,79 nếu giữ8 cho QA.
- Ngoại suy thô0,79 USD/480 đoạn cho phần còn lại ~15,60 USD, tổng~19,81 trước
  QA; không phải báo giá vì bill trễ/cold start và đoạn dài khác nhau. Ngân sách
  giữ8 USD cho QA không còn chắc chắn theo ngoại suy này.
- Đề xuất đổi lượt tới thành60 phút (3600 giây) để giảm startup/giữ ấm/lô bị làm
  lại; chưa được thực thi ở bước review. Không thay model/cap/corpus/source.
  Bắt dừng30 phút liên tục là cách đo ban đầu, không phải tối ưu chi phí dài hạn.

## Checkpoint/Billing mới nhất — 31/10/2026, 00:07 giờ Việt Nam

- Đã checkpoint1.696/11.657 đoạn (14,55%), tăng448 trong lượt30 phút mới nhất.
  Còn9.961 đoạn, tốc độ~14,93 đoạn/phút, ngoại suy~11,12 giờ, chưa bảo đảm.
- Trace960 attempts: 959 response OK (950 stop, 9 length), 1 CancelledError
  ở deadline. Ghi nhận clipping, không tự đổi cap/prompt trong cùng index.
- Ảnh Billing mới Total3,42 USD (GPU3,24 / CPU0,12 / Memory0,06). Còn21,58 USD
  so trần25; giữ8 USD cho QA/dự phòng thì index còn13,58 USD. Billing từ ảnh,
  chưa xác minh độ trễ cập nhật hoặc coi là hard cap.
- Có thể tiếp tục lượt30 phút cùng --resume; kiểm Usage sau khoảng1 giờ thêm
  và đối soát khi tổng tiến gần16 USD. Không gọi cloud trong bước review này.

## Checkpoint mới nhất — 30/10/2026, 23:34 giờ Việt Nam

- Đã checkpoint1.248/11.657 đoạn (10,71%), tăng480 trong lượt30 phút thứ ba.
  Còn10.409 đoạn, ngoại suy ở16 đoạn/phút ~10,84 giờ, không phải bảo đảm.
- Trace lượt mới1.023 attempts: 1.020 response thành công (1.018 stop, 2 length),
  3 CancelledError ở deadline; không có lỗi mạng khác trong lượt này.
- Chưa nhận Billing mới sau ảnh Total2,13 USD. Giữ trần25 USD, khoảng8 USD
  cho QA/dự phòng; không tự tăng thời lượng hoặc chạy tiếp cloud ở bước review.

## Billing cập nhật từ ảnh — 30/10/2026

- Dashboard Total2,13 USD; còn22,87 USD so trần25 USD. Giữ8 USD cho QA/dự phòng,
  index còn khoảng14,87 USD. Chưa xác minh độ trễ billing qua API.
- Có thể tiếp tục resume batch32/async16 theo lượt30 phút, giữ index768 đoạn.
  Kiểm Usage sau khoảng1 giờ thêm và dừng đối soát trước mốc tổng16 USD.
  Không có hard monetary cap trong runner; chưa gọi cloud ở bước cập nhật này.

## Full index hiện tại — 30/10/2026, sau lượt resume đầu

- Checkpoint768/11.657 đoạn (6,59%), tăng480 trong lượt30 phút batch32/async16.
- 9 timeout đều retry thành công; 1 request hủy ở deadline; có2 output length.
- Tốc độ events~16,13 đoạn/phút, ngoại suy còn~11,25 giờ; chưa phải bảo đảm.
- Review offline xong, chưa chạy tiếp cloud; cần Billing tích lũy mới để quản lý
  trần25 USD và tiền dành cho QA. MODAL_INDEX_30MIN_REVIEW.md ghi chi tiết.

## Ngân sách đã chốt — 30/10/2026

- Hai benchmark batch32/async16 trên cùng32 đoạn đã hoàn tất: 187,87 giây và
  111,54 giây khi GPU còn ấm; mỗi lượt64/64 response thành công, 6 kiểm toàn vẹn
  đạt. Lượt warm có2 length. Index chính giữ nguyên288 đoạn.
- Ngoại suy tốc độ warm17,21 đoạn/phút: còn ~11,01 giờ, riêng GPU ~12,13 USD;
  không bảo đảm hoặc báo giá trọn gói. Đề xuất lượt30 phút tiếp theo dùng
  batch32/async16, chừa khoảng8 USD cho QA/dự phòng và kiểm Billing sau lượt.

- Người dùng cho phép tổng khoảng 25 USD, đã dùng khoảng 1,5 USD (số tự báo).
  Còn khoảng 23,5 USD cho index, QA và chẩn đoán; chưa có billing breakdown.
- GPU A10 công khai khoảng 1,10 USD/giờ chưa CPU/RAM; ngoại suy index ở tốc độ
  hiện tại gần dùng hết ngân sách trước QA. Chưa tự resume index chính.
- Đang đo batch32/async16 tối đa 300 giây trên đúng 32 đoạn đã checkpoint,
  index phụ riêng; không đổi corpus/cap/model hoặc index chính. Kế hoạch:
  MODAL_BUDGET_2WIKI.md.

## Full index đợt đầu 30 phút — 30/10/2026

- Đã dừng đúng time_limit, checkpoint 288/11.657 đoạn (18 lô × 16, 2,47%).
- 608 attempts: 607 response Qwen thành công, 1 CancelledError khi hết giờ;
  có 1 glean output chạm cap4.096 thuộc chunk đã lưu. Chưa chỉnh cap/prompt.
- Tốc độ sơ bộ 9,6 đoạn/phút; ngoại suy còn 19,74 giờ, không phải bảo đảm hoặc
  ước lượng tiền. Cần billing thực tế/ngân sách tổng trước khi resume tiếp.
- Review: MODAL_INDEX_30MIN_REVIEW.md. Index partial được giữ nguyên, chưa QA.
- Các dòng "full index chưa chạy" bên dưới là snapshot trước đợt này.

## Modal pilot đã chạy — 30/10/2026

- Pilot batch16/async8 trên cùng 20 đoạn: 165,08 giây, 168 node/66 cạnh, 40/40
  request thành công, không length. So lượt batch4/async4 là nhanh hơn 43,7%
  trong hai lần đo; chưa phải benchmark kiểm soát hoặc số đo tiền GPU.
- Người dùng đã chọn đợt full index đầu giới hạn 30 phút. Đã thêm
  --max-runtime-seconds 1800, dừng partial/time_limit có thể resume; 14 test
  index/time-limit đạt. Full index chưa chạy trong bước chuẩn bị này.
- modal_slm.py local đã pin snapshot revision và dtype; người dùng cần redeploy
  trước full index mới. Hướng dẫn lệnh: RUN_2WIKI_DEV20_TEST80.md §3.

- Endpoint smoke đạt 3/3: Qwen2.5-3B, vLLM 0.11.0, trả `ok`.
- Pilot Modal index 20 đoạn hoàn tất: 20 chunk, 145 node/67 cạnh, 6 kiểm toàn vẹn
  đạt; 40/40 request thành công, 0 output length, dài nhất 2.111/4.096 token.
- Wall index 293,32 giây; chưa đo chi phí billing, chưa full index hay QA 2Wiki.
  Chunk không có nguồn graph là đoạn disambiguation cực ngắn, không mất chunk.
- Báo cáo: MODAL_PILOT20_REVIEW.md. Bước kế tiếp là kiểm throughput batch16/async8
  trên cùng 20 đoạn ở index mới, trước khi quyết định chạy toàn corpus 11.657 đoạn.
- Những dòng "chưa gọi Modal/chưa có endpoint" bên dưới là snapshot trước pilot.

## Chuẩn bị theo yêu cầu người dùng — 30/10/2026

- Đã port có chọn lọc acceleration từ `codex/mhr-phase3-acceleration` tại ae52921
  sang `reproduce/research/two_wiki_acceleration/`: truy hồi chung C0/C1 và consumer
  Gemini chạy gối giữa seed, đúng split 2Wiki và rubric nhận aliases. Không merge
  corpus/kết quả hoặc toàn bộ lịch sử nhánh MHR. Hướng dẫn/provenance:
  PORT_2WIKI_ACCELERATION.md. Cần validation 802 context dev thật trước thực thi;
  hiện chưa có index Modal để thực hiện cổng này. Chưa gọi GPU/Gemini.
  Toàn bộ tests/research sau tích hợp: **103 passed**, offline, 23,10 giây;
  entry point pipeline mặc định chỉ in plan đã kiểm thành công.

- Đã thay phương án split 80% dev / 20% test bên dưới bằng **20% phân tích lỗi /
  80% đánh giá** theo cuộc trao đổi mới: **401 internal_dev / 1.599 internal_test**.
  Giữ nguyên pool 2.000 câu, seed 13; không có title gold chung giữa hai tập.
  Split cũ chỉ là đề xuất; các snapshot lịch sử bên dưới không phải trạng thái mới.
- Đã ghi split vào ignored processed/splits/n2000_s13_dev20_test80; checksum tái
  tính đạt. Báo cáo public: env/2wiki_split_dev20_test80_seed13.json. Có smoke20
  chỉ lấy từ dev; chưa mở kết quả test để tinh chỉnh.
- Thêm freeze_2wiki_split.py và judge_2wiki.py: judge ghép theo query_id,
  nhận aliases, ba lượt chấm, trace thô và checkpoint, mặc định chỉ lập kế hoạch.
  Sáu test mới offline đạt; chưa kiểm chất lượng rubric bằng Gemini thật.
- Modal CLI 1.6.2 có sẵn và có file đăng nhập local; chưa xác minh tài khoản/credit.
  Kiểm cấu hình ngày 30/10: chưa có MINIRAG_SLM_URL/KEY hoặc các biến key Gemini
  chính trong env/.env. Chưa deploy, gọi GPU hoặc Gemini trong đợt chuẩn bị này.
- Còn cần endpoint/key riêng, model revision/serving được xác minh, ngân sách
  pilot, Gemini model ID/free-tier quota và smoke thực tế. Không coi là benchmark
  đã chạy. Hướng dẫn từng bước: RUN_2WIKI_DEV20_TEST80.md.

## Cập nhật tích hợp 29/10/2026

- Nhánh thử tích hợp `research/2wiki-shared-gpu` ghép nền 2Wiki `0d7a18c` với PR #1 tại `77ae1af`; không xung đột, **78 test offline đạt trên Python 3.13.5**.
- PR chung vẫn Draft/chưa merge tại thời điểm kiểm tra. Nhánh `research/2wiki-qwen` gốc giữ nguyên; không cập nhật `dev`/`main`.
- Chưa chạy Modal/Gemini. Đã bổ sung bản sửa guard endpoint khi resume index, khóa ghi index và trace request đầy đủ trên nhánh tích hợp; **86 test offline đạt** sau sửa, cần nhóm review trước dùng chung. Xem [báo cáo review](SHARED_GPU_INTEGRATION_REVIEW.md).
- Pilot/index local giữ nguyên; resume pilot cũ phải giữ source đã pin, không sửa manifest để vượt kiểm tra hash.

## Snapshot trước tích hợp

Cập nhật 26/10/2026. Nhánh `research/2wiki-qwen`, commit nền `9c59062a9cfaaab47b4e8b303829ce0d00624e91`.
Handoff/kế hoạch gốc: `c45ac1f458e07c7d750404043048ae2dc0e2a2bc`; protocol tham chiếu MultiHop: `790e0171a9e4e7c542aabc41993f48a37bff41ca`.

## Đã kiểm chứng offline

- Python client 3.13.5; import và embedding local 384 chiều đã được người chạy kiểm.
- Archive 2Wiki đúng checksum, đã giải nén. Chỉ dùng dev chính thức có nhãn; test chính thức có answer rỗng.
- `prepare_2wiki.py`: 12.576 câu, 54.957 đoạn ứng viên; mọi output có checksum và tái tính byte bằng `--check` thành công.
- 463 câu có title lặp, 523 lượt lặp nội dung giống nhau; giữ câu hỏi, gộp tài liệu.
- 70 supporting fact có sentence index ngoài đoạn: giữ nhãn gốc và đánh dấu mapping thiếu, không đoán hoặc loại câu.
- Đã đo pool 200/500/1.000/2.000 với seed 13 và thiết kế split ứng viên theo thành phần title gold.
- Audit Jaccard char 5-gram >= 0,85 trên câu hỏi và thân đoạn gold: 0 cặp ở cả bốn pool. Chưa bao phủ paraphrase ngữ nghĩa hoặc gần trùng mọi distractor.
- `tests/research/test_2wiki_preparation.py`: 7 passed; kiểm dữ liệu đầy đủ, checksum, ID/gold separation và không xuất nội dung test trong audit.
- `metrics.py` đã triển khai cho CSV judge chung: chuyển sang từng query × lượt sinh × lượt chấm, kiểm majority, ba nhãn và lỗi, bảng loại câu, McNemar chính xác, bootstrap theo query giữ các lượt sinh. 17 test metrics và 7 test dữ liệu đạt (24 tổng); dữ liệu metrics hoàn toàn giả.
- `.gitignore` bao phủ runs, indexes, processed và .venv; bộ bốn file trạng thái có sẵn, chờ người còn lại review S-02.

## Local đã chạy theo yêu cầu mới

- Ollama native 0.40.10 + Qwen2.5-3B-Instruct GGUF Q4_K_M có sẵn; không tải model hoặc gọi cloud.
- Smoke context 32.768, 100% GPU RTX 4050, khoảng 3,37 GB VRAM; model digest được khóa.
- Canary hai tài liệu giả: 2 chunk, 3 node, 2 cạnh; 6 request local gồm 2 extract/2 glean/1 parser/1 answer, không lỗi hoặc chạm trần. Answer có đúng Riverton của fixture.
- Giữ artifact canary lỗi SSLContext và canary đã sửa; chỉ sửa wrapper, không sửa minirag core. Không coi canary là benchmark 2Wiki.
- Sau chạy model được unload, GPU 0 MiB; Ollama nền vẫn ở loopback. Cấu hình tại `configs/research/2wiki/local_qwen.json`.
- 9 kiểm thử adapter local đạt, tổng `tests/research` là 33 passed. Chi tiết `LOCAL_QWEN_STATUS.md`.

## Chưa khóa hoặc chạy

- Người dùng đã gửi tin nhắn nhóm chọn pool 2.000 câu từ dev chính thức. Đã materialize corpus `2wiki-n2000-s13-4267adcf3ef6`: 11.657 đoạn, 11.661 chunk đã đo, 23.322 call index tĩnh trước retry/cache.
- Danh sách pilot 200 đoạn được chọn bằng seed 13 từ corpus, không chọn theo gold relevance. Đã chạy lô đầu 10/200 đoạn thật: 20 request local thành công, 77 node/32 cạnh, 7 kiểm toàn vẹn đạt. Checkpoint bất biến docs-0010 đã lưu. Toàn bộ ID/gold nằm trong processed/pools/n2000_seed13/ được ignore; public report chỉ có counts/hashes.
- Split 80/20 vẫn là ứng viên (1.599 dev / 401 test), chưa khóa split hoặc xuất câu internal_test. Chưa index toàn corpus hoặc sinh/chấm answer benchmark 2Wiki. Đề xuất N=500 trước đó đã được thay bằng lựa chọn N=2.000 của nhóm.
- Lô10 có 1/20 output chạm cap4096 và nhiều segment lặp; raw đã lưu, chưa đổi cap/prompt/stop. Dự toán sơ bộ pilot200 khoảng 61 phút, toàn corpus khoảng 59,6 giờ local. Báo cáo `LOCAL_PILOT_STAGE10.md`; không coi mốc10 là pilot hoàn tất.
- Bộ offline hiện 38 passed (thêm 5 test runner checkpoint/path/verify/stats). Runner resume từ chối torn write, giữ index và snapshot; recovery sang thư mục mới chưa tự động hóa.
- Chưa triển khai đầy đủ fixture chung S-08, kiểm chéo S-09 và ba ablation B2. Metrics judge có sẵn; Evidence Recall, latency/tokens và số early-exit/infra của generation còn chờ schema logger, hiện ghi null chứ không suy đoán. Không coi 24 test offline là hoàn tất các cổng chung.
- Chưa tích hợp code chung từ nhánh MultiHop hoặc sửa mặc định MiniRAG.

## Cần nhận/chốt trước pilot

- PDF đúng phiên bản/hash và nguồn dựng corpus paper; hiện chỉ gọi thiết kế 2Wiki là chuyển đổi benchmark của nhóm.
- Protocol review hai phía, rubric nhận aliases, schema log đầy đủ và runner tham số hóa 2Wiki.
- Giữ Gemini Flash theo yêu cầu; exact model ID/project/quota chưa xác minh, chưa gọi API.
- Local Q4_K_M có digest/sampling/endpoint đã xác minh bằng smoke; khác điều kiện Modal bf16 và không có HF revision được chứng minh tương đương. Nhóm cần review điều kiện local cho mọi nhánh 2Wiki. Output index 4096, QA 1024 đã thử fixture, cần pilot 2Wiki thật.
- Client giữ Python 3.13.5; server local là Ollama native, không cần Python 3.12 hoặc vLLM trên Windows.
- N=2.000 đã chọn; còn tỷ lệ split, mức chênh loại câu chấp nhận, backup chung, ngân sách/tải máy và trần pilot.

## Giới hạn môi trường

- Không cài graspologic do tương thích Python 3.13; runner sử dụng phải được kiểm trên fixture.
- pip freeze lỗi mã hóa đường dẫn Git worktree; lưu pip list --format=freeze và metadata editable riêng trong env/.
- `baseline.yaml` và các index LiHua giữ nguyên.

## Nơi lưu và báo cáo

- `docs/research/PREPARATION_REVIEW_2WIKI.md`: kết quả tổng hợp, giới hạn và cổng pilot.
- `docs/research/env/`: bản ghi môi trường và ba báo cáo pool/split/gần trùng.
- `dataset/2WikiMultiHopQA/processed/`: năm file chuẩn hóa; gitignored, chưa backup chung.
- Chưa có run benchmark QA/metrics. Có technical runs và pilot stage10 dữ liệu thật trong `runs/2wiki/local/`, index pilot `indexes/2wiki-local-q4km-pilot200-n2000-s13/` và index fixture `indexes/2wiki-local-q4km-synthetic-canary02/`. Backup chung chưa được kiểm chứng; checkpoint local không thay backup ngoài máy.
