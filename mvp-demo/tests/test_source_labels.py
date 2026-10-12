import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from table_sources import recover_headers

class SourceLabelTests(unittest.TestCase):
    def test_header_after_sparse_title_preserves_physical_rows(self):
        table=recover_headers({'headers':[None,None,'Experiment 2'],
           'rows':[{'row_idx':2,'values':['Subject','measurement','VO2maxVB']},{'row_idx':3,'values':[4,1.2,68.88]}]})
        self.assertEqual(table['header_row'],2);self.assertEqual(table['headers'][2],'VO2maxVB')
        self.assertEqual(table['rows'][1]['row_idx'],3)

    def test_missing_labels_do_not_use_numeric_values_as_header(self):
        table=recover_headers({'headers':[None,None],'rows':[{'row_idx':2,'values':[4,68.88]}]})
        self.assertEqual(table['headers'],['第 1 列','第 2 列']);self.assertEqual(table['header_row'],1)

    def test_identifier_progression_is_not_presented_as_anomaly(self):
        scan={'relations_blocks':[{'file':'a.csv','sheet':'a','block':{'rows':'2-9','cols':'1-2'},
              'progressions':[{'kind':'arithmetic_progression','col':'Subject','col_idx':0,'n':8,'rule':'sequential',
                'evidence':{'headers':['Subject','measurement'],'rows':[]}}]}]}
        result=app.normalise_scan(scan,'aabbcc112233','a.csv','review')
        self.assertFalse(result['findings']);self.assertEqual(len(result['excluded_signals']),1)

    def test_measured_progression_is_still_visible(self):
        scan={'relations_blocks':[{'file':'a.csv','sheet':'a','progressions':[{
            'kind':'arithmetic_progression','col':'measurement','col_idx':1,'n':8,'rule':'sequential'}]}]}
        self.assertEqual(len(app.normalise_scan(scan,'aabbcc112233','a.csv','review')['findings']),1)

if __name__=='__main__':unittest.main()
