# LiHua-World ablation v2 — kết quả (tự sinh bởi analyze_lihua_ablation.py)

| Nhánh | acc s101 | acc s202 | acc s303 | TB ± sd sinh |
|---|---:|---:|---:|---:|
| L-C0 | 48.51 | 48.97 | 49.20 | 48.89 ± 0.35 |
| L-B2 | 73.56 | 72.18 | 75.17 | 73.64 ± 1.5 |
| L-VEC | 66.21 | 67.36 | 63.91 | 65.83 ± 1.76 |
| L-BM25 | 74.48 | 75.40 | 75.17 | 75.02 ± 0.48 |
| L-B1 | 68.51 | 65.75 | 66.44 | 66.9 ± 1.44 |
| L-NOENT | 75.63 | 75.17 | 74.48 | 75.09 ± 0.58 |
| L-NOGRAPH | 73.56 | 75.40 | 74.25 | 74.4 ± 0.93 |

| Phép so | b − a | s101: Δ (lên/xuống, p, p Holm) | s202: Δ (lên/xuống, p, p Holm) | s303: Δ (lên/xuống, p, p Holm) | Kết luận |
|---|---|---|---|---|---|
| L1 | L-B2 − L-C0 | +25.05 (139/30, 5.68e-18) | +23.21 (129/28, 1.08e-16) | +25.97 (140/27, 1.35e-19) | {"confirmed": true, "direction": "B2 better"} |
| L2 | L-B2 − L-VEC | +7.35 (62/30, 0.00111, 0.00555) | +4.82 (56/35, 0.0354, 0.142) | +11.26 (67/18, 8.41e-08, 4.21e-07) | {"contributes": false, "direction": "positive", "noninferior_at_-3_all_seeds": true, "stage_d_direction_replicated": true, "stage_d": "+8.12 (H2)"} |
| L3 | L-B2 − L-BM25 | -0.92 (39/43, 0.741, 0.741) | -3.22 (30/44, 0.13, 0.276) | +0.00 (40/40, 1, 1) | {"contributes": false, "direction": "mixed", "noninferior_at_-3_all_seeds": false} |
| L4 | L-B2 − L-B1 | +5.05 (59/37, 0.0315, 0.126) | +6.43 (61/33, 0.00508, 0.0254) | +8.73 (61/23, 4.08e-05, 0.000163) | {"contributes": false, "direction": "positive", "noninferior_at_-3_all_seeds": true, "stage_d_direction_replicated": true, "stage_d": "+6.59 (H3)"} |
| L5 | L-B2 − L-NOENT | -2.07 (22/31, 0.272, 0.543) | -2.99 (19/32, 0.0919, 0.276) | +0.69 (28/25, 0.784, 1) | {"contributes": false, "direction": "mixed", "noninferior_at_-3_all_seeds": false} |
| L6 | L-NOENT − L-NOGRAPH | +2.07 (15/6, 0.0784, 0.235) | -0.23 (8/9, 1, 1) | +0.23 (9/8, 1, 1) | {"contributes": false, "direction": "mixed", "noninferior_at_-3_all_seeds": true} |
