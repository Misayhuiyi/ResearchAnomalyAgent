import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class SourceEvidenceTests(unittest.TestCase):
    def test_rounding_recovers_raw_precision_only_inside_original_block(self):
        table = {'headers': ['other', 'isotope'], 'rows': [
            {'row_idx': 2, 'values': ['-25.14594', '-25.14594']},
            {'row_idx': 3, 'values': ['-25.12261', '-25.12261']},
            {'row_idx': 4, 'values': ['-25.13993', '-25.13993']}]}
        block = {'file': 'raw.csv', 'sheet': 'raw', 'block': {'rows': '2-3', 'cols': '2-2'}}
        item = {'kind': 'identical_after_rounding', 'n_cells': 2, 'rounded_to': -25.1,
                'example_values': [-25.1459, -25.1226], 'example_cells': [[2,2]],
                'evidence': {'headers': ['NA'], 'col_offset': 1, 'highlight_cols': [1],
                             'rows': [{'row_idx':2, 'values':[-25.1459]}]}}
        result = app._normalise_finding(block, item, 'identical_after_rounding', 1, {'raw': table})
        self.assertEqual([c['original'] for c in result['evidence']['focus_cells']], [-25.14594, -25.12261])
        self.assertEqual(result['evidence']['headers'], ['isotope'])
        self.assertEqual(result['evidence']['rows'][0]['values'], ['-25.14594'])
        self.assertEqual(result['evidence']['highlight_cols'], [1])
        self.assertIn('若保留', result['summary_cn'])
        self.assertIn('不表示原文件', result['evidence']['note_cn'])
        wrong = app._normalise_finding({**block,'sheet':'missing'}, item, 'identical_after_rounding',1,{'raw':table})
        self.assertEqual(wrong['evidence']['focus_cells'], [])

    def test_source_rows_are_bounded_and_limit_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'raw.csv';path.write_text('a,b\n1,2\n3,4\n5,6\n', encoding='utf-8')
            with patch.object(app.statistical_checks,'MAX_ROWS',2):
                table=app._load_source_tables(path)['raw']
            self.assertEqual(len(table['rows']),2)
            self.assertTrue(table['limited'])

    def test_column_name_uses_absolute_zero_based_engine_coordinate(self):
        result=app._normalise_finding({'file':'raw.csv','sheet':'raw'},
            {'kind':'rounded_to_half_or_int','col':'NA','col_idx':2,'n':4,'count_05':4},
            'within_col',1,{'raw':{'headers':['a','b','mass'],'rows':[]}})
        self.assertEqual(result['columns'],['mass'])
        self.assertIn('mass',result['summary_cn'])
        self.assertNotIn('数值模式异常',result['title_cn'])


if __name__=='__main__': unittest.main()
