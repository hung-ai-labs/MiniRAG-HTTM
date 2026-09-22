# CE3 + CE4 — làm rẻ đường xếp lại trên CPU: backend thất bại, CE-lite đạt

> 21/09/2026 · Đăng ký trước: [`CE3_cpu_backend.md`](../../reproduce/rerank/preregistration/CE3_cpu_backend.md) (`7fa1e47`)
> và [`CE4_celite.md`](../../reproduce/rerank/preregistration/CE4_celite.md) (`e8cb2c7`), cả hai viết **trước** khi đo
> chỉ số tương ứng. Chỉ offline: **0 lời sinh, 0 lời chấm**, không 637, không tầng D.
> **Không mở lại hướng xếp hạng lại tất định.** Kết quả CE1 và quyết định STOP ở tầng dev **giữ nguyên là lịch sử**.

## Phase 0 — mốc xác nhận lại từ hiện vật đã lưu (không dựng lại gì)

B2 đông lạnh hash trùng **198/198** · model `cross-encoder/ms-marco-MiniLM-L6-v2` @ `233902d25c44…` · BertTokenizer ·
MaxP `512−len(q)−3`, bước cửa sổ/2 · lô 32 · CPU float32 · 20 ca độ sâu xếp hạng, CE1 cứu **11** ·
giữ đủ bằng chứng **151 → 162** · độ trễ CE1 p50 1830 / p95 2731 / **max 3429** ms, 5/200 câu vượt 3000.

## Phase 1 (CE3) — ONNX Runtime: tương đương hoàn hảo, nhưng **chậm hơn**

Backend chốt trước: ONNX Runtime 1.30.0, **chỉ `CPUExecutionProvider`** (CoreML bị cấm theo đăng ký trước — dùng nó
tương đương lén chuyển sang GPU để cứu số CPU), float32, opset 17, `ORT_ENABLE_ALL`, 6 luồng, lô 32, MaxP không đổi.

**Tương đương — nhóm A, mức tốt nhất có thể:**

| | |
|---|---|
| điểm từng chunk, 9.351 cặp | max \|Δ\| **1,597e−05** · p99 7,6e−06 · vượt 1e−3: **0** |
| thứ tự sau xếp lại | trùng **200/200** |
| `chunk_ids` sau A1@4000 | trùng **200/200** |
| chồng lấp top-10 | **1,0000** ở mọi câu |
| hash context | sẽ trùng **200/200** (selftest mục 9 đã chứng minh CE1 offline ≡ CE1 runtime) |

**Độ trễ — trượt, và trượt theo chiều ngược:**

| | p50 | p95 | max | vượt 3000 |
|---|---:|---:|---:|---:|
| CE1 PyTorch CPU | 1830 ms | 2731 ms | 3429 ms | 5/200 |
| CE3 ONNX CPU | **4958 ms** | **7579 ms** | **13110 ms** | **172/195** |

**Chậm hơn 2,71× ở p50, 3,82× ở max.** Nạp session 76 ms (đo riêng), RSS tăng ~2963 MB, file ONNX 58 KB + trọng số
ngoài `ce1_minilm_l6.onnx.data` 90,9 MB.

Export **không** hỏng: điểm khớp tới 1,6e−05 chứng minh đồ thị đúng. Đây là kết quả thật của backend — kernel CPU arm64
của ORT chậm hơn ATen của PyTorch trên máy này. Theo CE3: **không** thử INT8, **không** thử backend thứ hai, đi thẳng
sang Phase 2.

## Phase 2 (CE4) — CE-lite

**Luật đã chốt:** xếp lại bằng **đúng model CE1** chỉ **25 ứng viên đầu theo thứ tự RRF**; phần còn lại giữ thứ tự RRF
và nằm sau tiền tố; rồi **A1@4000 như cũ**. Chọn N = 25 theo luật phát biểu trước *"tiền tố nhỏ nhất nơi độ phủ bão hoà"*
(25 và 30 cùng cho 11/11 và 16/20) — không phải N làm chỉ số cuối đẹp nhất. Phần thăm dò (`celite_coverage.txt`) chỉ đo
độ phủ và chi phí, không đo chỉ số xác nhận.

### Phase 2A — chi phí và giữ bằng chứng

| | |
|---|---|
| ứng viên xếp lại/câu | 46,8 → **25,0** (53%) |
| cửa sổ MaxP/câu | 93,6 → **52,5** (56%) |
| ước tính tuyến tính | max ≈ 1922 ms |
| ~~**đo thật trên CPU** (n=195)~~ | ~~p50 845 · p95 1507 · max 1708 ms · 0 câu vượt 3000~~ **← SỐ NÀY SAI, xem đính chính** |
| 11 ca CE1 cứu được | **11/11 còn cứu**, **thêm 1 ca** CE1 không cứu được |

> ## ⛔ ĐÍNH CHÍNH 22/09/2026 — phép đo độ trễ ở trên KHÔNG so được
>
> Con số `p50 845 · p95 1507 · max 1708` đo bằng **vòng lặp tách rời** (`celite_eval.measure_latency`), chỉ chạy
> reranker, không có phần còn lại của pipeline. Nhưng con số của CE1 (`p50 1830 · p95 2731 · max 3429`) lấy từ
> `rerank_ms` ghi **trong pipeline**. Tôi đã so hai loại đo khác nhau và kết luận "max 1708 ms, dưới mốc 3000" —
> **kết luận đó không đứng vững**.
>
> Đo lại công bằng, cả hai **trong pipeline**, cùng cách dựng lại dev 200 (`celite_latency_fair.txt`):
>
> | | p50 | p95 | max | vượt 3000 |
> |---|---:|---:|---:|---:|
> | CE1 đầy đủ | 1830 ms | 2731 ms | 3429 ms | 5/200 |
> | **CE-lite** | **970 ms** | **1725 ms** | **5246 ms** | 1/200 |
>
> CE-lite **giảm một nửa p50 và p95** nhưng **đuôi max xấu hơn CE1** (5246 so với 3429). Đuôi bị chi phối bởi tải máy
> chứ không phải khối lượng của reranker. Kết luận "đạt mốc vận hành" ở mục 7 bảng quyết định CE4 vì thế **sai** —
> xem `logs/rerank/CE_LITE_CANARY.md`.

**Bảng chính**

| Chỉ số | B2 | CE1 đầy đủ | **CE-lite** |
|---|---:|---:|---:|
| đủ bằng chứng (180 câu có evidence) | 151/180 | 162/180 | **163/180** |
| đáp án nguyên văn trong Sources (94) | 82/94 | 87/94 | **87/94** |
| trong 20 ca độ sâu: đủ bằng chứng | 0/20 | 11/20 | **12/20** |
| Single đủ bằng chứng | 136/159 | 146/159 | **147/159** |
| Multi đủ bằng chứng | 15/21 | 16/21 | **16/21** |
| token Sources trung vị | 3602 | 3600 | 3712 (+3,1%) |
| token Sources max | 4000 | 3999 | **3999** |
| số chunk Sources trung vị | 8 | 6 | 6 |
| sự kiện phân biệt Null, trung vị | 10,5 | 7,5 | 7,5 |
| xếp lại ms/câu p50 | 0 | 1830 | **845** |
| xếp lại ms/câu max | 0 | 3429 | **1708** |

**Chuyển dịch giữ bằng chứng**

| | mất→giữ / giữ→mất | net | p |
|---|---|---:|---:|
| CE-lite so với **B2**, đủ bằng chứng | 17 / 5 | **+12** | 0,017 |
| — Single | 15 / 4 | +11 | |
| — Multi | 2 / 1 | +1 | |
| CE-lite so với B2, đáp án nguyên văn | 8 / 3 | +5 | 0,23 |
| CE-lite so với **CE1**, đủ bằng chứng | 1 / 0 | +1 | 1,0 |
| CE-lite so với CE1, đáp án nguyên văn | 0 / 0 | 0 | 1,0 |

**Ca CE-lite cứu thêm:** *"What type of instrument does Li Hua play in the basement?"* — chunk đáp án hạng RRF 20, CE1
đẩy **xuống** 22, CE-lite đưa lên **15**. Cơ chế: tiền tố chặn không cho chunk ngoài top-25 nhảy lên chiếm chỗ.

### Phase 2B — an toàn Null (bắt buộc)

| | chunk mới vào | rời đi | câu có chunk mới khớp đủ thực thể |
|---|---:|---:|---|
| CE1 | 67 | 93 | **4/20** (cổng ≤ 7) |
| CE-lite | 55 | 73 | **4/20** (cổng ≤ 7) |

Sự kiện phân biệt trong Sources câu Null: trung vị **10,5 → 7,5**, giống CE1.

**⚠ Điểm CE-lite kém CE1:** có **2/20 câu Null** mà CE-lite kéo vào một chunk khớp đủ thực thể mà CE1 **không** kéo vào
(`20261221_12:00` ở hạng 9; `20260625_19:00` ở hạng 4). Tổng số câu chạm cổng vẫn là 4/20 nên cổng đạt, nhưng đây là
bằng chứng gần giống **nhiều hơn** CE1 ở hai câu — đúng cảnh báo "đừng giả định ít CE hơn thì an toàn hơn".

**Ba chunk gây nhầm** (luật tiến cứu CE2: THOÁI LUI chỉ khi bị **đẩy lên** so với B2):

| | B2 | CE1 | CE-lite | Sources CE-lite | |
|---|---:|---:|---:|---|---|
| L002 `20260112_10:00` | 8 | 3 | **3** | có | THOÁI LUI |
| L052 `20260214_16:00` (whey) | 1 | 1 | **1** | có | TRUNG TÍNH |
| L055 `20261113_13:00` | 4 | 16 | **9** | — (rời Sources) | CẢI THIỆN |

**THOÁI LUI 1/3, cổng ≤ 1 → đạt, hết dư địa.** L055 bị đẩy xuống ít hơn CE1 (9 so với 16) nhưng vẫn ra khỏi Sources.

## Đối chiếu luật quyết định CE4

| # | Điều kiện | Kết quả | |
|---|---|---|---|
| 1 | giữ phần lớn cải thiện truy hồi của CE1 | 163/180 so với CE1 162/180 và B2 151/180 | ĐẠT |
| 2 | giữ phần đáng kể trong 11 ca | **11/11** + 1 ca thêm | ĐẠT (dải "ứng viên mạnh") |
| 3 | Multi không tụt đáng kể offline | 16/21, net +1 so B2, net 0 so CE1 | ĐẠT |
| 4 | an toàn Null không xấu đi đáng kể | 4/20 (≤ 7) · thoái lui 1/3 (≤ 1) | ĐẠT, kèm cảnh báo 2 câu ở trên |
| 5 | ngân sách context không đổi | max 3999 ≤ 4000 · trung vị +3,1% (≤ ±5%) | ĐẠT |
| 6 | không thêm lời gọi LLM | 0 | ĐẠT |
| 7 | độ trễ CPU đạt mốc vận hành | ~~max 1708 ms~~ → đo lại trong pipeline **max 5246 ms** | **TRƯỢT** (đính chính 22/09) |

## CE-lite là biến thể truy hồi MỚI, không phải tối ưu triển khai

`chunk_ids` sau A1 của CE-lite chỉ trùng CE1 ở **102/200** câu. Đúng như CE4 đã ghi trước, nó **không** được gọi là
"vẫn là CE1", và bộ số an toàn offline ở trên chính là phân tích riêng của nó.

## Diễn giải được phép

> *"Xếp lại có chọn lọc bằng cross-encoder trên 25 ứng viên đầu giữ trọn mức cải thiện giữ bằng chứng của CE1 đầy đủ
> (163/180 so với 162/180, B2 151/180), giữ cả 11 ca độ sâu xếp hạng mà CE1 cứu được, và đưa chi phí CPU từ max 3429 ms
> xuống max 1708 ms — dưới mốc vận hành 3000 ms."*

**Không** được viết bất cứ điều gì về accuracy, ảo giác hay Null "đã được giải quyết". Toàn bộ số trên là **giữ bằng
chứng offline**. CE1 từng vượt canary rồi trượt dev ở cổng chi phí, và tín hiệu chất lượng của nó ở dev (net +7,
p = 0,324, một lượt sinh) **chưa bao giờ là bằng chứng cải thiện**.

## Giới hạn

- Dev 200, một tập; 20 ca độ sâu, 21 câu Multi, 20 câu Null — mẫu nhỏ ở đúng chỗ quan trọng.
- Chưa chạy sinh hay chấm. Không suy ra accuracy.
- Câu hỏi "Multi tụt vì thứ tự trình bày" từ canary CE1 **vẫn chưa được kiểm lại**, và CE-lite đổi thứ tự khác CE1 ở
  98/200 câu, nên nó **không** thừa hưởng kết quả canary của CE1.
- Độ trễ đo bằng đồng hồ tường trên máy cá nhân; đã đo CE-lite và CE1 cùng cấu hình luồng nhưng không cùng thời điểm.
- Nhãn "chunk gây nhầm" do một người đọc xác định, chưa ai rà lại.
- Một model, một revision, một chính sách cắt, một thiết bị, một giá trị N.
