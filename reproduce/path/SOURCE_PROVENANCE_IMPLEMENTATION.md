# Triển khai tiền đề cho path scoring có provenance

09/11/2026. Gắn với `NEXT_GRAPH_IMPROVEMENT_RESEARCH_20261109.md`.

## Phần đã triển khai

1. `audit_source_provenance.py`: audit từ index và artifacts đóng băng; không
   gọi retrieval, embedding, generator hoặc judge. Tạo inventory, manifest
   hash, gói review 27 cặp cùng các ca thành công đối chứng. Không tự gán nhãn
   multi-hop, lỗi annotation hay sự kiện từ việc trùng entity.
2. `minirag/source_witnesses.py`: bộ ghi tại hai parser trích xuất gốc, trước
   merge. Ghi entity/relation, description và source_chunk thành cùng một
   record, ID ổn định, chống trùng trong lượt ghi. Dữ liệu gốc trả về parser
   giữ nguyên; không đổi scoring hoặc cấu trúc merge hiện có.
3. Test cho việc giữ đúng nguồn, giữ output parser, chống ghi đè, chống lồng
   capture và khôi phục parser khi có exception.

Đây là hạ tầng quan sát và bảo toàn nguồn, **chưa phải một C4 cải thiện QA**.
Không sửa C0/C1/C3 hoặc đổi context của study QA đang chạy.

## Audit thực tế

Lượt đầu: `logs/source_provenance/20261109_audit/report.json`.

| Đại lượng | Giá trị |
|---|---:|
| Cặp mục tiêu / câu phân biệt | 27 /26 |
| Ca đối chứng thành công | 6 |
| Node / cạnh | 1.556 /1.509 |
| Node có nhiều nguồn và nhiều description | 313 |
| Cạnh có nhiều nguồn và nhiều description | 167 |
| Node có cùng số nguồn/description lớn hơn 1 | 204 |
| Cạnh có cùng số nguồn/description lớn hơn 1 | 117 |
| Tham chiếu nguồn node tới ID không có trong kho chunk | 19 |
| Tham chiếu nguồn cạnh tới ID không có trong kho chunk | 9 |
| Cache LLM extraction | 0 entry |

19/9 là số tham chiếu theo node/cạnh, không phải số chunk phân biệt.
313/167 là số đối tượng **không đủ dữ liệu để xác định alignment**; không
được đổi thành số lỗi đã chứng minh. Source membership của một cạnh còn
được lưu; phần thiếu là ánh xạ mô tả cụ thể sang nguồn cụ thể sau merge.

Checkpoint extraction hiện chỉ là danh sách ID đã xử lý. Không có raw
extraction đủ để tái lập mapping chính xác trên toàn bộ graph. Không zip hai
danh sách, không suy diễn supporting quote từ description do model tạo.

## Chạy audit

```sh
.venv/bin/python reproduce/path/audit_source_provenance.py \
  --output logs/source_provenance/NEW_RUN
```

Output phải chưa tồn tại. Mở `REVIEW_PACKET.md` để đọc question, gold answer
và toàn bộ chunk; điền nhãn vào bản review riêng của `review_packet.jsonl`.
Raw source không bị sửa. Mọi semantic label vẫn là unreviewed cho tới khi
được đọc và thẩm định; các route ghi trong packet là đường cấu trúc có thể
đi tới nguồn, không phải chứng minh đó là selected/voted path của retrieval.

## Dùng capture cho một lần index mới

API tích hợp vào driver indexing đang dùng:

```python
from minirag.source_witnesses import capture_source_witnesses

# rag_new phải dùng working_dir MỚI và model/embedding đã chốt cho experiment.
# Không dùng các index đóng băng đang phục vụ QA.
with capture_source_witnesses("/path/to/NEW_RUN/raw_source_witnesses.jsonl"):
    await rag_new.ainsert(documents)
```

Đây là ví dụ tích hợp, không phải lệnh đã index lại. Capture wrap parser
trong process riêng của driver, không bọc server dùng chung index/query.
Nó không gọi thêm LLM; ghi những extraction vốn đã xảy ra. Không tự đổi
model/endpoint. Không có lệnh reindex trả phí hoặc ghi lên index cũ được chạy.

Sidecar chỉ chứa extraction thực tế đi qua parser trong lần capture đó.
Không retroactively phủ nguồn của tài liệu đã được checkpoint bỏ qua;
cần index mới từ đầu để đánh giá coverage đầy đủ. Nếu indexing thất bại,
sidecar là partial, không coi là graph witness hoàn chỉnh. File có sẵn bị
từ chối; chưa có chế độ resume sidecar. Không dùng lại file partial để công
bố kết quả; một cơ chế resume phối hợp với checkpoint index cần thiết kế riêng.

Schema gồm `kind`, `source_chunk`, `extraction`, `witness_id`,
`evidence_status=unvalidated_extraction`, `event_metadata=null`.
Description do model sinh không phải trích dẫn nguyên văn; chưa có validation
relation entailment, timestamp hay role. Không gọi record này là evidence
đã được xác nhận.

## Vì sao chưa bật W(p)

Tài liệu nghiên cứu đặt điều kiện audit phải chứng minh lỗi nguồn/sự kiện
trước khi định nghĩa W. Audit máy hiện chỉ xác nhận thiếu mapping, chưa
thẩm định 27 cặp và chưa có witness sự kiện đủ tin cậy. Vì vậy chưa có cơ sở
đặt threshold/trọng số hoặc phạt path vì thiếu timestamp.

Bước còn lại để có scorer hoàn chỉnh:

1. Thẩm định packet và đối chứng; xác định tần suất từng lỗi.
2. Thu witness trên index phiên bản mới, cùng SLM và embedding, nếu audit
   hỗ trợ hướng này; không trộn index Gemini với baseline Qwen để kết luận.
3. Định nghĩa W từ quan sát được, quy tắc unknown/fallback và ablation trước đo.
4. Nối scorer theo opt-in riêng, giữ mọi luồng và đối chứng C0/C1/C3,
   affinity-only/dense; chạy offline rồi mới QA.

Không thay bằng pool-affinity reranker trong lúc thiếu provenance. Chưa có
evidence/accuracy tăng cho hướng witness này; không gán số của C3 cũ cho nó.
