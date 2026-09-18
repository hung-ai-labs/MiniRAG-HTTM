"""Sua lop gate/report cua eval_offline.py. Khong dung toi tien trinh truy hoi dang chay."""
import io

P = r"E:\Sv clone\MiniRAG\reproduce\entity_resolution\eval_offline.py"
s = io.open(P, encoding="utf-8").read()
orig = s


def rep(old, new):
    global s
    assert old in s, "KHONG TIM THAY:\n" + old[:200]
    s = s.replace(old, new, 1)


# --- 1. ghi chu audit + dinh nghia cong da sua ---
rep(
    '# Cong da dang ky truoc -- KHONG doi sau khi thay ket qua.\n'
    'GATE = {"graph": "full-evidence net >= +9 VA p < 0,01", "rrf": "full-evidence net >= 0"}',

    '# Cong da dang ky truoc -- NGUONG KHONG DOI. Sua 17/09/2026 la sua ANH XA metric, khong phai\n'
    '# nguong, va duoc lam TRUOC khi bat ky ket qua full-run nao duoc doc:\n'
    '#   operate.py:1489 chup graph_chunk_ids TRUOC nhanh fusion (:1495-1504), nen `graph_ids`\n'
    '#   giong het nhau o ca hai mode -- cong RRF dat tren graph_top30 se khong he do RRF. Tac\n'
    '#   dong cua RRF chi hien ra o `chunk_ids` (sau fusion va sau cat token A1).\n'
    'GATE = {\n'
    '    "graph_only": {"metric": "mode=graph -> graph_top30 (ALL)",\n'
    '                    "rule": "full-evidence net >= +9 VA McNemar exact p < 0,01"},\n'
    '    "rrf": {"metric": "mode=rrf -> final_chunks (ALL)",\n'
    '             "rule": "full-evidence net >= 0"},\n'
    '}\n\n'
    'AUDIT_NOTES = [\n'
    '    "3-query engineering smoke test was observed before the full run; no merge decision, "\n'
    '    "metric definition or numerical threshold was changed based on it.",\n'
    '    "Gate metric mapping corrected before any full-run result was read: graph_ids is captured "\n'
    '    "before chunk fusion (operate.py:1489), so the RRF gate is evaluated on final_chunks, not "\n'
    '    "on graph_top30. Preregistered thresholds (+9 / p<0.01; >=0) are unchanged.",\n'
    '    "Control arm is NOT the byte-identical committed retrieval index: both arms had their "\n'
    '    "relationship VDB re-embedded with hf_embed at batch=1 per the 17/09/2026 amendment.",\n'
    ']')

# --- 2. --report-only; mo ta --resume trung thuc ---
rep(
    '    ap.add_argument("--resume", action="store_true",\n'
    '                    help="dung lai ket qua da co neu file du 180 ban ghi dung bo cau hoi")',

    '    ap.add_argument("--resume", action="store_true",\n'
    '                    help="dung lai mot luot (arm, mode) DA HOAN TAT du 180 ban ghi dung bo "\n'
    '                         "cau hoi. KHONG ho tro resume giua chung mot arm: arm dang do se "\n'
    '                         "phai chay lai tu dau.")\n'
    '    ap.add_argument("--report-only", action="store_true",\n'
    '                    help="chi tinh lai bao cao tu 4 raw log da co; tu choi chay truy van")')

rep(
    '            done = load_done(out_path, rows, args.limit) if args.resume else None',
    '            done = (load_done(out_path, rows, args.limit)\n'
    '                    if (args.resume or args.report_only) else None)\n'
    '            if done is None and args.report_only:\n'
    '                raise SystemExit(f"--report-only: thieu raw log day du cho {arm}/{mode}")')

# --- 3. graph_ids phai bat bien giua hai mode (he qua truc tiep cua operate.py:1489) ---
rep(
    '    add("tap do: 180 = 159 Single + 21 Multi + 0 Null",',

    '    for arm in ARMS:\n'
    '        gg = {r["question"]: r["graph_ids"] for r in data[(arm, "graph")]}\n'
    '        gr = {r["question"]: r["graph_ids"] for r in data[(arm, "rrf")]}\n'
    '        diff = [q for q in gg if gg[q] != gr.get(q)]\n'
    '        add(f"{arm}: graph_ids giong het o ca hai mode (chup truoc fusion, operate.py:1489)",\n'
    '            not diff, f"{len(diff)} cau lech")\n\n'
    '    add("tap do: 180 = 159 Single + 21 Multi + 0 Null",')

# --- 4. xac minh hai nhanh con nguyen ven, dung duoc ca o luot report-only ---
rep(
    'def index_hashes(workingdir):',

    'def verify_arms_intact(rep_json):\n'
    '    """Xac nhan hai nhanh van dung nhu luc dong bang (so canh, so ban ghi quan he) va cac kho\n'
    '    khong duoc phep doi van giong het index tham chieu. Dung duoc ca trong --report-only."""\n'
    '    from check_embedding_parity import load_vdb_json\n\n'
    '    refs = {"control": os.path.join(ROOT, "LiHua-World-qwen-modal"),\n'
    '            "treatment": os.path.join(ROOT, "LiHua-World-qwen-entres")}\n'
    '    keys = {"control": "control", "treatment": "entres"}\n'
    '    out = {}\n'
    '    for arm, d in ARMS.items():\n'
    '        g = read_graph(d)\n'
    '        recs, _ = load_vdb_json(d, "relationships")\n'
    '        exp = rep_json["arms"][keys[arm]]\n'
    '        same_counts = (g.number_of_edges() == exp["edges"] and len(recs) == exp["records"])\n'
    '        same_stores = all(\n'
    '            file_sha256(os.path.join(d, f)) == file_sha256(os.path.join(refs[arm], f))\n'
    '            for f in ("kv_store_text_chunks.json", "vdb_chunks.json", "vdb_entities_name.json"))\n'
    '        out[arm] = {"counts_match_frozen": same_counts,\n'
    '                    "chunk_and_name_stores_intact": same_stores,\n'
    '                    "edges": g.number_of_edges(), "rel_records": len(recs)}\n'
    '    return out\n\n\n'
    'def index_hashes(workingdir):')

rep(
    '    for arm, ok in hashes_ok.items():\n'
    '        add(f"{arm}: file index khong doi sau khi chay", ok)\n'
    '    return checks',

    '    for arm, info in hashes_ok.items():\n'
    '        add(f"{arm}: so canh / so ban ghi quan he dung nhu luc dong bang",\n'
    '            info["counts_match_frozen"], f"{info[\'edges\']} canh, {info[\'rel_records\']} ban ghi")\n'
    '        add(f"{arm}: kho chunk va entity_name con nguyen ven",\n'
    '            info["chunk_and_name_stores_intact"])\n'
    '    return checks')

rep(
    '            data[(arm, mode)] = recs\n'
    '            hashes_ok[arm] = hashes_ok.get(arm, True) and unchanged',
    '            data[(arm, mode)] = recs\n'
    '            _ = unchanged')

rep(
    '    cache_after = len({json.loads(ln)["prompt_sha256"]',
    '    hashes_ok = verify_arms_intact(rep)\n'
    '    cache_after = len({json.loads(ln)["prompt_sha256"]')

# --- 5. cong da sua ---
rep(
    '    g = results["graph"]["graph_top30"]["ALL"]\n'
    '    r = results["rrf"]["graph_top30"]["ALL"]\n'
    '    gate = {\n'
    '        "graph_only": {"rule": GATE["graph"], "net": g["net"], "p": g["mcnemar_p"],\n'
    '                        "passed": g["net"] >= 9 and g["mcnemar_p"] < 0.01},\n'
    '        "rrf": {"rule": GATE["rrf"], "net": r["net"], "passed": r["net"] >= 0},\n'
    '    }',

    '    g = results["graph"]["graph_top30"]["ALL"]      # cong graph-only: xep hang do thi top-30\n'
    '    r = results["rrf"]["final_chunks"]["ALL"]        # cong RRF: danh sach chunk CUOI sau fusion\n'
    '    gate = {\n'
    '        "graph_only": {**GATE["graph_only"], "net": g["net"], "p": g["mcnemar_p"],\n'
    '                        "passed": bool(g["net"] >= 9 and g["mcnemar_p"] < 0.01)},\n'
    '        "rrf": {**GATE["rrf"], "net": r["net"], "p": r["mcnemar_p"],\n'
    '                 "passed": bool(r["net"] >= 0)},\n'
    '    }')

rep(
    '        payload = {"mode": mode, "fusion": MODES[mode],\n'
    '                    "arms": {a: ARMS[a] for a in ARMS},\n'
    '                    "valid": valid, "checks": checks, **results[mode]}',

    '        payload = {"mode": mode, "fusion": MODES[mode],\n'
    '                    "arms": {a: ARMS[a] for a in ARMS},\n'
    '                    "audit_notes": AUDIT_NOTES, "gate": gate,\n'
    '                    "valid": valid, "checks": checks, **results[mode]}')

rep(
    '    lines += ["## cong da dang ky truoc", json.dumps(gate, ensure_ascii=False, indent=1)]',
    '    lines += ["## cong da dang ky truoc (nguong khong doi)",\n'
    '              json.dumps(gate, ensure_ascii=False, indent=1), "",\n'
    '              "## audit notes"] + [f"- {n}" for n in AUDIT_NOTES]')

io.open(P, "w", encoding="utf-8").write(s)
print(f"patched: {len(orig)} -> {len(s)} ky tu")
