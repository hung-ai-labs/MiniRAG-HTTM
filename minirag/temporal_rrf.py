"""Explicit C0/source-time/RRF composition and observational chunk-budget trace."""
from .utils import encode_string_by_tiktoken


def validate_profile(env,top_k,budget):
    """Allow only the requested composition; never enable it implicitly."""
    if env.get('MINIRAG_TEMPORAL_RRF','')!='1':
        raise ValueError('Temporal + RRF requires explicit MINIRAG_TEMPORAL_RRF=1')
    required={'MINIRAG_TEMPORAL':'1','MINIRAG_CHUNK_FUSION':'rrf',
        'MINIRAG_PATH2CHUNK_FIX':'0','MINIRAG_PATH_SCORE_FLOW':'0',
        'MINIRAG_TEMPORAL_EXPAND':'1','MINIRAG_TEMPORAL_H':'0'}
    defaults={'MINIRAG_PATH2CHUNK_FIX':'0','MINIRAG_PATH_SCORE_FLOW':'0',
        'MINIRAG_TEMPORAL_EXPAND':'1','MINIRAG_TEMPORAL_H':'0'}
    for key,value in required.items():
        if env.get(key,defaults.get(key,''))!=value:
            raise ValueError('C0 temporal/RRF incompatible setting: '+key)
    forbidden=('MINIRAG_SOURCE_EVENT_TIME','MINIRAG_GRAPH_ARM','MINIRAG_PATH_SCORE',
        'MINIRAG_PATH_PROJECTION','MINIRAG_PATH_SELECTION','MINIRAG_PATH_SCORE_CALIBRATION',
        'MINIRAG_PATH_SCORE_NORMALIZATION','MINIRAG_PATH_CONSENSUS','MINIRAG_PATH_RESEARCH',
        'MINIRAG_P2_ENHANCE','MINIRAG_PATH_PRUNE','MINIRAG_CHUNK_CUT',
        'MINIRAG_RERANK','MINIRAG_LEEF')
    if any(env.get(k,'').strip() for k in forbidden) or env.get('MINIRAG_GRAPH_FLOW','') not in ('','0'):
        raise ValueError('C0 temporal/RRF requires original graph/path flows and no extra reranker')
    if top_k!=60 or budget!=4000 or env.get('MINIRAG_TRUNCATE_SOURCES','1')=='0':
        raise ValueError('C0 temporal/RRF requires top_k60 and A1@4000')


def budget_trace(ranked_ids,usable_ids,texts,graph_ids,dense_ids,c0_ids,time_ids,budget):
    """Observe the existing prefix policy; does not select or reorder any chunk."""
    if len(set(ranked_ids))!=len(ranked_ids):raise ValueError('Fused IDs must be unique')
    graph_rank={c:i+1 for i,c in enumerate(graph_ids)}
    dense_rank={c:i+1 for i,c in enumerate(dense_ids)}
    fused_rank={c:i+1 for i,c in enumerate(ranked_ids)}
    c0=set(c0_ids);time_set=set(time_ids);rows=[];total=0;prefix=[];overflow=False
    for c in usable_ids:
        tokens=len(encode_string_by_tiktoken(texts[c]));total+=tokens
        if total>budget:overflow=True
        keep=not overflow
        if keep:prefix.append(c)
        score=(1/(60+graph_rank[c]) if c in graph_rank else 0.)+(1/(60+dense_rank[c]) if c in dense_rank else 0.)
        rows.append({'chunk_id':c,'fused_rank':fused_rank[c],
            'graph_time_rank':graph_rank.get(c),'dense_rank':dense_rank.get(c),
            'rrf_score':score,'tokens':tokens,'cumulative_tokens':total,
            'in_graph_time':c in graph_rank,'in_dense':c in dense_rank,
            'in_C0_top30':c in c0,'selected_by_source_time':c in time_set,
            'kept_by_A1':keep})
    return {'policy':'existing_prefix_stop_at_first_overflow','budget':budget,
        'pre_A1_chunk_ids':list(usable_ids),'ranked_count':len(ranked_ids),
        'usable_count':len(usable_ids),'pre_A1_tokens':total,
        'exceeds_budget':total>budget,'missing_text_ids':[c for c in ranked_ids if c not in texts],
        'expected_A1_chunk_ids':prefix,'candidates':rows,
        'count_scope':'sum of chunk-content tokens; excludes Entities/CSV overhead/question/system prompt'}
