# HD-Schema: Đặc tả Chuẩn hoá Log Kết quả Thí nghiệm (Task 7)

Tài liệu này định nghĩa cấu trúc dữ liệu chuẩn (`HD-Schema`) cho tệp kết quả thực nghiệm `logs/results.json` trong dự án nghiên cứu MiniRAG.

Schema này đóng vai trò **Data Contract** giữa 3 thành viên:
- **Huy Đức (Experiment & Evaluation)**: Lưu trữ metadata, tham số thực nghiệm (top_k, mode, latency, token consumption) để so sánh nhạy cảm (`HD2`, `HD3`, `HD-Final`).
- **Tài (Baseline & Failure Analysis)**: Lấy danh sách câu trả lời sai, ground truth và ngữ cảnh truy xuất để phân loại lỗi theo 6-Stage Failure Taxonomy (`T4`–`T6`).
- **Hùng (Retrieval & Proposed Method)**: Xem các đoạn trích xuất (retrieved evidence) để chẩn đoán path/entity và kiểm tra hiệu quả của Hybrid / Adaptive retrieval (`H2`–`H7`).

---

## 1. Cấu trúc Tổng thể (Top-Level Structure)

File `results.json` bao gồm một đối tượng JSON có các phần chính:
```json
{
  "experiment_id": "string",
  "timestamp": "ISO-8601 string",
  "config": { ... },
  "summary_metrics": { ... },
  "results": [ ... ]
}
```

---

## 2. Chi tiết các trường dữ liệu

### 2.1. `config` (Cấu hình Thực nghiệm)
| Trường | Kiểu dữ liệu | Mô tả |
|---|---|---|
| `corpus` | string | Tên/mô tả corpus dữ liệu (vd: `"LiHua-World (442 docs)"`) |
| `working_dir` | string | Đường dẫn thư mục index (vd: `"./LiHua-World-gemini"`) |
| `llm_model` | string | Tên mô hình sinh câu trả lời (vd: `"gemini-flash-lite-latest"`) |
| `embedding_model` | string | Mô hình embedding (vd: `"sentence-transformers/all-MiniLM-L6-v2"`) |
| `retrieval_mode` | string | Chế độ truy xuất (`"mini"`, `"light"`, `"naive"`) |
| `top_k` | int | Số lượng entity/nodes top_k (vd: `60`, `5`, `10`) |
| `judge_model` | string | Tên mô hình LLM dùng để chấm điểm |
| `judge_repeats` | int | Số lượt chấm độc lập (mặc định: `3` theo bài báo) |

### 2.2. `summary_metrics` (Tóm tắt Chỉ số)
| Trường | Kiểu dữ liệu | Mô tả |
|---|---|---|
| `total_queries` | int | Tổng số câu hỏi đã chạy |
| `accuracy` | float | Tỷ lệ chính xác (%) tính theo Judge LLM |
| `error_rate` | float | Tỷ lệ câu trả lời sai khẳng định (%) |
| `neither_rate` | float | Tỷ lệ từ chối/không biết (%) |
| `avg_exact_match` | float | Điểm Exact Match trung bình (0.0 - 1.0) |
| `avg_token_f1` | float | Điểm F1-Score trung bình (0.0 - 1.0) |
| `avg_latency_seconds` | float | Thời gian phản hồi trung bình mỗi câu (giây) |

### 2.3. `results[]` (Chi tiết từng Query)
Mỗi phần tử trong mảng `results` đại diện cho một câu hỏi:

```json
{
  "query_id": "q_0",
  "query": "Did Adam Smith send a message to Li Hua about the upcoming building maintenance schedule before the administrators announced a temporary change in the construction schedule due to weather conditions?",
  "query_type": "Multi",
  "ground_truth": "Yes",
  "generated_answer": "Yes, Adam Smith sent a message regarding the schedule prior to the announcement.",
  "is_correct": true,
  "retrieved_evidence": [
    {
      "rank": 1,
      "chunk_id": "chunk_102",
      "doc_name": "20260121_10:00.txt",
      "content": "Adam Smith sent a notice to Li Hua on Monday...",
      "score": 0.85
    }
  ],
  "evaluation": {
    "exact_match": 1,
    "token_f1": 0.82,
    "judge_passes": ["accurate", "accurate", "accurate"],
    "final_verdict": "accurate"
  },
  "performance": {
    "latency_seconds": 2.14,
    "input_tokens": 42,
    "output_tokens": 16
  },
  "failure_analysis": {
    "stage": null,
    "error_type": null,
    "note": ""
  }
}
```

---

## 3. Quy ước Trạng thái Đánh giá (Evaluation Verdicts)

Theo đúng định nghĩa của bài báo MiniRAG:
- `"accurate"`: Câu trả lời truyền tải đúng ý nghĩa của Ground Truth (kể cả khác cách diễn đạt hoặc chi tiết hơn).
- `"error"`: Khẳng định sai nội dung mà không thể hiện sự không chắc chắn (hallucination/bịa đặt).
- `"neither"`: Trả lời không biết, từ chối trả lời, hoặc lạc đề.
- `is_correct`: `true` nếu `final_verdict == "accurate"` hoặc `exact_match == 1` / `token_f1 > 0.5`.
