"""Thống kê cấu trúc đồ thị thực thể — bằng chứng Observed Problem cho việc hợp nhất thực thể
(docs/phan-cong/THANH_VIEN_2_HOP_NHAT_THUC_THE.md).

    .venv/bin/python reproduce/entity_resolution/graph_stats.py --workingdir ./LiHua-World-qwen-modal

Chỉ đọc graphml: không gọi LLM, không ghi vào index. Chạy lại trên index đã gộp để so trước / sau.
"""
import argparse, collections, os, re, statistics as st

import networkx as nx


def norm_key(name):
    """Khoá so trùng: bỏ ngoặc kép bao ngoài, casefold, bỏ mọi ký tự không phải chữ hay số (giữ chữ không phải Latin)."""
    return re.sub(r"[\W_]", "", name.strip('"').casefold())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workingdir", default="./LiHua-World-qwen-modal")
    ap.add_argument("--show", type=int, default=10, help="số nhóm trùng in ra")
    a = ap.parse_args()
    G = nx.read_graphml(os.path.join(a.workingdir, "graph_chunk_entity_relation.graphml"))
    comps = sorted((len(c) for c in nx.connected_components(G)), reverse=True)
    groups = collections.defaultdict(list)
    for n in G:
        groups[norm_key(n)].append(n)
    dup = sorted((v for k, v in groups.items() if k and len(v) > 1), key=lambda v: -sum(G.degree(x) for x in v))
    junk = sorted(n for n in G if not norm_key(n))
    types = collections.Counter(d.get("entity_type", "") for _, d in G.nodes(data=True))
    desc = [len(d.get("description", "")) for _, d in G.nodes(data=True)]
    hubs = sorted(G.nodes, key=G.degree, reverse=True)[:5]

    print(f"index: {a.workingdir}")
    print(f"node {G.number_of_nodes()} · cạnh {G.number_of_edges()}")
    print(f"thành phần liên thông {len(comps)} · lớn nhất {comps[0]} node · node cô lập (bậc 0) "
          f"{sum(1 for n in G if G.degree(n) == 0)}")
    print(f"nhóm trùng tên sau chuẩn hoá: {len(dup)} nhóm, {sum(len(v) for v in dup)} node")
    for v in dup[:a.show]:
        print("   ", " · ".join(f"{x} (bậc {G.degree(x)})" for x in sorted(v, key=G.degree, reverse=True)))
    print(f"tên không có chữ hay số (rác): {len(junk)} — {junk[:8]}")
    print(f"entity_type khác nhau: {len(types)} · phổ biến nhất: {types.most_common(8)}")
    print(f"độ dài mô tả node: trung vị {st.median(desc):.0f} · max {max(desc)} ký tự")
    print("hub bậc cao nhất:", " · ".join(f"{n} ({G.degree(n)})" for n in hubs))


if __name__ == "__main__":
    main()
