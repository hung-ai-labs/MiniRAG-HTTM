"""P0 prior, continuous relation support and matched source-background scoring."""
import copy
import hashlib
import json
import math
import time

from .path_affinity import condition_evidence
from .path_projection import project_paths

MODES=('full','no_relation','no_background','affinity_only')


def edge_key(u,v):return tuple(sorted((u,v)))


def cosine(value):
    value=float(value)
    if not math.isfinite(value) or not -1.000001<=value<=1.000001:
        raise ValueError('Missing or invalid relation/chunk cosine')
    return max(0.,min(1.,value))


def p0_path_weights(entries,relation_scores):
    """Retain every path and P0 type/vote count; score every hop without P2."""
    query,uniform={},{};fallbacks=0;zero_paths=0;signature=[]
    for seed,entry in entries.items():
        prior={};weighted={};uniform[seed]={}
        for path,scores in entry['Path'].items():
            a,v=float(scores[0]),float(scores[1])
            if any(not math.isfinite(x) or x<0 or not x.is_integer() for x in (a,v)):
                raise ValueError('New path scoring requires original P0 type/edge counts')
            q0=a+v+1.;prior[path]=q0;uniform[seed][path]=1.
            hops=[cosine(relation_scores[edge_key(u,w)]) for u,w in zip(path,path[1:])]
            relevance=(1. if not hops else 0. if any(x==0 for x in hops)
                       else math.exp(math.fsum(math.log(x) for x in hops)/len(hops)))
            weighted[path]=q0*relevance;zero_paths+=relevance==0
            signature.append((seed,path,a,v))
        if weighted and math.fsum(weighted.values())==0:
            weighted=prior;fallbacks+=1
        query[seed]=weighted
    return query,uniform,{'zero_relation_paths':zero_paths,'fallback_seeds':fallbacks,
        'original_paths':len(signature),'seeds':len(entries),
        'p0_input_sha256':hashlib.sha256(json.dumps(signature).encode()).hexdigest()}


async def prepare_scoring(entries,graph,pairs,query,*,valid,chunk_vectors,relation_vectors):
    """Compute P0, query-conditioned and structural projections on identical paths."""
    started=time.perf_counter()
    if valid is None or chunk_vectors is None or relation_vectors is None:
        raise ValueError('P0 relation scoring requires existing relation/chunk vectors and valid IDs')
    keys={edge_key(u,v) for e in entries.values() for p in e['Path'] for u,v in zip(p,p[1:])}
    t=time.perf_counter();rows=await relation_vectors.score_pairs(query,keys)
    relation_scores={}
    for row in rows:
        key=edge_key(row['src_id'],row['tgt_id']);value=float(row['distance']);cosine(value)
        if key in relation_scores and not math.isclose(relation_scores[key],value,abs_tol=1e-6):
            raise ValueError('Ambiguous duplicate vectors for a physical relation')
        relation_scores[key]=value
    if set(relation_scores)!=keys:raise ValueError('A path relation is missing its existing vector')
    relation_ms=1000*(time.perf_counter()-t)
    query_weights,uniform_weights,metadata=p0_path_weights(entries,relation_scores)
    prior_trace={};background_trace={};query_trace={}
    prior=await project_paths(copy.deepcopy(entries),graph,pairs,query,len(valid),'local',valid=valid,trace=prior_trace)
    background=await project_paths(copy.deepcopy(entries),graph,pairs,query,len(valid),'local',valid=valid,
        trace=background_trace,path_weights=uniform_weights)
    conditioned=await project_paths(copy.deepcopy(entries),graph,pairs,query,len(valid),'local',valid=valid,
        trace=query_trace,path_weights=query_weights)
    pool=set(prior_trace['candidate_chunk_ids'])
    if pool!=set(background_trace['candidate_chunk_ids']) or pool!=set(query_trace['candidate_chunk_ids']):
        raise ValueError('Source support changed between matched path projections')
    t=time.perf_counter();chunk_rows=await chunk_vectors.score_ids(query,pool)
    affinities={row['id']:cosine(row['distance']) for row in chunk_rows}
    if set(affinities)!=pool:raise ValueError('Missing vector for graph-supported source')
    metadata.update(mode='p0_relation_lift',base_scorer='P0',relation_vector_reads=len(keys),
        relation_score_ms=relation_ms,chunk_vector_reads=len(pool),chunk_score_ms=1000*(time.perf_counter()-t),
        prior_projection_ms=prior_trace['projection_ms'],background_projection_ms=background_trace['projection_ms'],
        query_projection_ms=query_trace['projection_ms'],node_mass=query_trace['node_mass'],
        edge_mass=query_trace['edge_mass'],candidate_chunk_ids=sorted(pool),
        total_scoring_ms=1000*(time.perf_counter()-started))
    return {'prior':prior,'background':background,'conditioned':conditioned,
            'affinities':affinities,'metadata':metadata}


def rank_scoring(bundle,max_chunks=3,mode='full'):
    """Every arm keeps exactly C1's ordered local candidates; only scores vary."""
    if mode not in MODES:raise ValueError('Unknown P0 relation-scoring ablation')
    reference=condition_evidence(bundle['prior'],bundle['affinities'],max_chunks)
    result={}
    for seed,entry in reference.items():
        background=bundle['background'][seed]['PathChunkScores']
        numerator=bundle['prior' if mode=='no_relation' else 'conditioned'][seed]['PathChunkScores']
        values={}
        for cid in entry['Path']:
            base=float(background[cid]);support=float(numerator[cid]);affinity=bundle['affinities'][cid]
            if not math.isfinite(base) or base<=0 or not math.isfinite(support) or support<0:
                raise ArithmeticError('Invalid matched path/source background')
            value=(affinity if mode=='affinity_only' else affinity*support if mode=='no_background'
                   else affinity*support/base)
            if not math.isfinite(value):raise ArithmeticError('Invalid P0 evidence weight')
            values[cid]=value
        result[seed]={'Score':entry['Score'],'Path':list(entry['Path']),'PathChunkScores':values}
    return result


async def project_p0_paths(entries,graph,pairs,query,max_chunks,*,valid,chunk_vectors,relation_vectors,diagnostics=None):
    bundle=await prepare_scoring(entries,graph,pairs,query,valid=valid,
        chunk_vectors=chunk_vectors,relation_vectors=relation_vectors)
    result=rank_scoring(bundle,max_chunks)
    if diagnostics is not None:
        diagnostics.update(bundle['metadata']);diagnostics['selection']='c1_affinity'
    return result
