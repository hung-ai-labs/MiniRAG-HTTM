"""Offline checkpoint/path tests; no model or network calls."""

import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT=Path(os.environ.get('MINIRAG_2WIKI_REPO',Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(ROOT/'reproduce/research'))
spec=importlib.util.spec_from_file_location('local_index_pilot',ROOT/'reproduce/research/local_index_pilot.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_pilot_paths_protect_other_indexes(tmp_path):
    with pytest.raises(ValueError,match='direct child'):
        m.check_paths(tmp_path/'LiHua-World',tmp_path/'runs/2wiki/local/a',tmp_path,False)
    index=tmp_path/'indexes/2wiki-local-q4km-pilot-test'
    run=tmp_path/'runs/2wiki/local/pilot-test'
    m.check_paths(index,run,tmp_path,False)
    index.mkdir(parents=True)
    with pytest.raises(ValueError,match='existing'):
        m.check_paths(index,run,tmp_path,False)


def test_resume_refuses_changed_identity():
    stored={'identity':{'docs':'same','model':'q4','seed':101}}
    m.require_matching_identity(stored,stored['identity'])
    with pytest.raises(ValueError,match='identity'):
        m.require_matching_identity(stored,{'docs':'changed','model':'q4','seed':101})


def test_torn_checkpoint_is_detected_without_rewriting(tmp_path):
    f=tmp_path/'kv_store_doc_status.json'
    f.write_text('{"doc1":{"status":"processed"}}')
    state={'committed_store_sha256':m.stores_hash(tmp_path)}
    m.require_clean_checkpoint(tmp_path,state)
    f.write_text('{"doc1":{"status":"processed"},"uncommitted":{}}')
    torn=f.read_bytes()
    with pytest.raises(ValueError,match='in-place repair'):
        m.require_clean_checkpoint(tmp_path,state)
    assert f.read_bytes()==torn


def test_index_links_detect_missing_vectors(tmp_path):
    import networkx as nx
    values={'kv_store_doc_status.json':{'doc-a':{'status':'processed'}},
            'kv_store_full_docs.json':{'doc-a':{'content':'text'}},
            'kv_store_text_chunks.json':{'chunk-a':{'full_doc_id':'doc-a'}},
            'vdb_chunks.json':{'data':[{'__id__':'chunk-a'}]},'extracted_chunks.json':['chunk-a']}
    for name,data in values.items():
        (tmp_path/name).write_text(json.dumps(data))
    graph=nx.Graph()
    graph.add_node('entity',source_id='chunk-a')
    nx.write_graphml(graph,tmp_path/'graph_chunk_entity_relation.graphml')
    docs=[{'minirag_doc_id':'doc-a'}]
    chunks={'chunk-a':{'full_doc_id':'doc-a'}}
    checks,counts=m.verify(tmp_path,docs,chunks)
    assert all(checks.values()) and counts['chunks']==1
    (tmp_path/'vdb_chunks.json').write_text('{"data":[]}')
    checks,_=m.verify(tmp_path,docs,chunks)
    assert checks['chunk_vectors_match'] is False


def test_stage_stats_count_truncation_and_errors():
    records=[{'status':'ok','phase':'extract','latency_s':2,'response':{'eval_count':100,'done_reason':'length'}},
             {'status':'ok','phase':'glean','latency_s':3,'response':{'eval_count':50,'done_reason':'stop'}},
             {'status':'failed','phase':'extract','latency_s':1}]
    result=m.stats(records,1,200)
    assert result['requests_failed']==1 and result['length_truncated']==1
    assert result['truncation_fraction']==.5
    assert result['remaining_pilot_model_seconds_extrapolated']==995
