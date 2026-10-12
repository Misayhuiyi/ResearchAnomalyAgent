import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pattern_checks as patterns
from statistical_checks import number


def inspect(headers, values, mode='vectors'):
    rows=[{'row_idx':i+2,'values':row} for i,row in enumerate(values)]
    return patterns.check_table('sample.csv','sheet',headers,rows,mode,number)


class PatternTests(unittest.TestCase):
    def ids(self, result):
        return {hit for f in result[0] for hit in f['rule_ids']}

    def test_fixed_difference_ratio_linear_and_decimal_scaling(self):
        rows=[[str(x),str(x+3),str(x*10),str(2*x+3)] for x in [1,4,2,6,9,3]]
        found,coverage=inspect(['a','b','c','d'],rows)
        ids=self.ids((found,coverage))
        self.assertTrue({'DET-02a','DET-02b','DET-02c','DET-03b'} <= ids)
        self.assertTrue(all(f['evidence']['comparison'][0]['left']['row_idx']==2 for f in found))
        self.assertTrue(all('rule_version' in f for f in found))

    def test_same_sequence_and_subset(self):
        rows=[[str(x),str(y)] for x,y in zip([99,1,4,2,6,9,98],[77,1,4,2,6,9,88])]
        self.assertIn('DET-01a',self.ids(inspect(['a','b'],rows)))
        self.assertIn('DET-01a',self.ids(inspect(['a','b'],[[str(x),str(x)] for x in [1,4,2,6,9]])))

    def test_reordering_unique_and_ambiguous_duplicate_values(self):
        unique=inspect(['a','b'],[[str(x),str(y)] for x,y in zip([1,2,3,4,5],[5,3,1,4,2])])
        self.assertTrue({'DET-01b','DET-03c'} <= self.ids(unique))
        reorder=next(f for f in unique[0] if 'DET-03c' in f['rule_ids'])
        self.assertTrue(reorder['evidence'].get('comparison'))
        ambiguous=inspect(['a','b'],[[str(x),str(y)] for x,y in zip([1,1,2,3,4],[4,1,3,2,1])])
        reorder=next(f for f in ambiguous[0] if 'DET-03c' in f['rule_ids'])
        self.assertFalse(reorder['evidence'].get('comparison'))
        self.assertIn('不唯一',reorder['summary_cn'])

    def test_precision_tail_and_rounding_checks(self):
        rows=[['0.451','0.452'],['0.471','0.472'],['0.491','0.492'],['0.521','0.522'],['0.531','0.532']]
        ids=self.ids(inspect(['a','b'],rows))
        self.assertIn('DET-03a',ids)
        self.assertIn('DET-04a',ids)
        mixed=inspect(['a'],[['1.0'],['1.00'],['2.00'],['3.00'],['4.00']])
        self.assertIn('DET-04b',self.ids(mixed))

    def test_terminal_digits_are_descriptive_not_significance(self):
        found,_=inspect(['a'],[[str(x)+'.11'] for x in range(8)])
        digit=next(f for f in found if 'DET-04c' in f['rule_ids'])
        self.assertEqual('info',digit['severity'])
        self.assertNotIn('p_value',digit['calculation'])
        self.assertEqual(digit['calculation']['longest_equal_tail_run'],8)

    def test_unrelated_vectors_do_not_gain_relation_hits(self):
        ids=self.ids(inspect(['a','b'],[['1.123','8.419'],['4.239','2.374'],['2.385','6.582'],['8.451','1.637'],['6.567','5.796']]))
        self.assertFalse(ids & {'DET-01a','DET-02a','DET-02b','DET-02c','DET-03c'})

    def test_missing_short_or_constant_vectors_not_fitted(self):
        for rows in [[['1','2'],['2','4']], [['1','2']]*8, [['1','2'],['','4'],['3','6'],['4','8'],['5','10']]]:
            self.assertFalse(self.ids(inspect(['a','b'],rows)) & {'DET-02a','DET-02b','DET-02c'})

    def test_weighted_relation_requires_explicit_weights_and_variable_inputs(self):
        headers=['输入1','输入2','权重1','权重2','结果']
        rows=[[str(x),str(x*x),'0.25','0.75',str(.25*x+.75*x*x)] for x in range(1,7)]
        self.assertIn('DET-02d',self.ids(inspect(headers,rows,'weighted')))
        rows[-1][-1]='999'
        self.assertNotIn('DET-02d',self.ids(inspect(headers,rows,'weighted')))
        _, coverage=inspect(headers[:-1],[r[:-1] for r in rows],'weighted')
        self.assertEqual('insufficient',coverage[0]['status'])

    def test_time_alignment_not_row_order(self):
        rows=[]
        for i,x in enumerate([1,4,2,6,9,3]):
            rows.extend([['A',str(i),str(x)],['B',str(i),str(x+5)]])
        ids=self.ids(inspect(['对象','时间','数值'],list(reversed(rows)),'time'))
        self.assertIn('DET-08b',ids)
        rows[1][1]='100'
        self.assertNotIn('DET-08b',self.ids(inspect(['对象','时间','数值'],rows,'time')))

    def test_duplicate_time_not_silently_deduplicated(self):
        _,coverage=inspect(['对象','时间','数值'],[['A','0','1'],['A','0','2'],['B','0','1']],'time')
        self.assertTrue(any(c['status']=='insufficient' for c in coverage))

    def test_time_difference_relationship_has_original_values(self):
        rows=[[obj,str(i),str(v)] for obj,values in [('A',[0,1,4,9,16,25]),('B',[0,2,6,12,20,30])] for i,v in enumerate(values)]
        result=inspect(['对象','时间','数值'],rows,'time')
        hit=next(f for f in result[0] if 'DET-08b' in f['rule_ids'])
        self.assertIn('变化量',hit['summary_cn'])
        self.assertEqual(hit['calculation']['left_differences'],['1','3','5','7','9'])
        self.assertEqual(hit['evidence']['comparison'][2]['left']['value'],'4')

    def test_explicit_sum_sequence_and_denominator(self):
        summed=inspect(['组成1','组成2','合计'],[['1.00','2.00','9.00']],'sums')
        self.assertIn('DET-09a',self.ids(summed))
        self.assertNotIn('DET-09a',self.ids(inspect(['组成1','组成2','合计'],[['1.00','2.00','3.00']],'sums')))
        seq=inspect(['顺序','数值'],[[str(i),str(i*3+2)] for i in range(6)],'sequence')
        self.assertIn('DET-09b',self.ids(seq))
        proportion=inspect(['分子','分母','比例'],[['1','3','0.80']],'denominator')
        self.assertIn('DET-09c',self.ids(proportion))
        self.assertNotIn('DET-09c',self.ids(inspect(['分子','分母','比例'],[['1','3','0.33']],'denominator')))

    def test_each_mode_discloses_insufficient_input(self):
        for mode in patterns.MODES:
            _, coverage=inspect(['unrelated'],[['']],mode)
            self.assertTrue(coverage)
            self.assertTrue(all(c['status']=='insufficient' for c in coverage),coverage)

    def test_every_vector_subrule_has_hit_normal_and_insufficient(self):
        x=['1.123','4.239','2.385','8.451','6.567']
        y=['8.419','2.374','6.582','1.637','5.796']
        hit_pairs={
            'DET-01a':(['1','4','2','6','9'],['1','4','2','6','9']),
            'DET-01b':(['1','4','2','6','9'],['9','6','1','4','2']),
            'DET-01c':(['1','4','2','6','9'],['3','9','5','13','19']),
            'DET-02a':(['1','4','2','6','9'],['4','7','5','9','12']),
            'DET-02b':(['1','4','2','6','9'],['2','8','4','12','18']),
            'DET-02c':(['1','4','2','6','9'],['5','11','7','15','21']),
            'DET-03a':(['1.111','4.111','2.111','6.111','9.111'],['1.112','4.112','2.112','6.112','9.112']),
            'DET-03b':(['1','4','2','6','9'],['10','40','20','60','90']),
            'DET-03c':(['1','4','2','6','9'],['9','6','1','4','2']),
            'DET-04a':(['0.451','0.471','0.491','0.521','0.531'],['1','4','2','6','9']),
            'DET-04b':(['1.0','2.00','3.00','4.00','5.00'],['1','4','2','6','9']),
        }
        for rule,(left,right) in hit_pairs.items():
            with self.subTest(rule=rule):
                self.assertIn(rule,self.ids(inspect(['a','b'],list(map(list,zip(left,right))))))
                self.assertNotIn(rule,self.ids(inspect(['a','b'],list(map(list,zip(x,y))))))
                missing=inspect(['a','b'],[['1','2']])[1]
                self.assertEqual(next(c for c in missing if c['rule_id']==rule)['status'],'insufficient')

    def test_digit_frequency_normal_distribution_is_not_significance(self):
        result=inspect(['a'],[[f'{i}.{i}'] for i in range(10)])
        hit=next(f for f in result[0] if 'DET-04c' in f['rule_ids'])
        self.assertEqual(set(hit['calculation']['counts'].values()),{1})
        self.assertEqual(hit['severity'],'info')
        short=inspect(['a'],[['1.1']])[1]
        self.assertEqual(next(c for c in short if c['rule_id']=='DET-04c')['status'],'insufficient')

    def test_time_subrules_positive_counterexample_and_insufficient(self):
        headers=['对象','时间','数值'];x=[1,4,2,6,9,3];y=[8,2,6,1,5,9]
        def tracks(right):return [[obj,str(i),str(v)] for obj,values in [('A',x),('B',right)] for i,v in enumerate(values)]
        for rule,right in [('DET-08a',x),('DET-08b',[v+5 for v in x]),('DET-08c',x[:5]+[77])]:
            with self.subTest(rule=rule):
                self.assertIn(rule,self.ids(inspect(headers,tracks(right),'time')))
                self.assertNotIn(rule,self.ids(inspect(headers,tracks(y),'time')))
                missing=inspect(headers,tracks(right)[:2],'time')[1]
                self.assertEqual(next(c for c in missing if c['rule_id']==rule)['status'],'insufficient')

    def test_five_point_sequence_and_nonsequence(self):
        headers=['顺序','数值']
        self.assertIn('DET-09b',self.ids(inspect(headers,[[str(i),str(2**i)] for i in range(5)],'sequence')))
        self.assertNotIn('DET-09b',self.ids(inspect(headers,[[str(i),str(v)] for i,v in enumerate([1,4,2,8,3])],'sequence')))

    def test_duplicates_bad_proportions_and_excel_reported_precision(self):
        found,coverage=inspect(['a','a'],[['1','2']]*5)
        self.assertFalse(found);self.assertTrue(all(c['status']=='insufficient' for c in coverage))
        found,coverage=inspect(['分子','分母','比例'],[['-1','3','0.8']],'denominator')
        self.assertFalse(found);self.assertEqual(coverage[0]['skipped_rows'],1)
        rows=[{'row_idx':2,'values':[1,3,.349],'formats':['0','0','0.0']}]
        # Reported .3 represents [.25,.35]; 1/3 is consistent even though stored .349 differs.
        found,coverage=patterns.check_table('x.xlsx','s',['分子','分母','比例'],rows,'denominator',number)
        self.assertFalse(found);self.assertEqual(coverage[0]['status'],'checked')

    def test_resource_limit_and_repeated_starts_are_disclosed(self):
        found,coverage=inspect(['a','b'],[[str(i%5),str(i%5)] for i in range(1001)])
        self.assertTrue(any('前1000行' in ' '.join(c['notes']) for c in coverage))
        self.assertTrue(any('3个起点' in ' '.join(c['notes']) for c in coverage))
        self.assertTrue(all(c['status']!='checked' for c in coverage))


if __name__=='__main__':
    unittest.main()
