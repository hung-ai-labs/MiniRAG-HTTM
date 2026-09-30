# MiniRAG-HTTM — đã cải tiến những gì, và tốt hơn bản gốc bao nhiêu

> Cập nhật 30/09/2026. Mọi con số trong file này tính lại trực tiếp từ file phán quyết trong `logs/`.
> Script kiểm: xem mục [Tái lập](#tái-lập) ở cuối.

---

## 1. Tóm tắt một trang

**Hệ thống chính thức hiện tại là `B2`.** So với MiniRAG gốc chạy trên cùng đồ thị, cùng model sinh, cùng giám khảo,
cùng ngân sách token:

| | MiniRAG gốc | **B2 (của nhóm)** | Chênh |
|---|---:|---:|---:|
| **accuracy** | 49,89 | **73,95 ± 2,21** | **+24,06** |
| error | 28,05 | 19,54 | −8,51 |
| neither ("không biết") | 22,07 | 6,51 | −15,56 |
| Single (347 câu) | 50,14 | **80,79** | +30,65 |
| Multi (43 câu) | 23,26 | **35,66** | +12,40 |
| **Null (45 câu)** | **73,33** | **57,78** | **−15,55** ⚠ |

*435 câu ngoài dev set, 3 lượt sinh độc lập (seed 101/202/303), phán quyết đa số 3 lượt chấm.*

**Kiểm định ghép cặp McNemar so với bản gốc, từng lượt sinh riêng:**

| Lượt | sai→đúng | đúng→sai | net | p |
|---|---:|---:|---:|---|
| 1 | 129 | 26 | **+103** | 1,3 · 10⁻¹⁷ |
| 2 | 126 | 30 | **+96** | 3,4 · 10⁻¹⁵ |
| 3 | 139 | 24 | **+115** | 6,9 · 10⁻²¹ |

Cả ba lượt cùng dấu, cùng độ lớn, p nhỏ hơn ngưỡng nhiều bậc. **Đây không phải nhiễu.**

**Nhưng phải nói kèm:** nhóm câu **Null** (câu mà đáp án đúng là *"không đủ thông tin"*) **tụt 15,55 điểm**.
Hệ thống tìm được nhiều bằng chứng hơn nên nó "dám trả lời" nhiều hơn — đúng ở câu có đáp án, nhưng ở câu không có
đáp án thì nó ghép mảnh và đoán. Đây là **đánh đổi đã biết**, đã điều tra kỹ, chưa khắc phục được. Chi tiết ở mục 5.

---

## 2. Cải tiến đã áp dụng

### 2.1 Sửa lỗi trong bản gốc (finding, không tính là đóng góp)

| Lỗi | Hậu quả | Đã sửa |
|---|---|---|
| **Bug O(N²) trong `ainsert`** | chèn N tài liệu thì trích xuất lại toàn bộ corpus N lần → ~68.000 lời gọi LLM cho 267 tài liệu | checkpoint `extracted_chunks.json` → **653 lời gọi** (giảm 99%) |
| **`Sources` không bị giới hạn token** | context trung vị **22.839 token**, max 33.412 → tràn cửa sổ 32k của Qwen2.5-3B ở 5–8% câu | **A1@4000** — cắt Sources ở 4.000 token; trung vị còn 3.743 |
| **Lỗi hoa/thường trong `get_node_from_types`** | cơ chế answer-type khớp **0 node** trên mọi truy vấn | đã vá: khớp **49 node**. Nhưng điểm **không** tăng (net −5, p = 0,583) → ghi nhận là **kết quả phủ định** |

### 2.2 Đóng góp chính: trộn xếp hạng bằng RRF

MiniRAG gốc xếp hạng chunk **chỉ bằng đường đi trên đồ thị** (`kwd2chunk`). Chunk mà vector tìm được nhưng không nằm
trên đường đi nào thì **không bao giờ** vào context.

| Phiên bản | Cơ chế | acc (435 câu) |
|---|---|---:|
| MiniRAG gốc | đồ thị | 49,89 |
| **V3** | RRF(đồ thị, vector), k=60 | 60,84 ± 2,07 |
| **B2 ← đang dùng** | **RRF(vector top-30, BM25 top-30), k=60** | **73,95 ± 2,21** |

`k = 60` lấy mặc định của Cormack 2009, **không tinh chỉnh**.

**Ba phiên bản cho ba kết luận khác nhau, và phải nói cả ba:**
- V3 chứng minh trộn xếp hạng có tác dụng (+10,95 so với gốc).
- Nhưng **ablation vector thuần** đạt 65,20 — **ngang V3** (80/61, p = 0,13). Nghĩa là **không chứng minh được đồ thị
  đóng góp gì** cho phần xếp hạng chunk. Không được viết "trộn giữ lợi thế đồ thị".
- B2 bỏ hẳn đồ thị khỏi xếp hạng chunk, thay bằng BM25 trên nguyên câu hỏi → tốt nhất. Đồ thị vẫn chạy để dựng bảng
  Entities, nhưng **không** tham gia xếp hạng chunk.

### 2.3 Hiệu năng: cắt tỉa đường đi (P1)

Phát hiện: **22.879 đường đi** được sinh mỗi truy vấn, **96% vô ích**.

| | trước | sau |
|---|---:|---:|
| số đường đi | 19.678 | **3.926** (−80%) |
| thời gian truy hồi | 5.239 ms | **1.035 ms** (−80%) |
| điểm QA | — | **không đổi** |

Giữ ≤ 60 đường mỗi seed. Đây là cải tiến **Efficiency thuần**, không đổi chất lượng.

### 2.4 Hợp nhất thực thể trùng tên (E1)

Gộp node trùng tên: 1.556 → 1.538 node. Kết quả: `graph_top30` net −1 (**trượt cổng**), `final_chunks` sau RRF net 0.
→ **Kết quả phủ định**, không bật.

---

## 3. Benchmark đầy đủ

### 3.1 So với bản gốc (435 câu ngoài dev — kết quả chính)

Đã nêu ở mục 1.

### 3.2 So với bảng trong bài báo MiniRAG

| | acc | err | neither | acc/(acc+err) |
|---|---:|---:|---:|---:|
| *Bài báo — Qwen2.5-3B (GPT-4o chấm)* | *48,75* | *26,02* | *25,23* | *65,20* |
| Bản tái tạo của nhóm (637 câu) | 51,02 ± 0,42 | 27,66 | 21,31 | 64,84 |
| **B2** | **73,95** | 19,54 | 6,51 | **79,10** |

⚠ **So với bài báo là tham chiếu, KHÔNG phải đối chứng**: khác giám khảo (Gemini Flash-Lite thay GPT-4o), khác đồ thị
(Qwen dựng 1.556 node, đã vá bug O(N²)), có thêm A1@4000 và bản vá answer-type. Bản tái tạo cao hơn bài báo 2,27 điểm
acc nhưng `acc/(acc+err)` **bằng nhau** — toàn bộ chênh lệch là `neither` chuyển sang trả lời.

### 3.3 Chất lượng truy hồi — **đo trực tiếp, 180 câu dev có Evidence**

Đây là chỗ cải tiến nằm. Cột Evidence chỉ dùng để **chấm điểm**; hệ thống lúc chạy không hề đọc nó.

| Chỉ số | MiniRAG gốc | **B2** | chênh |
|---|---:|---:|---:|
| Chunk cần lấy **tìm ra được** (có trong ứng viên) | 62,3% | **98,1%** | **+35,7** |
| Chunk cần lấy **giữ được** (vào Sources sau khi cắt) | 46,4% | **86,0%** | **+39,6** |
| Câu lấy **đủ mọi** chunk cần — trong ứng viên | 57,8% | **97,8%** | +40,0 |
| Câu lấy **đủ mọi** chunk cần — sau khi cắt | 41,7% | **83,9%** | **+42,2** |
| Độ chính xác Sources (chunk đúng / chunk lấy) | 8,0% | **15,0%** | +7,0 |
| Hạng trung vị của chunk cần lấy | 3 | **2** | −1 |
| Số chunk ứng viên (trung vị) | 30 | 47,5 | +17,5 |
| Số chunk vào Sources (trung vị) | 6 | 7,5 | +1,5 |

**Câu chuyện gọn trong một dòng:** bản gốc **tìm không ra** 37,7% chunk chứa bằng chứng (vì chunk nào không nằm trên
đường đi đồ thị thì không bao giờ được xét), và trong số tìm ra được lại **cắt mất** thêm một phần. B2 tìm ra 98,1% và
giữ được 86,0% — **cùng ngân sách 4.000 token, cùng model sinh, cùng giám khảo**.

Chạy lại bảng này: `.venv/bin/python reproduce/demo/so_sanh_chunk.py --acc`

### 3.4 Kịch bản demo trước hội đồng

```bash
# 1) bảng % truy hồi — mở đầu bằng con số
.venv/bin/python reproduce/demo/so_sanh_chunk.py --acc

# 2) chế độ hỏi đáp: gõ số câu, hoặc gõ từ khoá để tìm câu
.venv/bin/python reproduce/demo/so_sanh_chunk.py

# 3) bảng benchmark accuracy đầy đủ
.venv/bin/python reproduce/demo/bang_benchmark.py
```

Trong chế độ hỏi đáp, mỗi câu hiện cho **cả hai bên**: số chunk ứng viên, số chunk vào Sources, **thứ hạng** của từng
chunk cần lấy, tỉ lệ lấy đúng, câu trả lời và phán quyết. Lệnh `win` / `lose` / `null` / `multi` để lọc.

**Bốn câu đã kiểm tay, dùng được an toàn** (bản gốc trượt, B2 đúng, và câu trả lời thật sự đúng):

| # | Câu hỏi | Gốc | B2 |
|---|---|---|---|
| **3** | *Which game does Ileana mention for its unique world and storytelling?* | 0/1 chunk · trả lời "The Last of Us" ❌ | chunk hạng #2 · **"Horizon Zero Dawn"** ✓ |
| **5** | *Which game's narrative does Bronwyn appreciate for its father-son dynamic?* | 0/1 chunk | **"God of War"** ✓ |
| **12** | *Who offers to help with setting up for the garage sale?* | 0/1 chunk | **"AdamSmith"** ✓ |
| **25** | *Which character does LiHua mention as their favorite…?* | 0/1 chunk | **"Galadriel"** ✓ |

⚠ **Đừng dùng câu 4, 16, 22, 23, 45 làm ví dụ.** Chúng được giám khảo chấm `accurate` nhưng đọc kỹ thì câu trả lời sai
hoặc thiếu chi tiết — ví dụ câu 45 hỏi khoảng cách có hơn 3 ngày không (đáp án *Yes*, hai mốc 10/11 và 16/11 cách nhau
6 ngày) mà B2 trả lời *"No, less than three days"* vẫn được chấm đúng. Đây là **điểm yếu đã biết của giám khảo**
(ROADMAP mục 7: 13/40 câu được chấm đúng vẫn chứa ngày/thứ tự/người nói mâu thuẫn với Sources). Nếu thầy hỏi, đây là
câu trả lời trung thực: *accuracy đo được có thể cao hơn độ trung thành thực tế, và điều đó đúng cho **cả** bản gốc lẫn
bản cải tiến, nên phép so sánh vẫn công bằng.*

---

## 4. Những hướng đã thử và **thất bại** (kết quả phủ định)

Phần này quan trọng ngang phần thành công: nó cho thấy các lựa chọn đã được kiểm, không phải đoán.

| Hướng | Kết quả | Vì sao dừng |
|---|---|---|
| **Cắt vách (V2)** | acc 45,41 · 64/100, p = 0,006 | hại thật, do chính bước cắt vách |
| **RRF @2000 token (V4)** | 52,28 · so V3: 37/100, p = 7·10⁻⁸ | lợi ích của RRF **gắn với ngân sách 4.000** |
| **Bản vá answer-type** | net −5, p = 0,583 | sửa lỗi thật nhưng điểm không tăng |
| **Hợp nhất thực thể (E1)** | net −1, trượt cổng | không cải thiện |
| **5 hướng sửa Null** (A3, V5a–V5e) | đều phủ định | hướng verifier/từ chối **đã đóng** |
| **Xếp hạng lại tất định** (9 tín hiệu) | tín hiệu tốt nhất chỉ chạm 9/20 ca | và đồng thời đẩy bằng chứng gần giống lên đầu ở 15–16/20 câu Null |
| **Cửa sổ trong chunk dài (W=400)** | trượt 3/6 cổng | sự kiện phân biệt ở câu Null +33% |
| **Overflow-rescue** | độ phủ 5/25 ca | trần +1,6 điểm — dưới sàn nhiễu 1,5 điểm |
| **CE1 — cross-encoder xếp lại toàn bộ** | canary PROMOTE, **dev200 STOP** | trượt cổng chi phí: 5/200 câu vượt 3000 ms/câu trên CPU |
| **CE3 — ONNX Runtime** | tái hiện CE1 **chính xác** (chênh điểm 1,6·10⁻⁵) | nhưng **chậm hơn 2,71×** trên CPU arm64 |
| **CE-lite — xếp lại 25 ứng viên đầu** | giữ 11/11 ca CE1 cứu, giảm nửa p50/p95 | **canary STOP** — đuôi max 7162 ms, vẫn trượt cổng chi phí |

Chi tiết: `logs/retrieval_audit/README.md`, `logs/rerank/CE1_DEV200.md`, `logs/rerank/CE_LITE_CANARY.md`.

---

## 5. Điểm yếu đã biết: nhóm Null

**Null tụt 73,33 → 57,78 (−15,55 điểm).** Đây là điểm yếu thật, đã điều tra 5 vòng:

1. **Không phải do nhãn sai.** Kiểm toán 65 câu Null: 1 câu nhãn sai rõ ràng, 2 câu đáng tranh luận. Bỏ cả 3 câu chỉ
   thu hẹp chênh lệch 0,7–1,5 điểm.
2. **Không phải do rubric giám khảo.** Chấm lại bằng rubric làm rõ (khớp người 38/40 so với 15/40 của rubric gốc):
   khoảng cách Null so với bản gốc **vẫn còn** (net −5,67 so với −6,00).
3. **Cơ chế:** hệ thống truy hồi tốt hơn → nhiều "sự thật gần giống" trong context hơn → model ghép thành câu trả lời
   tự tin nhưng sai tiền đề. 19/32 câu Null bị chấm `error` là dạng này.
4. **Tín hiệu "độ phủ tiền đề"** đạt AUC 0,85 (cao hơn mọi tín hiệu cũ ≤ 0,65) nhưng làm cổng từ chối thì net oracle = 0
   ở **mọi** ngưỡng. Câu Null độ phủ thấp thì model đã tự từ chối đúng; câu Null model trả lời sai lại là loại độ phủ cao.
5. **Kết luận:** chưa có cách sửa nào đứng vững. Đây là **đánh đổi**, không phải bug.

**Cách trình bày đúng:** *"Cải thiện tổng thể +24 điểm đến từ nhóm câu có đáp án; nhóm Null đi ngược 15,5 điểm và
chúng tôi chưa khắc phục được. Chúng tôi đã loại trừ nhãn sai và rubric làm nguyên nhân chính."*

---

## 6. Giới hạn bắt buộc ghi khi trình bày

- **Một model sinh** (Qwen2.5-3B), **một đồ thị** (do Qwen dựng, 1.556 node, 46% node cô lập), **một giám khảo**
  (Gemini Flash-Lite, không phải GPT-4o như bài báo).
- **Nhiễu giữa các lượt sinh lớn hơn nhiễu giám khảo**: sd acc 2,09 trên 435 câu (giám khảo 0,30). Vì vậy mọi kết quả
  chính đều chạy **3 lượt sinh**.
- **Multi không lặp lại được ổn định** ở V3 (43,75 / 32,29 / 30,21) — không được viết "cải thiện Multi-hop" cho V3.
  B2 thì Multi 35,66 ổn định hơn nhưng n = 43, vẫn nhỏ.
- **Không chứng minh được đồ thị đóng góp** cho xếp hạng chunk (ablation vector thuần ngang V3).
- Đồ thị **thưa hơn upstream** do vá bug O(N²) — upstream trích xuất lặp nên vô tình gom thêm entity.
- Lợi ích của RRF **gắn với ngân sách A1@4000**; hạ xuống 2.000 thì mất hết.

---

## 7. Tái lập

```bash
# bảng benchmark chính (435 câu ngoài dev, 3 lượt sinh)
.venv/bin/python reproduce/demo/bang_benchmark.py

# so sánh chunk giữa bản gốc và B2 cho từng câu (demo)
.venv/bin/python reproduce/demo/so_sanh_chunk.py
```

| Dữ liệu | File |
|---|---|
| phán quyết bản gốc | `logs/qwen637_fix_judged.csv` |
| phán quyết V3 × 3 lượt | `logs/qwen637_v3{,_r2,_r3}_judged.csv` |
| phán quyết B2 × 3 lượt | `logs/stage_d/b2_s{101,202,303}_judged.csv` |
| context bản gốc (dev 200) | `logs/retrieval_audit/goc_dev_ctx.jsonl` |
| context B2 (dev 200) | `logs/retrieval_audit/vector_bm25_dev_ctx.jsonl` |
| kiểm toán truy hồi | `logs/retrieval_audit/README.md` |
| tầng D | `logs/stage_d/stage_d_report.json` |
