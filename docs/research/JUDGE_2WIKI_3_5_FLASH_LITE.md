# Judge 2Wiki đã chọn — 01/11/2026

**Rubric hiện hành:** `2wiki-upstream-aliases-v2`: nguyên văn JUDGE_PROMPT trong
Step_2_evaluate.py, chỉ append aliases, theo kế hoạch §B4. Đã loại bỏ câu chỉ
đạo "whole answer" do Codex thêm ngoài prompt gốc. Giữ nguyên smokeV1 và chấm
lại cùng answer ở `baseline-smoke-s101-fl35-v2`; không tự sửa phán quyết hoặc
khẳng định đổi prompt chắc chắn chữa mọi lỗi judge.

Theo tin nhắn nhóm do người dùng gửi, chốt **gemini-3.5-flash-lite**, không dùng
alias latest. Quyết định này thay yêu cầu Gemini Flash cũ của nhánh 2Wiki và
không thay judge cho LiHua/MultiHop-RAG hoặc sửa baseline.yaml.

- Google công bố model code này là stable:
  https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- Trang pricing công bố free tier cho input/output của model. Project/key cụ
  thể vẫn phải có quyền/quota free tier; không bật billing trả phí.
  https://ai.google.dev/gemini-api/docs/pricing
- Giữ rubric aliases, 3 lượt độc lập, shuffle và limiter hiện có. Không fallback
  sang latest hoặc model khác khi có lỗi.
- CLI judge_2wiki.py mặc định model này và từ chối model khác. Pipeline chỉ chấm
  khi có --judge-model gemini-3.5-flash-lite; bỏ flag thì vẫn chỉ QA như trước.
- Tên model cố định không tự chứng minh judge đúng. Đọc tay phán quyết smoke20
  trước chấm nhiều; ghi response_model, lỗi parse/API và mọi lần retry.

## Kiểm tra quyền API hiện tại

Cập nhật sau khi người dùng bổ sung8 key: 7/8 trả200 khi GET metadata model,
GEMINI_API_KEY_1 trảAPI_KEY_INVALID và đã được comment trong.env để giữ lại giá
trị nhưng không đưa vào pool. Chưa gọi inference hoặc xác minh quota/billing.
Quota tính theo project, không theo key:8 key cùng project không tạo8 lần quota.
https://ai.google.dev/gemini-api/docs/rate-limits

Metadata endpoint trả400, reason API_KEY_INVALID với key local tại thời điểm
kiểm tra ban đầu; chưa xác minh được quyền/quota project. Không ghi key vào report và
không gọi inference. Cần thay GEMINI_API_KEY bằng key thật từ Google AI Studio
(https://aistudio.google.com/apikey). Key Gemini không phải chuỗi tự tạo cho
MINIRAG_SLM_KEY. Không sửa MINIRAG_SLM_KEY/URL vì Qwen vẫn dùng chúng riêng.

## Chấm smoke sau khi có đủ20 answer và key hợp lệ

Lập kế hoạch/kiểm input trước, chưa gọi API:

```powershell
python reproduce/research/judge_2wiki.py --questions dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/smoke_dev20.csv --gold dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/smoke_dev20_gold.jsonl --answers runs/2wiki/modal/baseline-smoke-s101-c4/C0_s101/answers.jsonl --out runs/2wiki/judge/baseline-smoke-s101-fl35-v2 --model gemini-3.5-flash-lite
```

Thêm --execute mới gọi Gemini. Chưa thực thi khi key lỗi hoặc chưa xác minh
free-tier project. Không sửa rubric sau khi xem test, không thay model khi resume.
Lượt sinh Qwen và lượt judge khác nhau: một file answer được chấm3 lượt độc lập.

RUN_2WIKI_DEV20_TEST80.md và một số snapshot cũ còn placeholder/model family
trước quyết định; dùng model ID đã chốt tại đây cho mọi lệnh chấm2Wiki mới.
Giữ nguyên file registration đang được QA tham chiếu để tránh đổi hash giữa pha.
