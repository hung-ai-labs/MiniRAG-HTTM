# Lịch sử chuẩn bị và thí nghiệm

## DEV401-CTX-C6-001 — HYBRID_NO_GRAPH, đăng ký 02/11/2026

- Theo HANDOFF§S-07/2W-10, ablation độc lập tiếp so C1/B2_FULL. C5 vẫn incomplete
  ở một query, không đánh dấu đã hoàn tất hoặc sửa parser để tiến hành phần này.
- C6 mới: MINIRAG_NO_GRAPH=1, mini/rag_response; original-query vector top30 +
  BM25 top30 trộn RRF k60, Sources4000; Entities chỉ CSV header. Không gọi
  parser/get_types/graph/entity/relationship retrieval, không early-exit theo
  graph rỗng. Không sửa tokenizer/BM25/embedding/Qwen/index/prompt/top-k.
- Nhánh C6 chạy trước parser, vẫn ghi context log vector/BM25/ranked/kept IDs,
  hash/tokens/timing và no_graph=true/keyword_parser=false. C6 không yêu cầu
  hoặc đọc keyword cache; phase keywords explicit sẽ skip không gọi model.
- Dùng output mới runs/2wiki/modal/c6-dev-s101-c4/C6_s101, dev401 seed101;
  run_c6_dev_contexts.py --execute chỉ CPU/local embedding/offline, cấm LLM.
- Source extension ghi amendment riêng, manifest ngoài source phải khớp C1;
  không sửa metadata/run cũ. Chưa chạy GPU/judge/test1599, chưa đổi tiêu chí C5.
- Fixture cần poison graph methods/forbidden keyword, đúng hybrid ranking/
  Sources, log retrieval và phased-vs-direct; kiểm flag không rò cấu hình cũ.
  Loader hiện vẫn khởi tạo storage chung, không tuyên bố không load GraphML hay
  đo memory saving; phép đo retrieval không phải tổng startup/index-loading.
- Sau CPU: đối chiếu Sources với C1 và full context/prompt với C5. Nếu giống
  hoàn toàn thì chỉ ghi khả năng tái dùng generation để tránh gọi GPU trùng,
  chưa tự copy answer/verdict hoặc gọi đó là một lượt sinh độc lập.
- Trạng thái đăng ký: đang kiểm thử, chưa chạy context401 thật. C5 vẫn partial.
- Suite phased/acceleration đã đạt30 tests fake LLM/embedding; bổ sung test C6
  phase keywords skip và chạy lại nhóm C6. Có poison graph methods, không LLM
  trong context, full QA chỉ answer call, context/Sources khớp C5 trong fixture,
  ghi log và flag không rò C1. Chưa kiểm401 context thật; setup
  C6_HYBRID_NO_GRAPH_SETUP.md, entrypoint chỉ CPU đã chuẩn bị.
- Người dùng chạy C6 context xong401/401 ok. Kiểm đủ401 logs no_graph/khôngparser,
  graph seeds/paths0; vector/BM25/ranked/kept lists và Sources byte khớp C1.
  Full context C6=C5 ở401 câu. Không đọc keyword cache, không có request phase CPU.
- Đã kiểm401 messages C6 khớp Qwen request thực tế C5, cùng model/serving/seed101/
  QA1024; tái dùng401 C5 answers với generation_reuse manifest/proof hashes,
  new_qwen_calls0. Không copy request log thành compute mới, không đếm là repeat
  độc lập. Judge dùng pointer C5, vẫn partial1200/1203, không sửa parser/nhãn.
  Report C6_DEV401_CONTEXT_AND_REUSE_REVIEW.md. Retrieval median/p95 C6=.03/.04s
  so C1=1.51/10.42s chỉ mô tả khác đợt, chưa speedup có kiểm soát. Chưa GPU/test.

## DEV401-CTX-C5-001 — B2_NO_ENT, đăng ký 01/11/2026

- Theo HANDOFF§S-07/2W-10: B2_NO_ENT so C1/B2_FULL, giữ Sources nguyên từng byte,
  bảng Entities chỉ còn CSV header (không có entity rows). Không phải −Redge
  hoặc HYBRID_NO_GRAPH; giữ điều kiện early-exit và kết quả retrieval của C1.
- C5 mới: mini/vector_bm25 + MINIRAG_DROP_ENTITIES=1. Cờ mặc định tắt, apply_env
  xóa cờ khi chuyển về cấu hình cũ để tránh rò trạng thái; không sửa prompt,
  tokenizer, embedding, top-k, BM25/RRF hoặc Sources4000.
- Để không tính lại đồ thị, derive context từ401 C1 đã đo: thay phần Entities
  bằng header rỗng, kiểm và lưu SHA256 Sources C1/C5 từng query. Không gọi
  keyword/retrieval/embedding/LLM; retrieval_s/ms của bản derive là null, không
  coi thời gian copy context là speedup retrieval.
- Output mới runs/2wiki/modal/c5-dev-s101-c4/C5_s101; entrypoint
  run_c5_dev_contexts.py --execute. Dùng cùng401 dev/seed101/cache/index;
  manifest ngoài source phải khớp C1, source amendment/hash generator ghi riêng.
  Không sửa hoặc resume metadata cũ bằng source mới.
- Trước chạy: fixture so context derive với đường MiniRAG C5, Sources C1/C5
  byte-identical, empty entity rows, chuyển C5→C1 phục hồi context, hồi quy cũ.
- Sau context: kiểm401 Source hashes trước GPU answer/judge. Chưa chạy QA/judge,
  chưa mở test1599; người khác review S-07 còn cần theo handoff, không tự chứng
  nhận toàn protocol bằng test fixture. Trạng thái: đang chuẩn bị/kiểm thử.
- Kiểm thử đã đạt28 phased/acceleration với LLM/embedding giả. Sau bổ sung
  đối chiếu derive-context, chạy lại hai test C5 đều đạt; Sources nguyên byte,
  derive khớp core C5, cờ không rò C1. Chuẩn bị cache/identity, chưa derive corpus
  thật hoặc sinh/chấm C5. Hướng dẫn C5_NO_ENTITIES_SETUP.md.
- Người dùng đã derive401/401 C5 context ok; kiểm độc lập đủ401 ID, Sources
  byte-identical và SHA256 trùng C1 ở401 câu,401 bảng Entities không có data rows.
  Manifest ngoài source khớp C1. Chưa answer/judge C5 ở lần kiểm tra này.

## DEV401-QA-C5-001 — B2_NO_ENT answer/judge, đăng ký 01/11/2026

- Giữ401 Sources nguyên byte C1 đã kiểm, chỉ Entities header-only theo S-07.
  Dùng phased_qa answers configC5, Qwen/seed101/QA1024/concurrency4, cùng index,
  embedding/serving/prompt; không chạy lại context/retrieval/index.
- Output runs/2wiki/modal/c5-dev-s101-c4/C5_s101. Judge dự kiến
  runs/2wiki/judge/c5-dev-s101-fl35-v2, gemini-3.5-flash-lite/rubric v2, ba lượt,
  limiter/free-tier không đổi. Kiểm ID/answer/trace trước chấm.
- Đối chứng C1/B2_FULL, không phải C4. Báo accurate/error/neither, b/c/McNemar
  exact và bootstrap query; không kết luận graph/−Redge hoặc tương đương từ
  một seed. Không thay weights/top-k/prompt theo kết quả, chưa mở test1599.
- Billing trước hướng dẫn GPU: tháng11 metered0.85000258 USD/billed0;
  cộng tháng10 đã đối soát18.36875559 thành khoảng19.22 USD, còn khoảng5.78
  trong trần25 trước C5, chưa tính bill trễ/workload khác. Người dùng tự chạy
  lệnh answer tiếp theo; chưa GPU/judge C5 tại thời điểm đăng ký.
- QA C5 đã hoàn tất401/401 ID đúng dev, không rỗng, context_status ok401.
  Trace405 attempts:401 success Qwen/seed101,4 APITimeoutError đã có đủ answer;
  finish stop400/length1. Giữ nguyên câu chạm trần QA1024 để chấm, không chọn
  sinh lại hoặc tăng cap riêng C5; không tự gán length thành neither. Chi tiết
  query_id/token/hash ở C5_s101/qa_verification.json. Judge chưa khởi chạy ở lần
  kiểm tra này; dùng model/rubric/3 passes đã đăng ký.
- Chẩn đoán02/11 sau nhiều resume:1200/1203 phiếu ok; một query
  8cc029e708c311ebbd8dac1f6bf848b6 còn lỗi cả3pass (latest1 parse_failed,
  2 judge_failed). Gemini lặp giải thích dài, đôi lúc length; thêm quota.
  Giữ strict parser theo PROTOCOL_MHR_REVIEW dòng40, không lấy nhãn cuối/đổi
  protocol để ép hoàn tất. Run vẫn incomplete. Snapshot metrics tạm400 cặp
  đủ phiếu:42 lên/40 xuống, p=0,912157; excluded1 ghi rõ. Có1 no_majority khác
  giữ riêng. Artifact c1-c5-dev-s101-fl35-v2-partial-1200; report
  C5_JUDGE_INCOMPLETE_DIAGNOSIS.md. Không API/GPU/nhãn chỉnh tay trong chẩn đoán.

## DEV401-CTX-C4-001 — B2_NO_VECTOR, đăng ký 01/11/2026

- Theo HANDOFF§2W-10: sau B2_NO_BM25, kiểm B2_NO_VECTOR đối chứng B2_FULL/C1.
- ID C4 mới (C3 giữ nguyên naive). C4=mini + MINIRAG_CHUNK_FUSION=bm25:
  dùng BM25 top30 gốc thay RRF(vector top30,BM25 top30) cho Sources. Giữ Entities,
  parser/graph phía trước, early exits, Sources4000, seed101 và embedding384d.
  Vector candidate vẫn được tính ở đường chung để giữ điều kiện; không dùng nó
  xếp Sources. Đây không phải HYBRID_NO_GRAPH và chưa chứng minh speedup.
- Thêm nhánh bm25 ở operate.py và mapping C4 ở phased_qa.py; không chỉnh BM25
  tokenizer/k1/b/stopwords, top-k, prompt, weight hoặc các nhánh fusion cũ.
- Source hash thay vì mở rộng code: tạo run mới, source_amendment.json ghi hash
  tham chiếu C1/hash mới. Không ghi lại manifest hay resume run C0/C1/C2 cũ bằng
  source mới. Ngoài source, manifest/cache phải khớp C1. Test fixture hồi quy trước
  chạy; sau context cần kiểm Entities/graph/vector lists trên đủ401 câu thật.
- Output runs/2wiki/modal/c4-dev-s101-c4/C4_s101; entrypoint
  reproduce/research/run_c4_dev_contexts.py --execute. Chỉ CPU/offline embedding,
  keyword cache C1 nguyên byte, cấm gọi LLM. Không index/answer/judge/test1599.
- Mục tiêu: tách vai trò vector trong B2; ghi cả coverage tăng/giảm, token,
  latency mô tả. Không kết luận accuracy từ coverage hoặc p lớn thành tương đương.
- Trạng thái đăng ký: đang kiểm thử mở rộng, chưa chạy context corpus thật.
- Kiểm thử đã đạt26/26 trong test_phased_qa.py và test_2wiki_acceleration.py,
  fake LLM/embedding, không API. C4 phased khớp MiniRAG, BM25-order khi vector
  đảo thứ tự, giữ graph early-exit; các cấu hình cũ/paired C0C1 vẫn qua fixture.
  Setup C4_BM25_ONLY_SETUP.md ghi scope và source amendment. Chưa context401 thật.
- Người dùng chạy xong C4 context401/401 ok. Đã đối chiếu đầy đủ401 Entities,
  graph/vector/BM25 candidate lists với C1; ranked C4=bm25_ids, Sources<=4000.
  Manifest ngoài source khớp, source amendment khớp hai hash, keyword cache nguyên
  byte. C4 supporting-title hits655/996, đủ document143; C1=672/996, đủ154.
  C1→C4:2 thiếu→đủ/13 đủ→thiếu. Proxy không phải accuracy. Artifact context_comparison
  trong runs/2wiki/modal/c4-dev-s101-c4. Chưa answer/judge C4 tại lần kiểm tra này.

## DEV401-QA-C4-001 — B2_NO_VECTOR answer/judge, đăng ký 01/11/2026

- Dùng nguyên401 context C4 đã kiểm, cùng Qwen/index/seed101/embedding,
  QA max_tokens1024, concurrency4 và prompt như C1. Chỉ chạy phased_qa answers,
  không chạy lại keyword/context/index. C4 mapping bm25, source amendment được
  lưu riêng; bảng Entities và graph/vector/BM25 lists đã chứng minh khớp401 câu.
- Output runs/2wiki/modal/c4-dev-s101-c4/C4_s101. Judge dự kiến
  runs/2wiki/judge/c4-dev-s101-fl35-v2, gemini-3.5-flash-lite/rubric v2, ba lượt,
  limiter/free-tier như C1. Kiểm đủ401 ID, trace model/seed/finish trước chấm.
- Đối chứng chính C1/B2_FULL theo handoff; metrics accurate/error/neither,
  b/c/McNemar exact, bootstrap theo query. Không tuyên bố tương đương hoặc tác
  dụng vector từ một seed/p lớn; không chỉnh top-k/BM25/temperature theo kết quả.
- Trạng thái đăng ký: hướng dẫn người dùng chạy GPU, chưa answer/judge C4.
  Giữ trần25USD, đối soát Billing trước; chưa mở test1599.
- Người dùng báo QA C4 đủ401/401; kiểm tra chi tiết ghi ở PROJECT_STATE sau
  đọc answers.jsonl và requests.jsonl. Chưa tự khởi chạy judge; giữ cùng
  judge/rubric như đăng ký, output riêng c4-dev-s101-fl35-v2.
- Judge C4 sau resume đã đủ1203 phiếu ok. Mean3 judge accurate32,25±0,14 /
  error25,94±0,25 /neither41,81±0,29%; majority130/104/167. So C1:29 lên/46 xuống,
  net−17, exact McNemar p=0,063950; query-bootstrap CI95[-8,48;0,00] điểm majority.
  Xu hướng giảm khi bỏ vector chưa được xác nhận ở0,05; không kết luận tương
  đương hoặc vai trò vector đã chứng minh. Một seed, SD sinh chưa ước lượng.
  Report C1_C4_DEV401_ABLATION_REVIEW.md; metrics runs/2wiki/analysis/c1-c4-dev-s101-fl35-v2.
  Bước tiếp handoff là B2_NO_ENT với Sources nguyên byte C1; chưa chạy thêm GPU/test.

## DEV401-CTX-C2-001 — B2_NO_BM25, đăng ký 01/11/2026

- Theo HANDOFF §2W-10: ablation đầu tiên B2_NO_BM25, đối chứng B2_FULL/C1.
- C2 dùng vector top30 thay RRF(vector top30,BM25 top30) của C1; bảng Entities,
  graph/vector candidates, seed101, Qwen index, embedding384d và Sources4000
  giữ nguyên. Không suy ra vai trò đồ thị từ phép so này.
- Mục đích: kiểm vai trò thành phần BM25 trong B2 sau kết quả C0–C1 chưa có bằng
  chứng accuracy tăng. Không tinh chỉnh weights/top-k/prompt theo điểm dev.
- Bước hiện tại chỉ tạo context CPU trên dev401, dùng nguyên keyword cache C1,
  embedding offline, một worker; cấm LLM nếu thiếu cache. Không answers/judge/test.
- Output mới `runs/2wiki/modal/c2-dev-s101-c4/C2_s101`; entrypoint
  `reproduce/research/run_c2_dev_contexts.py --execute`. Không ghi đè C0/C1/index.
- Kiểm manifest C2=C1 và cache nguyên byte trước chạy; chỉ đổi cấu hình fusion.
  Sau đủ401 context: báo coverage proxy, gained/lost và token/latency mô tả;
  kiểm Entities/candidate lists. Không kết luận accuracy từ coverage.
- QA/judge C2 nếu thực hiện sẽ dùng cùng điều kiện và so với C1 theo query_id,
  acc/error/neither, b/c/McNemar; một seed chưa xác nhận khoa học. Đối soát ngân
  sách trước GPU; lệnh hiện tại không kích hoạt GPU.
- Trạng thái đăng ký: chuẩn bị cache/identity, chưa chạy context C2.
- Người dùng đã chạy context C2:401/401 ok; manifest/cache và401 bảng Entities,
  graph/vector candidate lists khớp C1; ranked_ids của C2 đúng vector_ids.
  Supporting-title hits628/996 (63,05%), đủ tài liệu130 câu, so C1=672/996 và154;
  C1→C2 có2 thiếu→đủ/26 đủ→thiếu. Không suy accuracy từ coverage. Chưa answer C2.
  Artifact: runs/2wiki/modal/c2-dev-s101-c4/context_comparison/.

## DEV401-QA-C2-001 — B2_NO_BM25 answer/judge, đăng ký 01/11/2026

- Tiếp DEV401-CTX-C2-001, cùng dev401/seed101, Qwen index/serving/embedding và
  QA max_tokens1024/concurrency4. Chỉ gọi pha answers của phased_qa, không chạy
  lại keyword/index/context. Output runs/2wiki/modal/c2-dev-s101-c4/C2_s101.
- So C2 với C1/B2_FULL đúng handoff§2W-10, không lấy C0 làm đối chứng chính của
  ablation bỏ BM25. Judge dự kiến gemini-3.5-flash-lite, rubric v2 giữ nguyên,
  ba lượt độc lập; output riêng runs/2wiki/judge/c2-dev-s101-fl35-v2.
- Kiểm đủ401 ID/answer không rỗng, trace model/stop/errors trước judge. Báo đủ
  accurate/error/neither, b/c và McNemar exact theo query_id; không kết luận từ
  một seed, không chỉnh BM25/top-k/prompt sau nhìn kết quả. Chưa mở test1599.
- Snapshot gross usage đã đối soát hai tháng khoảng18,65 USD, trần25 không đổi;
  có thể bill trễ/workload khác. Người dùng tự chạy lệnh answer ở bước kế tiếp,
  chưa gọi GPU/judge C2 tại thời điểm đăng ký. C1 answer641 giây chỉ là tham khảo
  thời gian/chi phí, không phải bảo đảm cho C2.
- Người dùng đã sinh xong C2:401 đáp án,401 ID duy nhất khớp dev, không rỗng,
  context_status ok401. Trace401 request thành công Qwen/Qwen2.5-3B-Instruct,
  finish stop401, seed101 ở401 request, không lỗi/length. Judge C2 chưa tồn tại
  tại lần kiểm tra này; bước tiếp người dùng chạy ba lượt judge đã đăng ký.
- Judge C2 sau resume hoàn tất1203 phiếu ok (giữ nguyên1195 phiếu ok cũ, thử lại
  7 judge_failed/1 parse_failed); không sửa rubric/parser. Mean3 judge acc36,66±0,25 /
  err29,18±0,25 /neither34,16±0,00%; majority146/118/137. So C1:47 lên/48 xuống,
  net−1, exact McNemar p=1; query-bootstrap CI95[-4,99;+4,24] điểm. Error net+17,
  p=0,145487. Chưa chứng minh tác dụng BM25 hoặc tương đương. Report:
  C1_C2_DEV401_ABLATION_REVIEW.md; metrics runs/2wiki/analysis/c1-c2-dev-s101-fl35-v2.
  Một seed, chưa chạy GPU/ablation thêm hoặc mở test trong bước tổng hợp.

## DEV401-QA-C1-001 — Sinh/chấm C1, đăng ký 01/11/2026

- Phụ thuộc DEV401-CTX-C1-001 hoàn tất401/401 context. Dùng đúng các context đã tạo, không chạy lại keyword/index/retrieval hoặc mở test1599.
- C1=B2_FULL có sẵn theo HANDOFF §1.5. Qwen2.5-3B bf16, seed101, QA max_tokens1024, concurrency4, serving và prompt giống C0. Baseline đối chứng `baseline-dev-s101-c4/C0_s101`; index/registration/code/keyword manifest đã kiểm khớp C0.
- Chạy pha `answers` của phased_qa thông thường. Chỉ tái dùng helper `gpu_child` để giới hạn wall-time1800 giây; không dùng paired-context acceleration/pipeline chưa có validation802. Guard wall-time không phải hard cap hóa đơn; có thể còn GPU giữ ấm.
- Đối soát Modal CLI trước chạy: summary2026-10 metered18.36875559 USD, billed0; summary2026-11 metered0, billed0. Giữ trần thí nghiệm25 USD theo gross usage, còn khoảng6.63 trước đợt này. Người dùng yêu cầu tiếp tục, không nâng trần theo credit tháng mới.
- QA output `runs/2wiki/analysis/c1-context-dev401-s101/C1_s101/answers.jsonl`; checkpoint từng dòng và kiểm401 ID, nonempty/context_status, response model, finish_reason, usage/errors trước judge.
- Judge output mới `runs/2wiki/judge/c1-dev-s101-fl35-v2`, model `gemini-3.5-flash-lite`, rubric `2wiki-upstream-aliases-v2`, ba lượt độc lập, giữ limiter/free-tier và aliases giống C0. Resume giữ phiếu ok, không tự coi lỗi API là neither hoặc đổi key/model/rubric để né giới hạn.
- Đo accurate/error/neither mean±sd giữa judge, majority ghép query_id, b lên/c xuống/McNemar exact so C0. Một lượt sinh chưa đủ kết luận cải tiến; không chọn cấu hình/top-k sau nhìn điểm. Báo cả kết quả âm, câu thiếu/lỗi và giới hạn chi phí/serving provenance.
- Trạng thái lúc đăng ký: chưa gọi QA/judge C1.
- QA hoàn tất: 401/401 ID đúng dev, không trùng/thiếu/lạ/rỗng; context_status ok401. Trace401 request thành công, response Qwen/Qwen2.5-3B-Instruct401, finish_reason stop401, không lỗi/length. Guard ghi elapsed641,02 giây, exit0 (05:41:38→05:52:19 UTC ngày01/11). Chưa khởi chạy judge C1 tại lần kiểm tra này; bước tiếp theo là người dùng chạy judge đã đăng ký.
- Judge C1 nay hoàn tất1.203/1.203 phiếu ok. Mean acc36,66±0,00 /err25,27±0,38 /neither38,07±0,38%; majority147/101/153. So C0 bằng metrics.py:51 lên/46 xuống, net+5, exact McNemar p=0,684859; CI95 query bootstrap delta majority[-3,49;+5,99] điểm. Chưa có bằng chứng cải thiện, không kết luận tương đương. Chỉ một lượt sinh; SD giữa lượt sinh chưa ước lượng. Report C0_C1_DEV401_QA_REVIEW.md; metrics/paired answers trong runs/2wiki/analysis/c0-c1-dev-s101-fl35-v2. Chưa chạy thêm GPU/ablation hoặc test1599 trong bước tổng hợp.
- Chẩn đoán offline97 cặp đổi accuracy: nhóm lên có18 tăng/30 giữ/3 giảm số supporting document; nhóm xuống6 tăng/34 giữ/6 giảm. Tập supporting titles giữ nguyên ở62/97 cặp; không quy tất cả đổi kết quả cho retrieval hay nhiễu sinh. Rà riêng Sharaf xác nhận cả hai Sources đủ hai quan hệ nhưng C1 abstain; ghi ví dụ trong report. Đây là association tự động cộng ví dụ rà, chưa phải taxonomy thủ công toàn97; không gọi API hoặc sửa nhãn.

## DEV401-CTX-C1-001 — Đăng ký kiểm tra context C1, 01/11/2026

- Phạm vi: internal_dev401 seed101, index `indexes/2wiki-modal-n2000-s13-dev20test80`, keyword cache từ `runs/2wiki/modal/baseline-dev-s101-c4/kw_s101.jsonl`. Không mở internal_test1599, không sinh đáp án hoặc gọi judge/GPU.
- Cấu hình có sẵn: C0=baseline nhóm; C1=B2 `vector_bm25` theo RUN_2WIKI_DEV20_TEST80.md và phased_qa.py. Đây là kiểm tra retrieval của cấu hình dự án, không đăng ký nó như phương pháp mới.
- Observed problem: 200/259 câu dev error/neither thiếu supporting document ở Sources; trên 67 câu, vector candidate đã có ít nhất một document bị bỏ qua. Nguồn: BASELINE_DEV401_FAILURE_REVIEW.md.
- Giả thuyết: fusion C1 có thể giữ thêm tài liệu hỗ trợ trong cùng ngân sách Sources. Chưa có căn cứ kết luận hiệu ứng riêng BM25 hay cải thiện accuracy.
- Giữ index, embedding local384d, question IDs, keyword seed101, top-k, Sources4000 và prompt/model không đổi. Một CPU worker, offline HF/Transformers; pha context cấm gọi LLM nếu cache thiếu.
- Output mới: `runs/2wiki/analysis/c1-context-dev401-s101`. Giữ nguyên run baseline. Đối chứng là context C0 đã đo, ghi rõ khác thời điểm đo latency; không dùng thời gian giữa hai đợt để tuyên bố speedup.
- Chỉ số: đủ401 context/status, supporting-title document coverage và exact supporting-fact proxy, số Sources/token, p50/p95 retrieval tham khảo; các câu tăng/giảm coverage và vấn đề annotation đã gắn cờ. Gold chỉ được dùng trong phân tích sau retrieval.
- Quy tắc quyết định: báo đầy đủ cả tăng và giảm; không chọn top-k/fusion weights theo điểm, không kết luận chất lượng QA từ coverage. Chỉ xem xét chạy generation khi context đủ, dữ liệu ghép ID/hash đúng và đã đối soát Billing trong trần tổng $25. Không có ngưỡng điểm tùy tiện hoặc kết luận khoa học từ một seed.
- Trạng thái lúc đăng ký: chưa chạy C1 context.
- Kết quả sau chạy: C1 đủ401/401 context ok; manifest/cache khớp C0, 401/401 Entities và graph/vector candidate lists giữ nguyên. Recall supporting-title proxy60,34%→67,47%; số câu đủ document137→154, 32 lên/15 xuống, McNemar proxy p=0,01862. Inference đủ document23→22; ghi cả kết quả âm. Chưa có answer/accuracy C1, chưa GPU/judge/test. Báo cáo `C1_DEV401_CONTEXT_REVIEW.md`; artifact `runs/2wiki/analysis/c1-context-dev401-s101/comparison/`. Không coi độ phủ tăng là bằng chứng accuracy tăng.

## PREP-001 — Môi trường và dữ liệu

- Nhánh `research/2wiki-qwen`, nền `9c59062a9cfaaab47b4e8b303829ce0d00624e91`.
- Python 3.13.5; import/embedding 384 chiều đã kiểm; package list và editable metadata trong env/.
- Archive khớp checksum; dev 12.576 câu có nhãn; test answer rỗng; aliases là JSONL.
- Ignore dữ liệu sinh/index/run/venv; S-02 chờ người còn lại review và quyết định backup index.

## PREP-002 — Chuẩn hóa và phát hiện dữ liệu nguồn

- Hoàn tất chuẩn hóa offline sau ghi chú review schema tại `PROTOCOL_2WIKI_REVIEW.md`.
- 54.957 đoạn ứng viên, 12.576 câu; chưa chọn corpus.
- Sửa kiểm tra title quá chặt: 523 lượt title lặp trong 463 câu đều cùng nội dung, không phải xung đột.
- Phát hiện 70 sentence index ngoài đoạn ở 70 câu; giữ nhãn gốc, fact null và mapping_status rõ ràng; không sửa đáp án hoặc loại câu.
- Chuẩn hóa version 2; mọi checksum trong processed/manifest.json, kiểm `--check` thành công.

## PREP-003 — Đo pool và split ứng viên

- Seed 13, sort _id rồi shuffle; dùng cả gold và distractor.
- N=200/500/1.000/2.000: chunk 1.535/3.446/6.388/11.661; nominal call index 3.070/6.892/12.776/23.322.
- Split gold-title connected components, ứng viên test 20%; cân bằng loại câu không dùng answer/judge.
- Kết quả 160/40, 400/100, 800/200, 1.599/401; không title gold chung. Mọi số là ứng viên, chưa khóa N hoặc split.

## PREP-004 — Audit gần trùng và kiểm chứng (26/10/2026)

- Cố định ngưỡng Jaccard char 5-gram >= 0,85 trước chạy audit; normalization NFKC + casefold + bỏ dấu câu/gộp khoảng trắng.
- So câu hỏi và thân đoạn gold bỏ title; join chính xác, prefix filter kiểm bằng exhaustive fixture.
- Cả bốn pool có 0 cặp vượt ngưỡng; không thay đổi nhóm/split ứng viên. Chưa kiểm paraphrase ngữ nghĩa và gần trùng mọi distractor.
- Báo cáo `env/2wiki_near_duplicate_audit_seed13.json`, chỉ thống kê và hash, không test text/IDs.
- 7 test offline đạt; toàn bộ năm file chuẩn hóa tính lại khớp byte. Chưa gọi LLM hoặc benchmark.
- Báo cáo review: `PREPARATION_REVIEW_2WIKI.md`. Chưa commit/push hoặc gửi báo cáo cho người khác.

## PREP-005 — Metrics judge và so sánh ghép cặp (26/10/2026)

- Đọc contract per_question.csv từ judge_run.py ở commit protocol tham chiếu; không thay rubric hay gọi judge.
- Triển khai metrics.py với summarize/compare; đếm ba nhãn, parse_failed/judge_failed/missing, majority/no_majority, bảng theo loại câu, mean/sd giữa lượt judge; xuất mỗi query × lượt sinh × lượt chấm.
- McNemar exact đếm lên/xuống theo query_id; bootstrap resample query, giữ các lượt sinh trong query. Tách sd giữa lượt sinh và giữa lượt judge.
- Từ chối query trùng/lạ, sai type/majority, checksum bị sửa và so khác index/split/rubric/judge nếu manifest có đủ. Khi không có provenance đầy đủ, đánh dấu false, không tự chứng nhận run.
- 17 test metrics dữ liệu giả đạt; chạy chung tests/research: 24 passed. Không dùng answer thật hoặc API, không tạo kết quả benchmark.
- Efficiency/Evidence Recall và early-exit/generation failures chưa có nguồn log phù hợp: báo null, cần tích hợp trước đánh dấu S-06 hoàn tất.

## PREP-006 — Chuyển sang local theo yêu cầu người dùng (26/10/2026)

- Phát hiện Ollama 0.40.10 và Qwen2.5:3b Q4_K_M đã có; không tải/cài lại. Chạy server loopback cloud disabled, parallel 1; không đổi .env hoặc env toàn hệ thống.
- Smoke LOCAL_OK, context 32k và 100% GPU xác minh qua native /api/ps, 3.367.879.311 byte VRAM.
- Canary01 dừng trước index do dataclasses deepcopy SSLContext của bound method; giữ logs/index rỗng. Sửa wrapper bằng closure, không sửa core.
- Canary02 index hai doc giả, tạo hai chunk/3 node/2 cạnh; sáu request extract/glean/parser/answer đều Qwen local, 1.189 token sinh, không lỗi/chạm trần. Answer chứa địa danh fixture Riverton.
- Lưu raw requests, context/generation, retrieval, cache keyword, events, runtime và checksum index. Đã unload model và xác nhận GPU 0 MiB. Server còn chạy nền.
- Thêm adapter/launcher/config/report và 9 test HTTP mock; tổng 33 passed. Chưa có benchmark/judge 2Wiki.
- Local Q4_K_M khác bf16/vLLM của MultiHop; mọi đối chứng 2Wiki sau này cần cùng digest/settings và index local. Không chứng nhận HF revision tương đương từ tên model.

## PREP-007 — Nhóm chọn pool 2.000 câu

- Người dùng gửi ảnh tin nhắn nhóm: nguồn có khoảng 12k câu, chạy 2k trước. Diễn giải chọn pool 2.000 câu hỏi, đã thông báo rõ trước khi chuẩn bị.
- Materialize theo đúng phép lấy mẫu đã đo (sort _id, shuffle seed 13), corpus ID `2wiki-n2000-s13-4267adcf3ef6`.
- 2.000 câu: compositional 796, comparison 480, bridge_comparison 481, inference 243. Hợp cả context gold và distractor: 11.657 đoạn, 11.661 chunk đo offline, nominal 23.322 call index.
- Tạo pilot_docs.jsonl gồm 200 đoạn lấy mẫu độc lập gold relevance bằng seed 13; chưa chạy index.
- Lưu docs/queries/gold/questions, corpus_manifest/pilot_manifest trong processed/pools/n2000_seed13/ được ignore. Public report chỉ counts/hashes, không full ID/test text.
- Split 80/20 vẫn là đề xuất, chưa khóa; không tự mở internal_test. Đề xuất 500 trước đó bị thay thế bởi lựa chọn mới.

## PILOT-001 — Lô đầu 10/200 đoạn thật, local Q4_K_M

- Người dùng đồng ý tiếp tục sau materialize pool2000. Chạy có giới hạn --max-new-docs10 để đo và kiểm checkpoint trước mở rộng.
- Runner mới không sửa minirag, bảo vệ đường dẫn/index cũ; identity/docs/model/source hashes, raw từng request, commit từng doc và checkpoint bất biến cuối lô. Nếu torn write thì từ chối sửa tại chỗ.
- 5 test mới đạt, tổng38 trước chạy model.
- Đã index 10 doc/10 chunk: 20/20 request Qwen local, 77 node/32 cạnh, 7/7 kiểm toàn vẹn đạt; --verify sau chạy vẫn đạt, không phát sinh request model.
- Sinh 12.921 token trong 182,161 giây request; tổng per-doc184,186 giây. Có 1 extraction cap4096 (5% request), 409 segment ## nhưng chỉ48 segment duy nhất và có COMPLETE. Đây là chẩn đoán rawtext, chưa thay stop/cap hoặc làm sạch đồ thị.
- Dự toán sơ bộ pilot200 khoảng61,4 phút tổng, full11657 khoảng59,6 giờ. Chưa chạy toàn corpus, chưa QA/judge, chưa nói chất lượng B2.
- Run/checkpoint/raw/index và báo cáo đã lưu, model được unload. Chi tiết LOCAL_PILOT_STAGE10.md.

## Chờ trước mở rộng pilot/benchmark 2Wiki

- Protocol/rubric/schema/logger/runner chung, S-08 và S-09; metrics judge chờ review, phần retrieval/efficiency và ablation chưa hoàn tất.
- Gemini Flash exact ID/project/quota; nhóm review điều kiện Qwen Q4_K_M local. Client Python 3.13.5; server native Ollama đã kiểm, không còn phụ thuộc Python server Modal.
- V-01/MR_FULL, V-02 cách paper dựng corpus vẫn chưa xác minh đủ.
- N=2.000 đã chọn; đã chạy lô kỹ thuật10 đoạn theo đồng ý tiếp tục của người dùng. Trước mở rộng cần review vòng lặp/cap và thời gian máy local; backup, split và cổng QA/benchmark chung vẫn còn mở.

## INFRA-001 — Review và thử tích hợp runner chung (29/10/2026)

- Nền 2Wiki `0d7a18c`, PR #1 head `77ae1af`; ghép không xung đột trên `research/2wiki-shared-gpu` riêng. PR vẫn Draft/chưa merge vào dev tại thời điểm kiểm tra.
- Python 3.13.5, toàn bộ 78 test research offline đạt. Giữ code chuẩn hóa/metrics/local adapter/config và index/checkpoint local.
- Chưa gọi Modal/Gemini hoặc chạy benchmark. Ba phát hiện cần xử lý trước live run: resume index phải so endpoint, khóa chống hai writer, lưu request thô và nối ID/attempt. Chi tiết `SHARED_GPU_INTEGRATION_REVIEW.md`.

## INFRA-002 — Sửa guard và request audit (29/10/2026)

- Trên nhánh tích hợp riêng: bắt buộc so endpoint hash khi resume; khóa OS xuyên suốt phiên ghi index; trace schema 2 lưu provider request/response và query/doc/chunk ID, phase, request ID/attempt, lỗi/hủy.
- Không thay prompt, retrieval, giới hạn sinh hoặc lựa chọn model/judge. Không sửa manifest của index cũ để vượt source/endpoint guard.
- Thêm test endpoint thay đổi không được sửa index, writer thứ hai bị từ chối, raw trace/retry attribution giữa task song song, cancellation và raw provider JSON. Cần nhóm review bản sửa trước đưa vào runner chung.
- Kết quả bản cuối: 86 passed trên Python 3.13.5 (38,87 giây), diff whitespace đạt; test dùng mock/fake và Hugging Face offline.
- Không chạy index/QA/judge thật, không phát sinh chi phí model.
