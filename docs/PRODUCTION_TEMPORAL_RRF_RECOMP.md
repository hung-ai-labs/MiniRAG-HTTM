# Pipeline production: MiniRAG C0 + source-time + RRF + chọn lượt lời và ngữ cảnh liền kề

Ngày: 11/11/2026. Cấu hình production được người dùng duyệt sau pilot 50 cặp.
**ACC quan sát tăng 76% → 86%, ERR giảm 14% → 10%; chưa xác nhận cải thiện bằng kiểm định thống kê.**

## 1. Pipeline dùng cho slide

```text
Câu hỏi
 ├─ MiniRAG C0
 │   → phân tích entity và answer-type
 │   → tìm seed, sinh path hai hop
 │   → P0 + semantic relation voting
 │   → path2chunk → kwd2chunk
 │   → source-time của Tài: bổ sung/ưu tiên nguồn đúng ngày/tháng
 │   → graph + time: top-30
 │
 └─ Dense: embedding câu hỏi, cosine với index chunk → top-30
                         │
              RRF, k=60; gộp trùng
                 tối đa 60 chunk
                         │
          Adapter chọn lượt lời do nhóm thiết kế
          • chia nguồn thành lượt lời nguyên văn
          • RECOMP chấm độ liên quan với câu hỏi
          • lấy lượt lời mục tiêu + lượt trước/sau cùng khối Time
          • giữ speaker, Time, chunk ID và quote/offset
          • gộp phần trùng, đánh dấu phần bị lược bỏ
          • thêm cả nhóm nếu vừa ngân sách; không vừa thì xét nhóm sau
                         │
            A1 kiểm tra ≤4.000 token nội dung Sources
                         │
          Entities của C0 + Sources được chọn → sinh câu trả lời
```

Luồng entity, answer-type, path, P0, relation voting và dense đều được giữ. Đây là thay đổi **chọn nội dung sau RRF và trước A1**, không phải đồ thị mới, không thay P0 bằng P2. Không cần indexing lại. Baseline và index gốc được giữ để đối chứng.

## 2. Source-time và RRF

Source-time dùng ngày của tài liệu (`Time:`), không suy ra ngày sự kiện được nhắc bên trong câu. Ngày/tháng trong câu hỏi được đối chiếu với metadata nguồn. Liên quan entity ưu tiên chunk trong ngày/tháng đó; tối đa ba chunk mỗi mốc được cộng vào điểm C0 theo cơ chế của Tài. Không suy diễn năm khi không xác định được duy nhất.

Hai bảng graph+time và dense có tối đa 30 chunk mỗi bảng. Với vị trí bắt đầu từ 1:

\[
RRF(c)=\frac{\mathbf{1}[c\in G]}{60+rank_G(c)}+
       \frac{\mathbf{1}[c\in D]}{60+rank_D(c)}.
\]

Chunk trùng ID chỉ xuất hiện một lần; hòa điểm giữ thứ tự xuất hiện. Tập hợp có tối đa 60 ID, bỏ ID thiếu văn bản. Không thêm BM25 hoặc tìm kiếm ngoài pool vào cấu hình này.

## 3. Chọn nội dung trong ngân sách

Từng chunk được chia thành lượt lời hoàn chỉnh, không cắt câu trả lời thành các từ riêng. Header `Time:` chia các khối độc lập. Văn bản không nhận diện được speaker được giữ như đơn vị raw; không bịa vai trò. Span dùng vị trí ký tự Unicode chính xác trong chunk. Offset tài liệu chỉ có khi mapping là duy nhất.

Với encoder công khai RECOMP, vector được mean-pooling theo attention mask. Điểm liên quan:

\[
s(q,u)=f(q)^\top f(Time(u)\Vert u).
\]

Không L2-normalize. Nếu vượt cửa sổ encoder, chỉ chia cửa sổ để chấm và lấy max; đơn vị văn bản được chọn vẫn nguyên vẹn. Checkpoint được ghim theo revision và SHA256; không fine-tune bằng QA/gold của dự án.

Mỗi mục tiêu `u` tạo nhóm `B(u) = {u trước, u, u sau}` trong **cùng chunk và cùng khối Time**. Ở biên chỉ lấy những lượt tồn tại. Đây là adjacency cục bộ, chưa bảo đảm đã giải quyết đại từ hoặc đủ bằng chứng ngữ nghĩa.

Duyệt mục tiêu theo điểm giảm dần; hòa điểm dùng hạng RRF rồi offset nguồn. Với tập đã chọn `S`, chỉ nhận nhóm mới nếu:

\[
\sum_{c\in pool}tokens(render_c(S\cup B(u)))\leq 4000.
\]

Phần trùng chỉ tính một lần; tính lại token sau render, gồm Time và dấu lược bỏ. Nếu nhóm không vừa thì bỏ qua cả nhóm và xét tiếp, không dừng toàn bộ như prefix và không cắt nhóm. Không chia relevance cho độ dài. Đầu ra giữ thứ tự chunk theo RRF và lượt lời theo nguồn; không viết lại nội dung bằng model sinh.

A1 sau đó giữ vai trò kiểm tra trần. Nếu A1 cắt mất nhóm đã chọn, runtime báo lỗi. **4.000 là tổng token nội dung Sources**, theo cùng quy ước baseline; chưa bao gồm CSV, Entities, câu hỏi và system prompt. Vì vậy toàn prompt có thể vượt 4.000.

## 4. Phần nhóm thiết kế và nguồn kế thừa

Tên mô tả cho slide: **“Bộ chọn lượt lời bảo toàn nguồn và ngữ cảnh liền kề dưới ngân sách token.”**

Nhóm thiết kế việc dùng lượt lời hội thoại làm đơn vị, giữ Time/speaker/offset, đóng nhóm trước–sau, gộp overlap, kiểm ngân sách sau render và tích hợp sau RRF/trước A1. Đây là thiết kế thích nghi trong project; không phải một pipeline có sẵn được bật bằng cờ của bài MiniRAG.

Cần ghi nhận đúng: encoder và nguyên lý extractive relevance của **RECOMP là công trình có trước**, RRF cũng là phương pháp có trước; source-time là phần của Tài. Không viết “nhóm tự phát minh RECOMP”, “toàn bộ phương pháp là mới”, hoặc “đã chứng minh đồ thị đóng góp”. Kết hợp cụ thể do nhóm triển khai chưa tự nó chứng minh novelty trong tài liệu nghiên cứu.

Nguồn: [RECOMP](https://arxiv.org/abs/2310.04408), [code tác giả](https://github.com/carriex/recomp/blob/main/run_extractive_compressor.py), [checkpoint công khai](https://huggingface.co/fangyuan/hotpotqa_extractive_compressor).

## 5. Kết quả QA tạm: 50 cặp, một lượt sinh và một lượt chấm

**Baseline của phép so này là C0 + source-time + RRF + A1 gốc**, không phải C0 thuần.

| Cấu hình | Đúng | Sai | Neither | ACC | ERR | Neither |
|---|---:|---:|---:|---:|---:|---:|
| Baseline C0 + source-time + RRF + A1 | 38 | 7 | 5 | 76% | 14% | 10% |
| Thêm bộ chọn lượt lời + ngữ cảnh liền kề | 43 | 5 | 2 | 86% | 10% | 4% |

- ACC: 8 câu lên / 3 xuống, net +5 câu = +10 điểm phần trăm; McNemar exact **p=0,2265625** (Holm hai endpoint: 0,453125).
- ERR: sửa 5 lỗi / tạo 3 lỗi mới, net −2 câu = −4 điểm phần trăm; **p=0,7265625**.
- Neither: 5 → 2 câu, giảm 6 điểm phần trăm.

Mẫu cố định 40 Single / 5 Multi / 5 Null; cùng index Qwen, parser cache, graph/P0, source-time, dense/RRF, Entities và prompt. Biến thay đổi là phần chọn nội dung. Cả sinh và judge dùng `deepseek-flash`, thinking tắt, cùng tham số giữa hai arm; generation max 1024, judge max 16. Đây không phải tái tạo đầy đủ benchmark SLM của paper.

Có 100 generation mới và 100 judgment hợp lệ. Một judgment giải thích bị cắt thay vì xuất nhãn: giữ chi phí/raw và retry cùng prompt/model/tham số, lấy nhãn hợp lệ đầu tiên. Không quy lỗi API thành neither. Pilot dùng 201 requests mới, chi phí ước tính theo giá peak **$0,165506**, không phải hóa đơn nhà cung cấp.

Mẫu nhỏ, dev đã xem nhiều lần, 40 câu thuộc pilot evidence trước và 10 câu thêm vẫn thuộc dev cũ; không phải holdout. Một lượt sinh/chấm có nhiễu và cùng family sinh/chấm có bias. **Chỉ được viết có tín hiệu tích cực trên pilot**, chưa viết cải thiện ACC/ERR đã được xác nhận. Chưa có nhãn span do người kiểm để công bố full-support recall của bản nén.

Dữ liệu để làm slide và rà từng câu: [paired_results.csv](../reproduce/production_results/qa50_20261111/paired_results.csv), [qa_report.json](../reproduce/production_results/qa50_20261111/qa_report.json), [kiểm tra độc lập](../reproduce/production_results/qa50_20261111/independent_verification.json). Hai file answers/judgments giữ đủ output và nhãn của hai arm.

## 6. Bật cấu hình production

Từ thư mục gốc repo:

```bash
pip install -r requirements.txt -r requirements-gemini.txt -r requirements-production.txt
python -m minirag.production --prepare-model
python -m minirag.production
```

Lệnh đầu chuẩn bị dependency; `--prepare-model` tải checkpoint công khai có revision ghim, không gọi QA/Judge. Không commit model hoặc cache. Lệnh cuối chỉ in cấu hình; mặc định launcher là `production`. Thư viện và `baseline.yaml` giữ mặc định cũ để các thí nghiệm lịch sử không bị đổi ngầm.

Chạy bằng backend đã cấu hình trong `.env`, dùng **bản sao index riêng** để cache/log truy vấn không ghi vào index đóng băng:

```bash
# Chọn tên mới chưa tồn tại; chỉ sao chép index hiện có, không indexing lại.
cp -R LiHua-World-qwen-modal playground-index-production
python -m minirag.production -- python reproduce/Step_1_QA.py \
  --workingdir ./playground-index-production \
  --questions ./dataset/LiHua-World/qa/query_set.csv --limit 12 \
  --outputpath ./logs/production_pilot12.csv
```

Ví dụ này **sẽ gọi backend khi người chạy thực thi**; lần đóng gói/push không chạy lại QA/Judge. Có thể thay lệnh con bằng script ứng dụng hiện có, miễn không tự ghi đè profile, dùng mini/top_k=60/budget=4000 và embedding tương thích index. Các profile khác phải chạy worker riêng vì biến môi trường dùng chung toàn process.

Đối chứng giữ cùng mọi luồng, chỉ tắt bộ chọn:

```bash
python -m minirag.production --profile baseline -- python reproduce/Step_1_QA.py \
  --workingdir ./playground-index-production --limit 12 \
  --outputpath ./logs/production_baseline12.csv
```

`--profile c0` là project C0, tắt source-time/RRF/bộ chọn. Có thể dùng `--model-dir` và `--cache-dir` hoặc biến `MINIRAG_RECOMP_MODEL_DIR`, `MINIRAG_RECOMP_CACHE`. Checkpoint thiếu/sai hoặc profile xung đột sẽ báo lỗi, không âm thầm chạy phương án khác. Không chạy launcher quanh script tự thay fusion/profile giữa các arm.

Kiểm tra offline kết quả đã công bố, không phát sinh API:

```bash
python -m reproduce.verify_production_pilot
python -m unittest discover -s tests -p test_extractive_context.py
python -m unittest discover -s tests -p test_production_profile.py
```

## 7. File chính

| File | Vai trò |
|---|---|
| `minirag/production.py` | Profile production mặc định của launcher, baseline/c0 đối chứng, chuẩn bị checkpoint |
| `minirag/operate.py` | Nối source-time và bộ chọn vào pipeline sẵn có |
| `minirag/temporal.py` | Source-time của Tài, đọc metadata nguồn |
| `minirag/temporal_rrf.py` | Kiểm profile và trace token/pool |
| `minirag/extractive_context.py` | Lượt lời, adjacency, source mapping, packing và validation |
| `minirag/recomp_encoder.py` | Encoder local ghim revision, vector cache ghi nguyên tử |
| `reproduce/production_results/qa50_20261111/` | Kết quả pilot và provenance để kiểm tra |

Chấp nhận cấu hình để sử dụng thực tế là quyết định triển khai. Kết luận khoa học vẫn giới hạn ở kết quả pilot nêu trên; chưa có benchmark 200 câu hay lặp nhiều lượt cho bộ chọn này.
