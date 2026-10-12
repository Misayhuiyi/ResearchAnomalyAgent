"""Fixed arithmetic and method-specific counterexamples for DET-05/06."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import statistical_checks as checks


def run_rule(key, headers, values):
    return checks.table_check('case.csv', 'case', headers,
                              [{'row_idx': 7, 'values': values}], [key])


class ExtendedStatisticsTests(unittest.TestCase):
    def assert_case(self, key, headers, values, status, count):
        findings, coverage = run_rule(key, headers, values)
        self.assertEqual(status, coverage[0]['status'], coverage)
        self.assertEqual(count, len(findings), findings)
        if findings:
            self.assertEqual(7, findings[0]['evidence']['rows'][0]['row_idx'])
        return findings, coverage

    def test_group_total_hit_counterexample_and_insufficient(self):
        headers = ['总人数', '分组1人数', '分组2人数', '分组3人数']
        for total, expected in [('100', 1), ('90', 0)]:
            self.assert_case('group_total', headers, [total, '20', '30', '40'], 'checked', expected)
        self.assert_case('group_total', headers, ['90', '20', '', '40'], 'insufficient', 0)
        self.assert_case('group_total', ['总人数','分组1人数'], ['90','90'], 'insufficient', 0)

    def test_flow_hit_counterexample_and_insufficient(self):
        headers = ['初始人数', '排除人数', '缺失人数', '分析人数']
        self.assert_case('participant_flow', headers, ['100','10','5','80'], 'checked', 1)
        self.assert_case('participant_flow', headers, ['100','10','5','85'], 'checked', 0)
        self.assert_case('participant_flow', headers, ['100','10','-5','95'], 'insufficient', 0)

    def test_normal_ci_hit_counterexample_and_missing_method(self):
        headers = ['n','mean','sd','ci_low','ci_high','confidence','ci_method']
        self.assert_case('mean_ci', headers, ['100','10.00','5.00','9.02','10.98','95','normal'], 'checked', 0)
        self.assert_case('mean_ci', headers, ['100','10.00','5.00','9.02','12.00','95','normal'], 'checked', 1)
        self.assert_case('mean_ci', headers, ['100','10.00','5.00','9.02','10.98','95','bootstrap'], 'insufficient', 0)

    def test_t_ci_hit_counterexample_and_insufficient(self):
        headers = ['n','mean','sd','ci_low','ci_high','confidence','ci_method']
        # t(0.975,9)=2.262157..., margin=2.262157*2/sqrt(10)=1.430714.
        for upper, expected in [('11.43', 0), ('12.43', 1)]:
            self.assert_case('mean_ci', headers, ['10','10.00','2.00','8.57',upper,'95','t'], 'checked', expected)
        self.assert_case('mean_ci', headers, ['1','10.00','2.00','8.19','11.81','95','t'], 'insufficient', 0)

    def test_negative_mean_and_rounded_sd_ci_are_not_clipped_to_zero(self):
        headers = ['n','mean','sd','ci_low','ci_high','confidence','ci_method']
        self.assert_case('mean_ci', headers, ['100','-10.00','5.00','-10.98','-9.02','95','normal'], 'checked', 0)
        self.assert_case('mean_ci', headers, ['100','10','5','9.00','11.00','95','normal'], 'checked', 0)

    def test_p_methods_each_have_hit_counterexample_and_missing_condition(self):
        headers = ['test','statistic','p','tail','df','df2']
        cases = [('z','1.960','0.0500','two-sided','',''),
                 ('t','2.228','0.0500','two-sided','10',''),
                 ('chi2','3.841','0.0500','right','1',''),
                 ('f','4.965','0.0500','right','1','10')]
        for row in cases:
            with self.subTest(method=row[0]):
                self.assert_case('reported_p', headers, list(row), 'checked', 0)
                incorrect=list(row); incorrect[2]='0.5000'
                self.assert_case('reported_p', headers, incorrect, 'checked', 1)
                missing=list(row); missing[3]=''
                self.assert_case('reported_p', headers, missing, 'insufficient', 0)

    def test_p_direction_rounding_and_threshold_not_treated_as_exact(self):
        headers = ['test','statistic','p','tail']
        self.assert_case('reported_p', headers, ['z','-1.645','0.050','left'], 'checked', 0)
        self.assert_case('reported_p', headers, ['z','-1.645','0.050','right'], 'checked', 1)
        self.assert_case('reported_p', headers, ['z','4.000','<0.001','two-sided'], 'checked', 0)
        self.assert_case('reported_p', headers, ['z','1.000','<0.001','two-sided'], 'checked', 1)
        self.assert_case('reported_p', headers, ['z','0.00','1.000','two-sided'], 'checked', 0)

    def test_p_missing_df_and_noncentral_or_adjusted_method_not_guessed(self):
        headers = ['test','statistic','p','tail']
        for method in ['t','f','chi2','welch-adjusted','noncentral-t']:
            self.assert_case('reported_p', headers, [method,'2','0.05','two-sided'], 'insufficient', 0)

    def test_grim_integral_mean_hit_counterexample_and_missing(self):
        headers=['n','mean']
        self.assert_case('integer_mean', headers, ['3','1.50'], 'checked', 1)
        self.assert_case('integer_mean', headers, ['3','1.33'], 'checked', 0)
        self.assert_case('integer_mean', headers, ['0','1.33'], 'insufficient', 0)
        self.assert_case('integer_mean', headers, ['3','-1.33'], 'checked', 0)

    def test_new_rules_are_explicit_not_enabled_by_default(self):
        for key in ['group_total','participant_flow','mean_ci','reported_p','integer_mean']:
            self.assertEqual([key], checks.selections([key]))
        self.assertEqual([], checks.selections(None))

    def test_excel_p_display_precision_and_numeric_zero(self):
        headers=['test','statistic','p','tail']
        rows=[{'row_idx':2,'values':['z',4,0,'two-sided'],'formats':['General','0.000','0.000','General']}]
        findings, coverage=checks.table_check('x.xlsx','x',headers,rows,['reported_p'])
        self.assertEqual([],findings)
        self.assertEqual('checked',coverage[0]['status'])
        rows[0]['formats'][2]='General'
        _, coverage=checks.table_check('x.xlsx','x',headers,rows,['reported_p'])
        self.assertEqual('insufficient',coverage[0]['status'])


if __name__ == '__main__':
    unittest.main()
