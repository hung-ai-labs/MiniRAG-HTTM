import copy
import unittest
from minirag.extractive_context import catalogue,render_selected,select,verify_output,OMISSION

TEXT='Time: 20260501_10:00\nAlice: Will you join dinner tomorrow?\nBob: Yes, I will.\nAlice: Bring a coat.\nBob: I cannot bring one.\n'


class SourceTests(unittest.TestCase):
    def test_all_utterances_and_header_have_exact_offsets(self):
        cat=catalogue('c',TEXT,'d','prefix '+TEXT+' suffix')
        self.assertEqual(len(cat['unit_ids']),4);self.assertEqual(cat['document_start'],7)
        for s in cat['segments']:self.assertEqual(TEXT[s['start']:s['end']],s['quote'])
        first=cat['segments'][1];self.assertTrue(first['quote'].startswith('Alice:'))
        self.assertIn('Time:',first['score_text'])

    def test_nonadjacent_spans_have_explicit_omission_marker(self):
        cat=catalogue('c',TEXT);units=cat['unit_ids']
        rendered,spans=render_selected(cat,TEXT,[units[0],units[3]])
        self.assertIn(OMISSION,rendered);self.assertIn('cannot',rendered)
        self.assertEqual(len(spans),3)
        with self.assertRaises(ValueError):render_selected(cat,TEXT+'changed',units)

    def test_adjacency_does_not_cross_time_boundary(self):
        text=TEXT+'Time: 20260502_10:00\nBob: Yesterday was different.\n'
        cat=catalogue('c',text);last=cat['segments'][-1]
        self.assertEqual(last['neighbor_ids'],[last['id']])
        self.assertNotIn('cannot',render_selected(cat,text,[last['id']])[0])

    def test_unknown_source_and_ambiguous_document_are_not_invented(self):
        cat=catalogue('c','A paragraph without speakers.','d','A paragraph without speakers. '*2)
        self.assertEqual(cat['document_mapping'],'UNRESOLVED')
        self.assertEqual(cat['segments'][0]['kind'],'raw')


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.cat=catalogue('c',TEXT);self.texts={'c':TEXT};self.cats={'c':self.cat}
        self.scores={u:float(i) for i,u in enumerate(self.cat['unit_ids'])}

    def test_neighbors_keep_reply_with_adjacent_context_and_source_time(self):
        # Budget fits the final two turns but not the complete source.
        ids=self.cat['unit_ids'];rendered,_=render_selected(self.cat,TEXT,ids[-2:])
        result=select(['c'],self.texts,self.cats,self.scores,'neighbors',budget=len(rendered),cost=len)
        self.assertEqual(result['selected_unit_ids']['c'],sorted(ids[-2:]))
        self.assertIn('Bring a coat',result['texts']['c']);self.assertIn('cannot',result['texts']['c'])
        self.assertTrue(verify_output(result,self.texts,self.cats))

    def test_no_bundle_clipping_and_whole_comparator_uses_full_original(self):
        out=select(['c'],self.texts,self.cats,self.scores,'neighbors',budget=3,cost=len)
        self.assertEqual(out['chunk_ids'],[])
        out=select(['c'],self.texts,self.cats,self.scores,'whole',budget=len(TEXT),cost=len)
        self.assertEqual(out['texts']['c'],TEXT);self.assertTrue(verify_output(out,self.texts,self.cats))

    def test_whole_and_fine_grained_use_exact_same_unit_scores(self):
        before=copy.deepcopy((self.cats,self.scores))
        for mode in ('whole','utterance','neighbors'):
            out=select(['c'],self.texts,self.cats,self.scores,mode,budget=500,cost=len)
            self.assertTrue(verify_output(out,self.texts,self.cats));self.assertLessEqual(out['tokens'],500)
        self.assertEqual((self.cats,self.scores),before)

    def test_invalid_score_stale_source_and_unknown_mode_fail(self):
        for texts,scores,mode in [({'c':TEXT+'x'},self.scores,'whole'),
            (self.texts,{},'whole'),(self.texts,self.scores,'other')]:
            with self.assertRaises(ValueError):select(['c'],texts,self.cats,scores,mode,cost=len)

    def test_integrity_verifier_rejects_synthetic_quote(self):
        out=select(['c'],self.texts,self.cats,self.scores,'whole',budget=500,cost=len)
        out['spans']['c'][0]['quote']='fake quotation'
        with self.assertRaises(ValueError):verify_output(out,self.texts,self.cats)

    def test_whole_selection_uses_max_unit_score_and_original_rrf_order_for_output(self):
        cat2=catalogue('d','Time: day\nD: Second source.\n')
        texts={**self.texts,'d':'Time: day\nD: Second source.\n'}
        cats={**self.cats,'d':cat2};scores={**self.scores,cat2['unit_ids'][0]:100.}
        result=select(['c','d'],texts,cats,scores,'whole',budget=10000,cost=len)
        self.assertEqual(result['chunk_ids'],['c','d'])
        result=select(['c','d'],texts,cats,scores,'whole',budget=len(TEXT),cost=len)
        self.assertEqual(result['chunk_ids'],['d'])


if __name__=='__main__':unittest.main()
