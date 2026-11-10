# MiniRAG theo đúng bài báo — cài đặt cần tái tạo ("C-paper")

Nguồn: `miniRAG1.pdf` (ACL 2026, tr. 37121–37144): §3.1–3.2 (tr. 37123–37126), §4.1 (tr. 37126), §4.4 (tr. 37128),
Phụ lục A.3 (tr. 37134), B (tr. 37136–37141). Đọc kèm [PAPER_CODE_AUDIT.md](PAPER_CODE_AUDIT.md) (code công bố lệch ở đâu).
Viết 09/11/2026.

## 1. Index (§3.1, Phụ lục B)

| Mục | Bài báo | Index của nhóm |
|---|---|---|
| Chunk | 1.200 token, chồng 100 token | Giống (mặc định code) |
| Vector store | nano vector base | Giống |
| Embedding | all-MiniLM-L6-v2 | Giống |
| Prompt trích xuất | `entity_extraction` (tr. 37137–37139): thực thể + mô tả, quan hệ + mô tả + keywords + strength, content keywords | Giống prompt code |
| Node | **Chunk node V_c** + entity node V_e | Code chỉ có entity node; chunk là thuộc tính `source_id` |
| Cạnh | E_α (entity–entity), **E_β (entity–chunk) có mô tả d_eβ** = "mô tả của thực thể" sinh từ chunk đó | Không có cạnh E_β |

**d_eβ dựng lại được không cần index lại:** mô tả của node được lưu theo từng chunk, nối bằng `<SEP>`, song song với
`source_id`. Khớp 1–1: **Qwen 1.400/1.556 node (90,0%), Phi 3.549/3.684 (96,3%)**; 3.851 / 6.067 cặp entity–chunk.
Node không khớp (do gộp trùng): dùng toàn bộ mô tả làm d_eβ cho mọi chunk của node — ghi vào Limitations.
Không có prompt riêng nào cho d_eβ trong phụ lục.

## 2. Truy hồi (§3.2)

1. **Query → từ khoá** bằng SLM (`query_to_keyword`, tr. 37139–37141): `answer_type_keywords` (≤ 3, chọn từ answer
   type pool) + `entities_from_query`.
2. **Seed V̂_s:** so embedding với entity node, "examining various text corpora (i.e., entity names, chunk content)"
   (tr. 37124). **V̂_a:** node đáp án theo kiểu dự đoán, **lấy từ tập khởi đầu** (code lọc toàn đồ thị — audit #2).
3. **Ê_α — Eq. (2):** ω_e(e) = Σ_{v̂∈V̂_s∪V̂_a} count(v̂, Ĝ_{e,k}); chọn các cạnh điểm cao nhất (đã cài: EQ2).
4. **Đường đi — Eq. (3):** mọi đường không lặp **độ dài n** từ seed; ω_p = ω_v(v̂_s|v_q)·(1 + Σ_{e∈p∧Ê_α} ω_e(e) +
   Σ_{v∈p∧V̂_a} count(v,p)); giữ **top-k đường cho mỗi cặp (query entity, seed)** (đã cài một phần: EQ3, k = 50, n = 2).
5. **Chunk:** V_c^q = mọi chunk node nối với entity trên các đường giữ lại.
   - **Step 1 Candidate Filtering:** lấy giao **V̂_c ∧ V_c^q** (V̂_c: chunk khớp ngữ nghĩa với câu hỏi ở bước 2;
     code thay bằng thưởng ×10 cho top vector — audit #6).
   - **Step 2 Similarity:** độ tương đồng embedding giữa câu hỏi và **chunk ghép các mô tả cạnh d_eβ của nó**
     (code không có — audit #7).
   - **Step 3:** xếp theo điểm Step 2, lấy top.
6. **Context sinh:** Ê_α (quan hệ) + V̂_c^q (chunk) + V̂_a (node đáp án); prompt `minirag_response` (tr. 37141).

## 3. Tham số (Phụ lục A.3, B)

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| top-k tài liệu cuối | **5** | "configure the top-k retrieval to 5 documents" |
| Giới hạn token | **6.000** | 5 × chunk 1.200 ≈ 6.000 |
| k (số hop của Ĝ_{e,k} **và** số đường top-k) | **10** (suy ra) | Bảng A3 dòng k=10 (54/34) trùng Bảng A4 dòng n=4 (54/34) ⇒ cấu hình mặc định là k=10, n=4. Bài không ghi thẳng |
| n (độ dài đường) | **4** | "n should be kept at a moderate value (e.g., n = 4)" |
| Reranker | Không | §4.1 |

Lưu ý: EQ3 đã đăng ký K = 50 (lấy mức cao nhất của A3) và giữ n = 2 của code — khác bộ (10, 4) suy ra ở đây.

## 4. Đánh giá (§4.1, A.4, B)

- acc = câu trả lời nhất quán với đáp án (tương đương ngữ nghĩa được chấp nhận); err = trả lời sai mà không nhận ra.
- Giám khảo **GPT-4o**, prompt `gpt-4o_judge` (tr. 37141): **một lần gọi chấm ba câu trả lời** của ba hệ thống, điểm
  1 / 0 / −1; lặp **3 lần, xáo thứ tự**, báo trung bình và phương sai. Nhóm thay GPT-4o bằng Gemini Flash-Lite
  (cùng giao thức, `Step_2_evaluate.py`) — hằng số giữa mọi cột.
- Phần cứng bài báo: 4× RTX 3090.

## 5. Ablation của bài báo (Bảng 2, §4.4)

| Dòng | Nghĩa |
|---|---|
| −I | Thay đồ thị dị thể bằng index dựa trên mô tả kiểu LightRAG/GraphRAG |
| −R_chunk | Bỏ chunk node khi truy hồi |
| −R_edge | Bỏ thông tin cạnh |

## 6. Mâu thuẫn trong chính bài báo (ghi khi trích)

- Qwen2.5-3B LiHua: Bảng 1 = 46,78; Bảng 2 = 46,93.
- Bảng A3/A4 cho acc 48–64% nhưng không nói model/dataset; cao hơn mọi dòng SLM ở Bảng 1.
- §3.1 nói SLM sinh d_eβ, nhưng phụ lục không có prompt nào cho việc đó; §4.3/4.4 lại nói MiniRAG *không* dựa vào
  mô tả ("−I" là thêm index dựa trên mô tả).
