import os
import asyncio
import unittest
from collections import Counter
from datetime import date
from unittest.mock import patch

from minirag import temporal


class TemporalTest(unittest.TestCase):
    def test_parser_day_formats_and_month_names(self):
        years = {2026}
        expected = temporal.day_node(date(2026, 4, 8))
        for query in ('20260408', '2026-04-08', '2026/04/08', 'April 8, 2026',
                      'Apr. 8', '8 April 2026', '8 Apr'):
            with self.subTest(query=query):
                self.assertEqual(temporal.parse_query(query, years), (expected,))

    def test_parser_month_rules_and_invalid(self):
        month = temporal.month_node(2026, 4)
        self.assertEqual(temporal.parse_query('during April', {2026}), (month,))
        self.assertEqual(temporal.parse_query('April 2026', {2026, 2027}), (month,))
        self.assertEqual(temporal.parse_query('April', {2026}), ())
        self.assertEqual(temporal.parse_query('in April', {2026, 2027}), ())
        self.assertEqual(temporal.parse_query('April 31, 2026', {2026}), ())
        self.assertEqual(temporal.parse_query('20260230', {2026}), ())
        self.assertEqual(temporal.parse_query("April Fool's", {2026}), ())
        self.assertEqual(temporal.parse_query('next Tuesday', {2026}), ())
        self.assertEqual(temporal.parse_query('yesterday', {2026}), ())
        self.assertEqual(temporal.parse_query('in next April', {2026}), ())
        self.assertEqual(temporal.parse_query('April 8 next year', {2026}), ())
        self.assertEqual(temporal.parse_query('April 8 in April', {2026}),
                         (temporal.day_node(date(2026, 4, 8)),))

    def test_overlay_uses_document_header_and_full_doc_id(self):
        docs = {'d': {'content': 'Time: 20260408_08:38\ntext'},
                'bad': {'content': 'event was 20260409'}}
        chunks = {'c': {'full_doc_id': 'd'}, 'x': {'full_doc_id': 'bad'}}
        by_time, years = temporal.overlay(docs, chunks)
        self.assertEqual(years, {2026})
        self.assertEqual(by_time[temporal.day_node(date(2026, 4, 8))], ['c'])
        self.assertEqual(by_time[temporal.month_node(2026, 4)], ['c'])

    def test_switch_off_and_no_anchor(self):
        with patch.dict(os.environ, {'MINIRAG_TEMPORAL': '0'}), \
             patch.object(temporal, 'loaded_overlay', side_effect=AssertionError('read')):
            self.assertEqual(temporal.active('April 8', object()), ((), None))
        with patch.dict(os.environ, {'MINIRAG_TEMPORAL': '1'}), \
             patch.object(temporal, 'loaded_overlay', return_value=({}, {2026})):
            self.assertEqual(temporal.active('Who is Alice?', object()), ((), None))

    def test_h_score_boost_and_ties(self):
        import networkx as nx
        graph = nx.Graph()
        graph.add_node('s', source_id='a<SEP>b')
        graph.add_node('z', source_id='a')
        h = temporal.entity_h(graph, [('u', 's', .5), ('u', 's', .5), ('v', 'z', -.2)])
        self.assertEqual(h['a'], 1.5)
        self.assertEqual(h['b'], 1.5)
        scores = Counter({'old': 3, 'a': 2, 'b': 2})
        order, lists = temporal.rank_temporal(scores, {'time:day:2026-04-08': ['a', 'b', 'new']},
                                              ['time:day:2026-04-08'], h, ['a'])
        self.assertEqual(lists['time:day:2026-04-08'], ['a', 'b', 'new'])
        self.assertEqual(order[:3], ['a', 'b', 'new'])
        self.assertEqual(temporal.rank_temporal(scores, {'t': ['a', 'b', 'new']}, ['t'], h,
                                                ['a'], expand=False)[0], ['a', 'b', 'old'])
        self.assertEqual(temporal.rank_temporal(scores, {}, (), h, [])[0],
                         [cid for cid, _ in scores.most_common()])
        self.assertEqual(order, temporal.rank_temporal(scores, {'time:day:2026-04-08': ['a', 'b', 'new']},
                                                       ['time:day:2026-04-08'], h, ['a'])[0])

    def test_cpaper_step1_union(self):
        graph = {'a', 'b', 'c'}
        self.assertEqual(temporal.candidate_ids(graph, ['a'], ['b']), {'a', 'b'})
        self.assertEqual(temporal.candidate_ids(graph, ['a'], ['b'], expand=False), {'a'})

    def test_cpaper_temporal_candidate_reaches_step2(self):
        import networkx as nx
        from minirag import QueryParam, cpaper
        from tests.test_cpaper import VDB, Chunks, Storage, embed
        graph = nx.Graph()
        graph.add_node('A', entity_type='"PERSON"', source_id='c2', description='gold')
        graph.add_node('B', entity_type='"PLACE"', source_id='c1', description='plain')
        graph.add_edge('A', 'B', description='relation', keywords='relation', weight=1)
        args = (['A'], ['person'], 'gold', Storage(graph),
                VDB({'A': [{'entity_name': 'A', 'distance': .9}]}),
                VDB({'gold': [{'src_id': 'A', 'tgt_id': 'B'}]}),
                VDB({'A': [{'id': 'c2', 'distance': .8}],
                     'gold': [{'id': 'c1', 'distance': .9}]}),
                Chunks({'c1': 'plain', 'c2': 'gold text'}), embed, QueryParam(top_k=2))
        t = 'time:day:2026-04-08'
        with patch.dict(os.environ, {'MINIRAG_TEMPORAL': '1', 'MINIRAG_PAPER_MODE': '1'}, clear=False), \
             patch.object(cpaper, 'temporal_active', return_value=((t,), {t: ['c2']})), \
             patch.object(cpaper, 'encode_string_by_tiktoken', side_effect=lambda s: s.split()), \
             patch.object(cpaper, 'truncate_list_by_token_size', side_effect=lambda rows, **kw: rows):
            full = asyncio.run(cpaper.build_context(*args))
            with patch.dict(os.environ, {'MINIRAG_TEMPORAL_EXPAND': '0'}, clear=False):
                noexpand = asyncio.run(cpaper.build_context(*args))
        self.assertIn('gold text', full)
        self.assertNotIn('gold text', noexpand)


if __name__ == '__main__':
    unittest.main()
