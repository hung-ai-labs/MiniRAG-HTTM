# Graph repair — báo cáo giai đoạn 1: chẩn đoán

Ngày đo: 08–09/11/2026. Phạm vi: 180 câu dev LiHua-World có Evidence, 207 chunk đáp án theo `screen_variant.gold_map()`, đồ thị Qwen `LiHua-World-qwen-modal` (1.556 node, 1.509 cạnh), C0 graph-only, A1@4000. Không sinh câu trả lời, không chấm judge, không đo cơ chế mới. Mọi lần truy hồi dùng parser cache và embedding cục bộ; index gốc chỉ được đọc rồi sao sang thư mục tạm. Các lượt chạy lại sau sự cố RAM dùng **tối đa hai shard đồng thời, mỗi lần chỉ một cấu hình**.

## T0 — kiểm hồi quy

| Lượt | `chunk_ids` khớp C0 đóng băng | Log nội tại |
|---|---:|---:|
| DIAG tắt | 180/180 | Không ghi log DIAG |
| DIAG bật | 180/180 | 180 dòng, 180 câu duy nhất |

Mốc so là `logs/c_ablation/graph/C0/C0_records.jsonl`; kết quả từng câu ở `logs/graph_repair/phase1/t0_{off,on}/`. `t0_regression.json` liệt kê 0 câu lệch ở cả hai lượt. Sau T0 chỉ bổ sung `source_id` của seed cô lập vào trường reachable của DIAG; nhánh này không tham gia xếp hạng. Test DIAG tắt và test C-ablation qua bằng `unittest`: 9/9 và 4/4. Lệnh `python -m pytest ...` của brief không chạy được vì `.venv` thiếu `pytest` và không được tải gói qua mạng.

## T1 — tín hiệu nào thật sự đi đến Sources?

**D1.** Ghi đè `[a,e]` của đường đi thành `[0,0]` hoặc xáo trộn với RNG 13, sau `edge_vote_path`: cả hai lượt đổi **0/180** danh sách `chunk_ids` so với C0. Trong C0, `path2chunk` chọn Counter của đường cuối rồi chỉ chuyển ID sang `kwd2chunk`; nhân cả Counter đường cuối với một hệ số dương không đổi thứ tự nội bộ. Đây là kết quả trên luồng C0, không phủ định mọi công thức điểm khi có đường truyền điểm khác.

**D2.** Hai lượt có cùng 3.533.757 đường được chấm:

| Answer-type | `len(maybe_answer_list)` | Đường có `a>0` | `chunk_ids` khác FIX=1 |
|---|---:|---:|---:|
| `MINIRAG_ANSWER_TYPE_FIX=0` | trung vị 0; 140/180 câu bằng 0, 40 câu >0 | 227.623 | 0/180 |
| `MINIRAG_ANSWER_TYPE_FIX=1` | trung vị 142,5; min 1, max 627 | 1.137.821 | — |

Vì vậy lỗi so khớp hoa/thường làm mất tín hiệu ở phần lớn, **không phải toàn bộ**, câu trên tập này. Sửa nó thay đổi điểm đường đi nhưng không đổi Sources trong C0. Đây không phải bằng chứng tăng accuracy.

**D3.** Levenshtein chạy ở 180/180 câu: 1.694 lần gọi, 4.908 lượt loại, 3.542 cặp câu–chunk bị loại, gồm 48 ID chunk khác nhau trên toàn tập. Có 7 cặp câu–chunk đáp án ở 7 câu từng bị loại (12 lượt loại). Trong bảy cặp đó, hai vẫn tới Sources, một có ứng viên nhưng ngoài trần xếp hạng và bốn ở L1; việc từng bị lọc **không đồng nghĩa** bộ lọc là nguyên nhân duy nhất làm mất chunk.

**D4.** Có 26.807 seed ứng viên trước lọc đường ngắn; 9.513 bị loại (**9.513/26.807 = 35,486999664266794%**). Số seed hoạt động trung vị 96,5/câu. Top-1% là 16/1.556 node theo từng thước đo: 159/180 câu có seed trong top-1% bậc, 159/180 trong top-1% `df`, 160/180 trong hợp hai tập. `df` là số ID chunk khác nhau ở `source_id` của node.

## T2 — tầng đầu tiên làm mất từng chunk đáp án

L0 dùng hợp nguồn **node** trên mọi đường, gồm seed cô lập; nguồn **cạnh** ghi riêng. Log T0 được tạo trước khi trường reachable ghi thêm seed cô lập; `diagnose.py` bù nguồn của seed này trực tiếp từ GraphML chỉ đọc. L1 kiểm tập chunk có đóng góp trong `kwd2chunk` trước khi xếp hạng; L2 kiểm giới hạn graph top-30; L3 kiểm A1@4000. Mỗi chunk đáp án vào đúng một hàng. Cột “câu” đếm câu có ít nhất một chunk ở hàng đó nên các hàng có thể chồng nhau ở Multi.

| Tầng | Toàn bộ: chunk / câu | Single: chunk / câu | Multi: chunk / câu |
|---|---:|---:|---:|
| L0 `not_reachable` | 2 / 2 | 2 / 2 | 0 / 0 |
| L1 `reach_not_cand` | 70 / 69 | 58 / 58 | 12 / 11 |
| L2 `cand_not_top30` | 6 / 6 | 5 / 5 | 1 / 1 |
| L3 `top30_not_a1` | 33 / 31 | 25 / 25 | 8 / 6 |
| OK | **96 / 88** | 69 / 69 | 27 / 19 |

Tổng là 207 chunk ở 180 câu (Single 159 câu/159 chunk; Multi 21 câu/48 chunk). **75/180 câu** giữ đủ đáp án: Single 69/159, Multi 6/21. Con số OK 96/207 và 75/180 tái hiện C0 đóng băng. Tái dựng xếp hạng graph và danh sách sau A1 từ log khớp **180/180** mỗi bước; một ID graph không có trong kho text được bỏ qua đúng như runtime.

**L0.** Hai câu mất cùng `chunk-cac66d48bd38add0b88b9b8ec10aa122`. Chunk này không có trong `source_id` của **bất kỳ node hay cạnh nào** trong đồ thị; vì vậy không có thực thể sở hữu để tính hạng cosine, kiểm seed hay khoảng cách 2-hop. Đây là thiếu phủ đồ thị lúc dựng index, không phải bằng chứng rằng tăng hop sẽ cứu được.

**L1.** 60/70 chunk có trong Counter của đường cuối ở ít nhất một seed nhưng đứng ngoài top-3 của mọi seed đó (hạng tốt nhất trung vị 17,5; min 4). Mười chunk còn lại chỉ xuất hiện trong Counter cộng dồn mọi đường, không trong Counter đường cuối; **cả 10 vẫn ngoài top-3** khi dùng Counter cộng dồn. Xét toàn bộ L1, có 10 chunk đạt top-3 của một seed nếu dùng Counter cộng dồn, nhưng đó chỉ là trần cục bộ: còn phải qua `kwd2chunk` và A1. Levenshtein từng loại một số chunk đáp án nhưng không tạo nhóm nguyên nhân đơn nhất ở L1.

**L2/L3.** Sáu chunk L2 có hạng ứng viên 31–69 (trung vị 44,5); 33 chunk L3 có hạng 4–29 (trung vị 12). Top-1% node theo bậc **hoặc** `df` là hợp của hai danh sách 16 node; seed đóng góp lớn nhất thuộc hợp này chiếm **103.254/651.068 token** Sources được giữ. Hợp top-5% (78 node theo từng thước đo) chiếm **238.248/651.068 token**. Đây là phần token *được dùng*, gán cho seed có đóng góp lớn nhất mỗi chunk, không phải phép chứng minh hub gây mất đáp án. Trung vị tỉ phần theo câu lần lượt 0 và 0,36354038775299674. Các ID trước gold và seed đóng góp lớn nhất được ghi ở `t2_summary.jsonl` cho từng trường hợp.

**Phản thực tế hệ số hiện có.** Từ các đóng góp đã log, đặt riêng ×2 hoặc ×10 về 1 rồi xếp hạng lại; không chạy pipeline mới. Tái dựng thứ hạng gốc và A1 đều khớp 180/180 trước ablation:

| Bỏ hệ số | Câu đổi graph top-30 | Câu đổi Sources sau A1 | Chunk vàng lên / xuống sau A1 | Câu đủ đáp án lên / xuống |
|---|---:|---:|---:|---:|
| ×2 | 168 | 131 | 2 / 6 | 0 / 6 |
| ×10 | 180 | 162 | 6 / 41 | 5 / 30 |

Các hệ số quyết định thứ tự ở nhiều câu, nhưng bỏ riêng từng hệ số làm **hại retention ròng** trên tập này. Không dùng bảng này để đề xuất bỏ boost.

**Năm ca cụ thể** (hạng tính trên toàn tập ứng viên trước trần graph):

1. “Who does LiHua ask for help with installing a curtain?” — `chunk-cac66d48bd38add0b88b9b8ec10aa122`, L0. Không có node/cạnh sở hữu; không có seed chiếm chỗ có thể quy trách nhiệm.
2. “Did Adam Smith send Li Hua a reminder about the upcoming rent due date before Li Hua sent a message about having already transferred the rent on 20260301?” — `chunk-11f7713d2f099c989452a38b997d7e23`, L1. Seed `"ADAMSMITH"` giữ chunk ở hạng 65 trong Counter đường cuối (hạng 79 trong Counter mọi đường), ngoài top-3.
3. “Who offers to help with setting up for the garage sale?” — `chunk-eba0d93cacae52f0485016cffc855ef7`, L1. Seed `"GARAGE SALE"` có chunk ở hạng 4 của Counter mọi đường, nhưng đường cuối không có nó; ngay cả bản Counter cộng dồn vẫn thiếu một bậc để vào top-3.
4. “What does Emily think will happen next in the series in terms of story development?” — `chunk-29db8f2cea363e3ea7cf31601cf9fbbe`, L2, hạng 31. Phía trên có `chunk-2c5e5f4bb7bbe2044095b40d65eca145` do seed `"EMILYBURNETT"` đóng góp lớn nhất (14,219193458557129).
5. “What does LiHua say Cersei's power came at the price of?” — `chunk-0a2d4a40a78adcd43333ae04eb46fe71`, L3, hạng 5 nhưng A1 cắt. Phía trên có `chunk-953f8dd24048597751fbca446d7f5934` do `"CERSEI'S CHARACTER"` đóng góp lớn nhất (16,798526763916016).

## T3 — độ bền theo `top_k`

Mỗi lượt 180 câu, cùng đồ thị, cache parser, A1@4000 và tối đa hai shard. Ở `top_k=10/5`, tên mã L2 vẫn là `cand_not_top30` nhưng giới hạn thực của `kwd2chunk` là `floor(top_k/2)` = **5/2**, không phải 30.

| `top_k` | L0 | L1 | L2 | L3 | OK chunk / 207 | Câu đủ / 180 | Seed hub top-1% ở câu | Token Sources do hub top-1% / tổng | Top-5% / tổng |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 60 | 2 | 70 | 6 | 33 | 96 | 75 | 160 | 103.254/651.068 | 238.248/651.068 |
| 10 | 2 | 97 | 29 | 4 | 75 | 60 | 146 | 121.542/470.289 | 261.849/470.289 |
| 5 | 2 | 107 | 38 | 0 | 60 | 48 | 129 | 50.164/218.460 | 126.647/218.460 |

Số câu giữ đủ đáp án theo Single/Multi lần lượt là **69/6**, **56/4**, **47/1**. Khi giảm `top_k`, mất mát chuyển vào L1/L2; ở `k=5`, A1 không làm mất thêm chunk đáp án. Tỉ phần Sources do seed hub top-5% chi phối vẫn cao (238.248/651.068 → 261.849/470.289 → 126.647/218.460), nhưng **không thể gọi đó là “hub chiếm ngân sách A1” ở `k=5`** vì trần A1 không còn là nút thắt quan sát được. Tái dựng xếp hạng và A1 đều khớp 180/180 ở cả hai lượt nhỏ.

## Bằng chứng ngoài dev và giới hạn suy luận

[Kết quả bước 2 của L-FLOW](../../.worktrees/lihua-flow/docs/research/lihua_world/LIHUA_FLOW.md) đo trên 435 câu ngoài dev, gồm 388 câu có Evidence, ba seed: C0 giữ đủ chunk đáp án **36,86 / 37,11 / 36,34%**; C3 L-FLOW chỉ **23,97 / 24,23 / 24,74%** (13–15 câu lên, 60–63 xuống, McNemar `p ≤ 1,6·10⁻⁷` mỗi seed); C2 L-FLOW0 **25,00 / 25,26 / 25,26%**. Context C0R khớp byte với C0 ở 435/435 câu × 3 seed. Phần hại chủ yếu nằm ở nối tổng điểm thô vào `kwd2chunk`, không phải riêng công thức P2. Đây là số đo bổ sung của nhóm, **không chạy lại** trong giai đoạn này và chưa đo accuracy câu trả lời.

Phân tầng trên một đồ thị Qwen, một corpus và chỉ câu có Evidence; nó không suy ra accuracy hay tính khái quát sang index khác. Gold là nhãn chẩn đoán, không đi vào truy hồi. Phân loại L1 dùng trạng thái Counter đã log và thứ tự hiện tại; sửa một bước có thể chưa đưa chunk qua các bước sau. Phân rã hub gán mỗi chunk cho seed đóng góp lớn nhất, nên là mô tả, không phải nhân quả. Trước khi tokenizer cache được bổ sung, một lượt smoke đã khiến `tiktoken` **thử** tải `o200k_base` nhưng kết nối bị hệ thống chặn; không có dữ liệu mạng nhận được. Các lượt đo hoàn chỉnh sau đó dùng cache cục bộ và `MINIRAG_KW_CACHE_ONLY=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.

## Ứng viên cơ chế cho giai đoạn 2

Đây là **hướng để đăng ký giả thuyết**, chưa phải Proposed Method và chưa cài đặt/đo. Trần là số câu có ít nhất một chunk vàng ở tầng tương ứng, **trần lạc quan** vì câu Multi có thể còn mất chunk ở tầng khác.

| Hướng thuần đồ thị | Tầng nhắm tới | Trần câu có thể tác động | Rủi ro phải kiểm soát |
|---|---|---:|---|
| Bổ sung nguồn thực thể/cạnh khi dựng đồ thị cho chunk chưa được trích xuất | L0 | 2 | Phải index lại; có thể tăng node rác và trùng thực thể. |
| Phân bổ nguồn theo đường và seed, xét nhiều đường với tín hiệu liên quan có chuẩn hóa thay cho chỉ Counter đường cuối/top-3 cứng | L1 | 69 | Tổng điểm thô L-FLOW đã làm hại rõ trên ngoài dev; tăng ứng viên có thể dìm vàng trong A1. |
| Xếp hạng graph có điều tiết mức phổ biến của seed (`degree`, `df`) cùng độ phù hợp câu hỏi | L2 | 6 | Trần nhỏ; bỏ ×2/×10 trực tiếp làm hại retention; hub không mặc nhiên là nhiễu. |
| Chọn Sources theo độ đa dạng đường/seed trong ngân sách A1, vẫn chỉ từ ứng viên graph | L3 | 31 | Có thể đẩy bằng chứng tốt ra ngoài và tăng ngữ cảnh gây nhầm ở Null; hiệu ứng biến mất khi `k=5`. |

Giai đoạn 2 cần đăng ký cơ chế, đối chứng, chất lượng **và** hiệu suất, rồi đo ablation; đổi `top_k`, bỏ boost hay chỉ sửa bug không tự thân là đóng góp.

## Tái tạo và file

Từ gốc repo, dùng duy nhất `.venv\Scripts\python.exe`. Các lệnh truy hồi đặt env offline, `TIKTOKEN_CACHE_DIR=E:\Project\MiniRAG\data-gym-cache`; runner tự đặt thêm `TMP/TEMP` vào `logs/graph_repair/tmp/`, chạy trên bản sao index và giới hạn **2 shard**. Lệnh dưới đây chỉ tổng hợp log đã có, trừ `run_offline.py`:

```powershell
$env:MINIRAG_KW_CACHE_ONLY='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:TIKTOKEN_CACHE_DIR='E:\Project\MiniRAG\data-gym-cache'
$env:PYTHONIOENCODING='utf-8'

.\.venv\Scripts\python.exe reproduce\graph_repair\verify_t0.py --frozen logs\c_ablation\graph\C0\C0_records.jsonl --off logs\graph_repair\phase1\t0_off\C0_records.jsonl --on logs\graph_repair\phase1\t0_on\C0_records.jsonl --output logs\graph_repair\phase1\t0_regression.json
.\.venv\Scripts\python.exe reproduce\graph_repair\compare_d1.py
.\.venv\Scripts\python.exe reproduce\graph_repair\run_offline.py --name d2_fix0 --diag --answer-type-fix 0
.\.venv\Scripts\python.exe reproduce\graph_repair\summarize_t1.py
.\.venv\Scripts\python.exe reproduce\graph_repair\diagnose.py --run t0_on --output logs\graph_repair\phase1\t2_summary.json --rank-l0
.\.venv\Scripts\python.exe reproduce\graph_repair\run_offline.py --name k10 --diag --top-k 10
.\.venv\Scripts\python.exe reproduce\graph_repair\diagnose.py --run k10 --output logs\graph_repair\phase1\k10_summary.json
.\.venv\Scripts\python.exe reproduce\graph_repair\run_offline.py --name k5 --diag --top-k 5
.\.venv\Scripts\python.exe reproduce\graph_repair\diagnose.py --run k5 --output logs\graph_repair\phase1\k5_summary.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_path_score_flow.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_c_ablation.py -v
```

Các lệnh `run_offline.py` phải chạy **lần lượt**, không đồng thời. T0/D1 đã chạy và được giữ nguyên; không cần chạy lại để tái tạo các số từ log. D2 mới chỉ ghép `shard_0/1`; `shard_2/3` dở dang từ lần crash cũ còn trong thư mục vì thao tác xóa đệ quy bị chính sách môi trường chặn, nhưng không tham gia bất kỳ tổng hợp nào. `diagnose.py` ghi JSON tổng hợp và JSONL từng chunk vàng; `summarize_t1.py` ghi `t1_summary.json`.

File mã tạo: `reproduce/graph_repair/{verify_t0.py,compare_d1.py,run_offline.py,summarize_t1.py,diagnose.py,PHASE1_REPORT.md}`. File sửa: `minirag/operate.py` (DIAG và can thiệp D1 đều mặc định tắt), `reproduce/path/eval_offline.py` (`--top-k`, offset, FIX và dọn temp Windows), `tests/test_path_score_flow.py` (DIAG tắt). Đầu ra mới: `logs/graph_repair/phase1/` chứa log và JSON T0–T3; `data-gym-cache/` có bản cache tokenizer cục bộ. Không sửa `baseline.yaml`, `.gitignore`, `reproduce/demo/*`, file L-FLOW, hay index; không commit.
