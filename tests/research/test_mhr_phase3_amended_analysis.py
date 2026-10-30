"""Amended audit must bind native receipts and preserve every original valid slot."""
import copy
import json
import unittest
from reproduce.research import mhr_phase3_amended_analysis as a


def fixture():
    questions={'q':{'Type':'null'},'other':{'Type':'comparison'}}
    latest={(q,p):{'query_id':q,'pass':p,'status':'parse_failed' if q=='q' else 'ok',
                  'label':None if q=='q' else 'accurate'} for q in questions for p in (1,2,3)}
    identity={'query_id':'q','model':'model','prompt_sha256':'prompt','evaluation_version':'amended',
              'response_format':{'schema':'fixed'}}
    valid={}
    for p,label in ((1,'neither'),(2,'error'),(3,'accurate')):
        raw=json.dumps({'label':label})
        valid[p]={'raw':raw,'response_model':'model','finish_reason':'stop',
            'requests':[{'ok':True,'prompt_sha256':'prompt','response_text':raw}]}
    return questions,latest,identity,valid


class AmendedAuditTests(unittest.TestCase):
    def test_effect_display_uses_discordant_counts_without_double_rounding(self):
        d={'seeds':{'202':{'paired_C1_vs_C0':{'all':{'n':2156,'primary_accurate':
           {'up':439,'down':234,'diff':9.5,'p':0.001,'ci95':[7.19,11.83]}}}}}}
        a.exact_effect_displays(d)
        p=d['seeds']['202']['paired_C1_vs_C0']['all']['primary_accurate']
        self.assertEqual(p['diff'],9.51)
        self.assertEqual(p['diff_from_rounded_rates_pp'],9.5)
        self.assertEqual(p['p'],0.001)
        self.assertEqual(p['ci95'],[7.19,11.83])

    def test_merge_keeps_original_votes_and_raw_json(self):
        q,old,i,v=fixture();before=copy.deepcopy(old)
        merged=a.merge_votes(old,v,q,i)
        self.assertEqual(old,before)
        self.assertEqual(merged[('other',1)],old[('other',1)])
        self.assertEqual(merged[('q',1)]['label'],'neither')
        self.assertEqual(merged[('q',1)]['attempts'][0]['raw'],v[1]['raw'])

    def test_refuse_overwrite_of_existing_valid_vote(self):
        q,old,i,v=fixture();old[('q',1)]|={'status':'ok','label':'error'}
        with self.assertRaises(ValueError):a.merge_votes(old,v,q,i)

    def test_refuse_receipt_prompt_or_raw_mismatch(self):
        for field,value in (('prompt_sha256','other'),('response_text','{"label":"error"}')):
            q,old,i,v=fixture();v[1]['requests'][0][field]=value
            with self.assertRaises(ValueError):a.merge_votes(old,v,q,i)

    def test_refuse_incomplete_scope_or_wrong_model(self):
        q,old,i,v=fixture();del v[3]
        with self.assertRaises(ValueError):a.merge_votes(old,v,q,i)
        q,old,i,v=fixture();v[1]['response_model']='other-model'
        with self.assertRaises(ValueError):a.merge_votes(old,v,q,i)


if __name__=='__main__':unittest.main()
