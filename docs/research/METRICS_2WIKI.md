# Metrics judge offline — bản để review S-06

`reproduce/research/metrics.py` chạy Python 3.13.5; summarize dùng thư viện chuẩn, bootstrap dùng NumPy đã có trong venv. Không gọi LLM/API, không đọc .env, không sửa rubric hoặc MiniRAG.

## Đầu vào và đầu ra

- `summarize`: `--questions` CSV có query_id/Type (có thêm Question/Gold Answer cũng được, các trường text/gold không đi vào metrics); `--judge-csv` theo runner MultiHop với query_id, Type, pass1, pass2, pass3, majority; `--gen-repeat` là ID lượt sinh, ví dụ 101.
- `--run-manifest` tùy chọn để review offline; trước kết luận benchmark phải có đủ config_hash/index_hash/split_hash/rubric_version/judge_model. Các tên này là adapter contract cho metrics, chưa khẳng định runner hiện tại xuất sẵn mọi trường.
- Tạo một thư mục mới gồm long `per_question.csv` (query_id, Type, gen_repeat, judge_pass, status, label) và `metrics.json`.
- `compare`: nhận danh sách thư mục metrics baseline/variant. Ghép đúng gen_repeat và query_id; không ghép theo dòng hoặc câu hỏi. Từ chối bộ câu hoặc metadata judge/index/split/rubric khác nhau khi có provenance.
- Từ chối output đã tồn tại; tạo thư mục/run mới khi thay config. Mỗi input/output CSV và script được băm SHA-256.

## Hợp đồng số liệu

- Nhãn hợp lệ: accurate/error/neither. parse_failed, judge_failed, missing là lỗi riêng; không đổi thành neither. Nhãn lạ bị từ chối để không che lỗi upstream.
- Mỗi lượt judge: Acc/Err/Neither chia n_valid; báo n_expected, n_valid, n_parse_failed, n_infra_failed (judge API), n_missing. Đây chưa bao phủ infra của generation.
- majority tính lại từ ba pass và so với cột ghi sẵn. 1-1-1 là no_majority; pass lỗi/thiếu là incomplete.
- Tỷ lệ majority chia số câu có đủ ba phán quyết hợp lệ, gồm no_majority trong mẫu số và báo riêng. Nhãn no_majority được coi là không-accurate khi kiểm accurate-vs-không-accurate; incomplete loại khỏi cặp và đếm rõ.
- McNemar hai phía chính xác theo binomial, báo b_up/c_down/net/p và số cặp đủ/thiếu. error là biến phụ riêng.
- Bootstrap mặc định 10.000 lần, seed 13; lấy mẫu theo query, giữ toàn bộ các lượt sinh của query. Báo số câu đủ cả hai cấu hình trên mọi repeat, số bị loại và CI95 delta. Không dùng các verdict như mẫu độc lập.
- Judge mean/sd nằm trong từng repeat; generation mean/sd của delta nằm trong báo cáo compare. Không gộp chung một dấu +/-.
- Judge metrics không chứng nhận run completed. Early exits, generation failures, retrieval Evidence Recall, latency/token hiện là null vì CSV judge không cung cấp; cần logger adapter trước khi S-06 hoàn tất.
- `comparison_provenance_verified=false` nếu thiếu manifest/identity. Không dùng báo cáo đó như đối chứng đã khóa protocol.

## Lệnh mẫu cho run tương lai

Các đường dẫn dưới là placeholder cho artifact thật, chưa có run benchmark nào được thực hiện.

```bat
.venv\Scripts\python.exe reproduce\research\metrics.py summarize --questions <dev-questions.csv> --judge-csv <judge-per_question.csv> --gen-repeat 101 --run-manifest <run_manifest.json> --out <new-metrics-directory>
.venv\Scripts\python.exe reproduce\research\metrics.py compare --baseline <base101> <base202> <base303> --variant <b2-101> <b2-202> <b2-303> --out <new-comparison.json>
```

## Kiểm chứng đã thực hiện

17 test metrics chỉ dùng dữ liệu giả: ba nhãn/lỗi/missing, 1-1-1, type/ID/majority sai, exact binomial, bootstrap tái lập, tổng hợp tính lại, tampering, ba repeat giữ đúng hai query (không thành 6 hoặc 18 mẫu), khác model judge và thiếu manifest.

Chạy cùng bộ chuẩn bị dữ liệu: **24 passed** trên Python 3.13.5. Lệnh dùng `-p no:cacheprovider` để tránh cache pytest cũ có quyền sở hữu khác:

```bat
.venv\Scripts\python.exe -m pytest tests\research -q -p no:cacheprovider
```

Đây là test kỹ thuật, không phải số chất lượng của Qwen hoặc cải tiến B2. Chưa có kiểm chéo S-09 từ người còn lại.
