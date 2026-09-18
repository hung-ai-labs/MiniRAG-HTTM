"""Kiem thu lop report cua E1. KHONG chay truy hoi, khong can raw log.

Bao phu dung ba dieu de doa tinh hop le cua ket luan:
  1. FAIL hoac UNVERIFIED o check bat buoc PHAI chan cong (passed = None, NOT_EVALUATED);
  2. cong RRF phai doc final_chunks, khong phai graph_top30 (graph_ids la ban chup truoc fusion);
  3. full-evidence la TAP CON that su -- trung mot phan khong duoc tinh la dat.

    .venv/Scripts/python.exe reproduce/entity_resolution/test_report_layer.py
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "screening"))

from report_e1 import (  # noqa: E402
    Check, PASS, FAIL, UNVERIFIED, decide_gates, full_evidence, paired,
)

fails = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond:
        fails.append(name)


def make_results(graph_net, graph_p_pairs, rrf_graph_net, rrf_final_net):
    """Dung ket qua gia. graph_p_pairs = (wins, losses) de McNemar ra p that."""
    from screen_variant import mcnemar_p

    def block(net, wins=None, losses=None):
        wins = wins if wins is not None else max(net, 0)
        losses = losses if losses is not None else max(-net, 0)
        return {"n": 180, "control_pass": 10, "control_rate": 5.6, "treatment_pass": 10 + net,
                "treatment_rate": 5.6, "wins": wins, "losses": losses, "tie_pass": 5,
                "tie_fail": 100, "net": net, "mcnemar_p": mcnemar_p(wins, losses)}

    gw, gl = graph_p_pairs
    return {
        "graph": {"graph_top30": {"ALL": block(graph_net, gw, gl), "Single": block(0),
                                   "Multi": block(0)},
                   "final_chunks": {"ALL": block(0), "Single": block(0), "Multi": block(0)},
                   "workload": {}},
        "rrf": {"graph_top30": {"ALL": block(rrf_graph_net), "Single": block(0), "Multi": block(0)},
                 "final_chunks": {"ALL": block(rrf_final_net), "Single": block(0),
                                   "Multi": block(0)},
                 "workload": {}},
    }


all_pass = [Check("a", PASS), Check("b", PASS)]

# ---- 1. moi check PASS -> cong duoc tinh ----
res = make_results(graph_net=12, graph_p_pairs=(12, 0), rrf_graph_net=-99, rrf_final_net=3)
gate, overall = decide_gates(res, all_pass)
check("moi check PASS -> overall VALID", overall == "VALID", overall)
check("moi check PASS -> gate EVALUATED", gate["status"] == "EVALUATED", gate["status"])
check("graph-only dat khi net=12 va p<0,01", gate["graph_only"]["passed"] is True,
      f"net={gate['graph_only']['net']} p={gate['graph_only']['mcnemar_p']:.2g}")

# ---- 2. cong RRF phai doc final_chunks, KHONG phai graph_top30 ----
check("cong RRF lay net tu final_chunks (+3), khong phai graph_top30 (-99)",
      gate["rrf"]["net"] == 3, gate["rrf"]["net"])
check("cong RRF dat voi net=+3", gate["rrf"]["passed"] is True)
check("nhan metric cua cong RRF ghi ro final_chunks",
      "final_chunks" in gate["rrf"]["metric"], gate["rrf"]["metric"])
res2 = make_results(graph_net=12, graph_p_pairs=(12, 0), rrf_graph_net=+50, rrf_final_net=-4)
gate2, _ = decide_gates(res2, all_pass)
check("RRF truot khi final_chunks am du graph_top30 duong",
      gate2["rrf"]["passed"] is False and gate2["rrf"]["net"] == -4, gate2["rrf"]["net"])

# ---- 3. FAIL o check bat buoc chan cong ----
gate3, overall3 = decide_gates(res, all_pass + [Check("hong", FAIL)])
check("co FAIL -> overall INVALID", overall3 == "INVALID", overall3)
check("co FAIL -> gate NOT_EVALUATED", gate3["status"] == "NOT_EVALUATED", gate3["status"])
check("co FAIL -> graph_only.passed = None", gate3["graph_only"]["passed"] is None)
check("co FAIL -> rrf.passed = None", gate3["rrf"]["passed"] is None)
check("co FAIL -> liet ke check chan cong kem trang thai", "FAIL: hong" in gate3["blocking_checks"],
      gate3["blocking_checks"])

# ---- 4. UNVERIFIED o check bat buoc cung chan cong ----
gate4, overall4 = decide_gates(res, all_pass + [Check("thieu bang chung", UNVERIFIED)])
check("co UNVERIFIED -> overall UNVERIFIED", overall4 == "UNVERIFIED", overall4)
check("co UNVERIFIED -> gate NOT_EVALUATED", gate4["status"] == "NOT_EVALUATED")
check("co UNVERIFIED -> passed = None ca hai cong",
      gate4["graph_only"]["passed"] is None and gate4["rrf"]["passed"] is None)

# ---- 5. check khong bat buoc thi khong chan ----
gate5, overall5 = decide_gates(res, all_pass + [Check("phu", FAIL, required=False)])
check("check optional FAIL khong chan cong", overall5 == "VALID"
      and gate5["graph_only"]["passed"] is True)

# ---- 6. full-evidence la tap con, khong phai trung mot phan ----
row = {"graph_ids": ["c1", "c2", "c9"]}
check("du ca hai gold -> dat", full_evidence(row, ["c1", "c2"], "graph_ids") is True)
check("chi trung mot phan -> KHONG dat", full_evidence(row, ["c1", "c3"], "graph_ids") is False)
check("gold rong -> khong dat", full_evidence(row, [], "graph_ids") is False)
check("danh sach rong -> khong dat", full_evidence({"graph_ids": []}, ["c1"], "graph_ids") is False)

# ---- 7. paired() dem dung tren du lieu tong hop ----
gold = {"q1": ["a"], "q2": ["a"], "q3": ["a"], "q4": ["a"]}
ctrl = [{"question": "q1", "type": "Single", "graph_ids": ["a"]},     # tie-pass
        {"question": "q2", "type": "Single", "graph_ids": []},        # win
        {"question": "q3", "type": "Multi", "graph_ids": ["a"]},      # loss
        {"question": "q4", "type": "Multi", "graph_ids": []}]         # tie-fail
trt = [{"question": "q1", "type": "Single", "graph_ids": ["a"]},
       {"question": "q2", "type": "Single", "graph_ids": ["a"]},
       {"question": "q3", "type": "Multi", "graph_ids": []},
       {"question": "q4", "type": "Multi", "graph_ids": []}]
r = paired(ctrl, trt, gold, "graph_ids")
check("paired: 1 win / 1 loss / 1 tie-pass / 1 tie-fail",
      (r["wins"], r["losses"], r["tie_pass"], r["tie_fail"]) == (1, 1, 1, 1), r)
check("paired: net = wins - losses = 0", r["net"] == 0)
check("paired: control_pass = tie_pass + losses = 2", r["control_pass"] == 2)
check("paired: treatment_pass = tie_pass + wins = 2", r["treatment_pass"] == 2)
rs = paired(ctrl, trt, gold, "graph_ids", "Single")
check("paired loc Single: n=2, 1 win, 0 loss", (rs["n"], rs["wins"], rs["losses"]) == (2, 1, 0), rs)

# ---- 8. McNemar dung exact two-sided binomial ----
from screen_variant import mcnemar_p  # noqa: E402


def exact_ref(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


cases = [(0, 0), (9, 0), (12, 0), (13, 4), (5, 5), (17, 3), (1, 0), (30, 12)]
ok = all(abs(mcnemar_p(b, c) - exact_ref(b, c)) < 1e-12 for b, c in cases)
check("mcnemar_p khop exact two-sided binomial doc lap", ok,
      f"vd (9,0)={mcnemar_p(9, 0):.6g}, (13,4)={mcnemar_p(13, 4):.4g}")
check("mcnemar_p(12,0) < 0,01 (nguong cong graph-only)", mcnemar_p(12, 0) < 0.01,
      f"{mcnemar_p(12, 0):.2g}")
# net = +8 co p = 0,0078 (<0,01) nhung VAN truot vi nguong net >= +9. Kiem dung o muc cong,
# khong phai o muc p, de khong nham lan hai dieu kien.
res8 = make_results(graph_net=8, graph_p_pairs=(8, 0), rrf_graph_net=0, rrf_final_net=0)
gate8, _ = decide_gates(res8, all_pass)
check("net=+8 truot cong graph-only du p<0,01 (chan boi nguong net>=9)",
      gate8["graph_only"]["passed"] is False and mcnemar_p(8, 0) < 0.01,
      f"net=8, p={mcnemar_p(8, 0):.4g}")
res9 = make_results(graph_net=9, graph_p_pairs=(9, 0), rrf_graph_net=0, rrf_final_net=0)
gate9, _ = decide_gates(res9, all_pass)
check("net=+9 voi p=0,0039 thi dat cong graph-only",
      gate9["graph_only"]["passed"] is True, f"p={mcnemar_p(9, 0):.4g}")
res_p = make_results(graph_net=10, graph_p_pairs=(25, 15), rrf_graph_net=0, rrf_final_net=0)
gate_p, _ = decide_gates(res_p, all_pass)
check("net=+10 nhung p=0,15 thi truot (chan boi nguong p)",
      gate_p["graph_only"]["passed"] is False,
      f"p={gate_p['graph_only']['mcnemar_p']:.3g}")

print()
print("KET QUA:", "TAT CA PASS" if not fails else f"{len(fails)} FAIL: {fails}")
sys.exit(1 if fails else 0)
