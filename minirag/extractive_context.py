"""Source-preserving utterance selection after RRF, before unchanged A1.

RECOMP supplies relevance scores, not entailment, support labels or event truth.
Default OFF. Never use evaluation labels to construct units, scores or selection.
"""
from collections import defaultdict
import hashlib
import math
import re

VERSION='recomp-utterance-v1'
MODES=('whole','utterance','neighbors')
OMISSION='[... omitted original turns ...]'
MARKERS=re.compile(r'^(Time:[^\n]*|[^:\n]{1,90}:[ \t]*)',re.M)


def sha(text):return hashlib.sha256(text.encode()).hexdigest()


def catalogue(cid,text,document_id=None,document_text=None):
    """Keep complete speaker turns. Time headers delimit independent blocks.

    Prefixes and unparsed text are retained as raw context, never invented roles.
    Offsets are Unicode character positions, not bytes or tokenizer offsets.
    """
    matches=list(MARKERS.finditer(text));segments=[];header=None;block=0
    def add(kind,start,end,speaker=None):
        while end>start and text[end-1].isspace():end-=1
        if end<=start:return None
        seg={'id':cid+':'+str(len(segments)),'kind':kind,'start':start,'end':end,
            'quote':text[start:end],'speaker':speaker,'block':block,'header_id':header}
        segments.append(seg);return seg['id']
    if not matches:
        add('raw',0,len(text))
    else:
        if matches[0].start()>0:header=add('header',0,matches[0].start())
        for i,m in enumerate(matches):
            end=matches[i+1].start() if i+1<len(matches) else len(text)
            if m[0].startswith('Time:'):
                block+=1
                header=add('header',m.start(),end)
            else:
                add('utterance',m.start(),end,m[0].split(':',1)[0])
    # A source containing only headers must still remain selectable as raw text.
    if not any(s['kind']!='header' for s in segments):
        segments=[];header=None;block=0;add('raw',0,len(text))
    units=[s for s in segments if s['kind']!='header'];by={s['id']:s for s in segments}
    for u in units:
        siblings=[s['id'] for s in units if s['block']==u['block']]
        i=siblings.index(u['id'])
        u['neighbor_ids']=siblings[max(0,i-1):i+2]
        # Scoring visibility is IDENTICAL for whole-chunk and extractive arms.
        h=by[u['header_id']]['quote']+'\n' if u['header_id'] else ''
        u['score_text']=h+u['quote']
    offset=(document_text.index(text) if document_text is not None and document_text.count(text)==1 else None)
    return {'chunk_id':cid,'text_sha256':sha(text),'document_id':document_id,
        'document_start':offset,'document_mapping':'EXACT_UNIQUE' if offset is not None else 'UNRESOLVED',
        'segments':segments,'unit_ids':[s['id'] for s in units],
        'semantic_status':'UNASSESSED','version':VERSION}


def render_selected(cat,text,unit_ids):
    if sha(text)!=cat['text_sha256']:raise ValueError('Stale source text')
    chosen=set(unit_ids)
    if not chosen<=set(cat['unit_ids']):raise ValueError('Unknown source unit')
    if not chosen:return '',[]
    segments=cat['segments'];by={s['id']:s for s in segments}
    headers={by[u]['header_id'] for u in chosen}-{None}
    selected=[s for s in segments if s['id'] in chosen or s['id'] in headers]
    pieces=[];spans=[];last_end=None
    for s in selected:
        if text[s['start']:s['end']]!=s['quote']:raise ValueError('Quote/offset mismatch')
        if last_end is not None and text[last_end:s['start']].strip():pieces.append(OMISSION)
        pieces.append(s['quote']);last_end=s['end']
        spans.append({'segment_id':s['id'],'kind':s['kind'],'speaker':s['speaker'],
            'start':s['start'],'end':s['end'],'quote':s['quote'],
            'document_start':cat['document_start']+s['start'] if cat['document_start'] is not None else None})
    return '\n'.join(pieces),spans


def prefix(ranked,texts,budget,cost):
    kept=[];total=0
    for c in ranked:
        n=cost(texts[c])
        if total+n>budget:break
        kept.append(c);total+=n
    return kept


def select(ranked,texts,catalogues,scores,mode,*,budget=4000,cost=None):
    """Rank by relevance, scan for fitting units; never divide score by token cost.

    Whole chunks use max of EXACTLY the same unit scores, not another encoder.
    neighbors adds both adjacent original turns, within a single Time block.
    A neighbor bundle that cannot fit is skipped as a whole, never clipped.
    """
    if mode not in MODES:raise ValueError('Unknown extractive selection mode')
    if not 0<budget or len(ranked)>60 or len(set(ranked))!=len(ranked):raise ValueError('Invalid budget/pool')
    if cost is None:
        from .utils import encode_string_by_tiktoken
        cost=lambda s:len(encode_string_by_tiktoken(s))
    order={c:i for i,c in enumerate(ranked)}
    for c in ranked:
        if sha(texts[c])!=catalogues[c]['text_sha256']:raise ValueError('Stale source catalogue')
        for u in catalogues[c]['unit_ids']:
            if u not in scores or not math.isfinite(scores[u]):raise ValueError('Missing/nonfinite unit score')
    selection=defaultdict(set);actual_text={};source_spans={};total=0;targets=[];skipped=0
    if mode=='whole':
        chunk_scores={c:max(scores[u] for u in catalogues[c]['unit_ids']) for c in ranked}
        for c in sorted(ranked,key=lambda c:(-round(chunk_scores[c],10),order[c])):
            n=cost(texts[c])
            if total+n<=budget:
                actual_text[c]=texts[c];total+=n;selection[c].update(catalogues[c]['unit_ids'])
                source_spans[c]=[{'segment_id':c+':whole','kind':'whole','start':0,'end':len(texts[c]),
                    'quote':texts[c],'document_start':catalogues[c]['document_start'],'speaker':None}]
            else:skipped+=1
    else:
        units=[(c,s) for c in ranked for s in catalogues[c]['segments'] if s['kind']!='header']
        for c,u in sorted(units,key=lambda cu:(-round(scores[cu[1]['id']],10),order[cu[0]],cu[1]['start'])):
            uid=u['id']
            if uid in selection[c]:continue
            desired=selection[c]|set(u['neighbor_ids'] if mode=='neighbors' else [uid])
            rendered,spans=render_selected(catalogues[c],texts[c],desired)
            proposal=total-cost(actual_text[c]) if c in actual_text else total
            proposal+=cost(rendered)
            if proposal>budget:skipped+=1;continue
            selection[c]=desired;actual_text[c]=rendered;source_spans[c]=spans;total=proposal
            targets.append({'target_unit_id':uid,'source_chunk_id':c,
                'closure_ids':u['neighbor_ids'] if mode=='neighbors' else [uid],
                'dependency_status':'ADJACENT_TURNS_ONLY_SEMANTICS_UNVERIFIED'})
    kept=[c for c in ranked if c in actual_text]
    assert sum(cost(actual_text[c]) for c in kept)==total<=budget
    output={'mode':mode,'chunk_ids':kept,'texts':{c:actual_text[c] for c in kept},
        'spans':{c:source_spans[c] for c in kept},
        'selected_unit_ids':{c:sorted(selection[c]) for c in kept},
        'target_bundles':targets,'tokens':total,'skipped_nonfitting':skipped,
        'dependency_claim':'Local adjacency only, not guaranteed coreference/semantic completeness',
        'source_integrity':'EXACT_SPANS','semantic_status':'UNASSESSED'}
    return output


def verify_output(result,texts,cats):
    for c in result['chunk_ids']:
        if sha(texts[c])!=cats[c]['text_sha256']:raise ValueError('Source hash mismatch')
        for s in result['spans'][c]:
            if texts[c][s['start']:s['end']]!=s['quote']:raise ValueError('Output span not verbatim')
        if result['mode']=='whole':
            if result['texts'][c]!=texts[c]:raise ValueError('Whole comparator changed text')
        else:
            rendered,spans=render_selected(cats[c],texts[c],result['selected_unit_ids'][c])
            if result['texts'][c]!=rendered or result['spans'][c]!=spans:raise ValueError('Rendered source mismatch')
    for bundle in result['target_bundles']:
        c=bundle['source_chunk_id']
        if not set(bundle['closure_ids'])<=set(result['selected_unit_ids'][c]):raise ValueError('Dependency clipped')
    return True


def runtime_select(query,ranked,texts,store,mode):
    """Local-only inference hook; fail clearly rather than changing the model."""
    import json
    import os
    from pathlib import Path
    from .recomp_encoder import RecompEncoder,DEFAULT_MODEL_DIR
    directory=Path(os.environ.get('MINIRAG_RECOMP_MODEL_DIR',str(DEFAULT_MODEL_DIR)))
    cache=os.environ.get('MINIRAG_RECOMP_CACHE','').strip() or None
    key=(str(directory),cache)
    if key not in _RUNTIME_MODELS:_RUNTIME_MODELS[key]=RecompEncoder(directory,cache)
    encoder=_RUNTIME_MODELS[key]
    docs_path=Path(store._file_name).with_name('kv_store_full_docs.json')
    with docs_path.open() as f:docs=json.load(f)
    cats={}
    for c in ranked:
        docid=store._data[c].get('full_doc_id')
        cats[c]=catalogue(c,texts[c],docid,docs.get(docid,{}).get('content'))
    result=select(ranked,texts,cats,encoder.score(query,cats),mode)
    verify_output(result,texts,cats)
    result['model_provenance']=encoder.provenance
    return result


_RUNTIME_MODELS={}
