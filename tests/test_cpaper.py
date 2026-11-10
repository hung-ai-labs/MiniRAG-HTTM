import asyncio
import os
import unittest
from unittest.mock import patch

import networkx as nx
import numpy as np

from minirag import QueryParam
from minirag import cpaper
from minirag.operate import _build_mini_query_context


class VDB:
    def __init__(self, data):
        self.data = data
        self.calls = []

    async def query(self, text, top_k=5):
        self.calls.append((text, top_k))
        return self.data.get(text, [])[:top_k]


class Chunks:
    def __init__(self, contents):
        self.contents = contents

    async def get_by_ids(self, ids):
        return [await self.get_by_id(cid) for cid in ids]

    async def get_by_id(self, cid):
        return {'content': self.contents[cid]} if cid in self.contents else None


class Storage:
    def __init__(self, graph):
        self._graph = graph

    async def get_node_from_types(self, types):
        return []


async def embed(texts):
    return np.asarray([[1., 0.] if 'gold' in t else [0., 1.] for t in texts])


class CPaperTest(unittest.TestCase):
    def graph(self):
        g = nx.Graph()
        g.add_node('A', entity_type='"PERSON"', source_id='c1<SEP>c2',
                   description='first<SEP>gold relation')
        g.add_node('B', entity_type='"PLACE"', source_id='c2', description='second')
        g.add_node('C', entity_type='"PERSON"', source_id='c3<SEP>c4',
                   description='unaligned')
        g.add_edge('A', 'B', description='A relates B', keywords='relation', weight=1)
        g.add_edge('B', 'C', description='B relates C', keywords='relation', weight=1)
        return g

    def test_edge_description_alignment_and_fallback(self):
        _, owners, desc = cpaper.build_heterogeneous_graph(self.graph())
        self.assertEqual(desc[('A', 'c1')], 'first')
        self.assertEqual(desc[('A', 'c2')], 'gold relation')
        self.assertEqual(desc[('C', 'c3')], 'unaligned')
        self.assertEqual(desc[('C', 'c4')], 'unaligned')
        self.assertEqual(owners['c2'], {'A', 'B'})

    def test_answers_only_from_starting_set(self):
        self.assertEqual(cpaper.answer_nodes(self.graph(), {'A', 'B'}, ['person']), {'A'})

    def test_paths_are_simple_bounded_and_deterministic(self):
        graph, _, _ = cpaper.build_heterogeneous_graph(self.graph())
        one = cpaper.enumerate_paths(graph, 'A', cap=1)
        self.assertEqual(one, cpaper.enumerate_paths(graph, 'A', cap=1))
        self.assertTrue(all(len(p) == 5 for p in one[0]))
        self.assertTrue(all(len(p) == len(set(p)) for p in one[0]))
        self.assertTrue(one[1])

    def test_step2_descriptions_and_step3_pack(self):
        owners = {'c1': {'A'}, 'c2': {'B'}}
        desc = {('A', 'c1'): 'plain', ('B', 'c2'): 'gold'}
        contents = {'c1': 'plain', 'c2': 'plain'}
        ranked = asyncio.run(cpaper.rank_chunks('gold', {'c1', 'c2'}, contents, owners, desc, embed))
        self.assertEqual([cid for cid, _ in ranked], ['c2', 'c1'])
        no_edge = asyncio.run(cpaper.rank_chunks('gold', {'c1', 'c2'}, contents, owners, desc,
                                                  embed, with_descriptions=False))
        self.assertEqual([cid for cid, _ in no_edge], ['c1', 'c2'])  # lexical tie
        ids = [f'c{i}' for i in range(7)]
        packed, used = cpaper.pack_chunks(ids, {cid: 'x' for cid in ids}, lambda _: 1000)
        self.assertEqual((packed, used), (ids[:5], 5000))
        packed, used = cpaper.pack_chunks(ids, {cid: 'x' for cid in ids}, lambda _: 2001)
        self.assertEqual((packed, used), (ids[:2], 4002))

    def test_mode_off_never_calls_paper(self):
        with patch.dict(os.environ, {'MINIRAG_PAPER_MODE': '0'}, clear=False), \
             patch.object(cpaper, 'build_context', side_effect=AssertionError('paper called')):
            result = asyncio.run(_build_mini_query_context(
                ['A'], [], 'question', Storage(nx.Graph()), None, VDB({}), VDB({}),
                VDB({}), Chunks({}), embed, QueryParam(top_k=2)))
        self.assertIsNone(result)

    def test_full_steps_intersection_top5_context_determinism(self):
        graph = self.graph()
        storage = Storage(graph)
        name_db = VDB({'A': [{'entity_name': 'A', 'distance': .9}]})
        chunk_db = VDB({'A': [{'id': 'c1', 'distance': .8}],
                              'question': [{'id': 'c2', 'distance': .9}]})
        edge_db = VDB({'question': [{'src_id': 'A', 'tgt_id': 'B'}]})
        chunks = Chunks({'c1': 'plain', 'c2': 'gold text', 'c3': 'plain'})
        with patch.dict(os.environ, {'MINIRAG_PAPER_MODE': '1'}, clear=False), \
             patch.object(cpaper, 'encode_string_by_tiktoken', side_effect=lambda s: s.split()), \
             patch.object(cpaper, 'truncate_list_by_token_size', side_effect=lambda rows, **kw: rows):
            args = (['A'], ['person'], 'question', storage, None, name_db,
                    edge_db, chunk_db, chunks, embed, QueryParam(top_k=2))
            ctx1 = asyncio.run(_build_mini_query_context(*args))
            ctx2 = asyncio.run(_build_mini_query_context(*args))
        self.assertEqual(ctx1, ctx2)
        self.assertIn('gold text', ctx1)
        self.assertNotIn('plain\n', ctx1)
        self.assertIn('-----Relationships-----', ctx1)
        self.assertIn('B relates C', ctx1)
        self.assertIn('-----Entities-----', ctx1)
        self.assertNotIn('unaligned', ctx1)  # C not a starting answer node
        with patch.dict(os.environ, {'MINIRAG_PAPER_MODE': '1', 'MINIRAG_CPAPER_INTERSECTION': '0'}, clear=False), \
             patch.object(cpaper, 'encode_string_by_tiktoken', side_effect=lambda s: s.split()), \
             patch.object(cpaper, 'truncate_list_by_token_size', side_effect=lambda rows, **kw: rows):
            without_intersection = asyncio.run(_build_mini_query_context(*args))
        self.assertIn('plain', without_intersection)


if __name__ == '__main__':
    unittest.main()
