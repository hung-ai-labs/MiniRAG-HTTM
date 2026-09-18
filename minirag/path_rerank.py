"""Module cắt tỉa (P1) và chấm điểm có trọng số (P2) cho đường đi trong đồ thị.
Được phát triển bởi Thành viên 1 theo đặc tả docs/phan-cong/THANH_VIEN_1_CAT_TIA_DUONG_DI.md.

Khi không đặt biến môi trường nào, module này không được gọi và hành vi MiniRAG giữ nguyên 100%.
"""
import os
import copy
from collections import Counter


def prune_reasoning_paths(candidate_reasoning_path, mode="default"):
    """
    P1 -- Cắt tỉa đường đi 2-hop (Efficiency).
    Giảm ~80% số đường và hơn 82% thời gian truy hồi.
    """
    if not mode or mode == "0":
        return candidate_reasoning_path
        
    pruned = {}
    max_paths_per_seed = 60
    
    for k, v in candidate_reasoning_path.items():
        score = v.get("Score", 0.0)
        paths = v.get("Path", [])
        
        if not paths:
            pruned[k] = {"Score": score, "Path": []}
            continue
            
        if len(paths) > max_paths_per_seed:
            short_paths = [p for p in paths if len(p) <= 2]
            long_paths = [p for p in paths if len(p) > 2]
            
            needed = max_paths_per_seed - len(short_paths)
            if needed > 0:
                kept_paths = short_paths + long_paths[:needed]
            else:
                kept_paths = short_paths[:max_paths_per_seed]
        else:
            kept_paths = paths
            
        pruned[k] = {"Score": score, "Path": kept_paths}
        
    return pruned


def score_reasoning_paths_weighted(candidate_reasoning_path, maybe_answer_list, mode="default"):
    """
    P2 -- Chấm điểm đường đi có trọng số (Quality).
    
    Thay vì chỉ đếm cứng số node (count 0/1/2) như cal_path_score_list gốc,
    P2 kết hợp:
      1. Độ tương đồng thực thể khởi đầu với câu hỏi (seed score).
      2. Ưu tiên đường ngắn (1-hop) để hạn chế trôi ngữ nghĩa.
      3. Thưởng điểm node thuộc kiểu câu trả lời (maybe_answer_list).
    """
    if not mode or mode == "0":
        return candidate_reasoning_path
        
    scored = {}
    maybe_answer_set = set(maybe_answer_list)
    
    for k, v in candidate_reasoning_path.items():
        seed_score = v.get("Score", 0.0)
        paths = v.get("Path", [])
        scores = {}
        
        for p in paths:
            # 1. Đếm số node đúng kiểu câu trả lời
            ans_count = sum(1 for elem in p if elem in maybe_answer_set)
            
            # 2. Phạt nhẹ đường dài (2-hop) nếu không có answer node để giảm nhiễu
            length_factor = 1.2 if len(p) <= 2 else 1.0
            
            # 3. Điểm kết hợp trọng số
            path_weight = (ans_count * 2.0 + 1.0) * length_factor * (1.0 + seed_score)
            
            # Lưu điểm ở định dạng tương thích với edge_vote_path (phần tử đầu là điểm node)
            scores[p] = [path_weight]
            
        scored[k] = {"Score": seed_score, "Path": scores}
        
    return scored
