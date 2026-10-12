"""Corpus helpers and frozen truth. Local licensed materials are optional in CI."""
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from openpyxl import Workbook
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import check_corpus_evidence as evidence


class CorpusHelperTests(unittest.TestCase):
    def test_numeric_counter_excludes_text_empty_and_boolean(self):
        for v in (None,'',True,False,'NA','nan','inf'):self.assertFalse(evidence.numeric(v))
        for v in (0,-1,1.25,'-25.14591','1e-5'):self.assertTrue(evidence.numeric(v))

    def test_independent_value_comparison_preserves_precision(self):
        self.assertTrue(evidence.same('-25.14591',-25.14591))
        self.assertFalse(evidence.same('-25.14591',-25.1459))
        self.assertTrue(evidence.same('',None));self.assertFalse(evidence.same('NA',None))

    def test_csv_and_tsv_reader_keeps_physical_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            for extension,delimiter in (('.csv',','),('.tsv','\t')):
                path=Path(directory)/('source'+extension)
                path.write_text('label'+delimiter+'value\nA'+delimiter+'0.451\nB'+delimiter+'0.469\n',encoding='utf-8')
                rows=evidence.table(path,path.stem)
                self.assertEqual(rows[1],['A','0.451']);self.assertEqual(rows[2],['B','0.469'])

    def test_excel_reader_does_not_shift_title_and_header_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.xlsx';book=Workbook();sheet=book.active;sheet.title='Experiment 2'
            sheet.append(['标题',None]);sheet.append(['Subject','VO2maxVB']);sheet.append([4,65.95549826312603]);book.save(path);book.close()
            rows=evidence.table(path,'Experiment 2')
            self.assertEqual(rows[2][0],4);self.assertAlmostEqual(rows[2][1],65.95549826312603,12)

    def corpus(self):
        folder=ROOT/'test-corpus'
        if not (folder/'manifest.json').exists():self.skipTest('Local licensed public corpus not downloaded in CI')
        return folder,json.loads((folder/'manifest.json').read_text(encoding='utf-8'))

    def test_all_frozen_corpus_files_match_manifest(self):
        folder,manifest=self.corpus()
        self.assertEqual(len(manifest['papers']),5);self.assertEqual(len(manifest['cases']),12)
        for name,expected in manifest['hashes'].items():
            self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),expected,name)

    def test_known_iris_differences_are_source_not_injected_labels(self):
        folder,manifest=self.corpus()
        case=next(c for c in manifest['cases'] if c['id'].startswith('E01'))
        raw=evidence.table(folder/'originals/Fisher1936/iris_uci.csv','iris_uci')
        fixed=evidence.table(folder/'originals/Fisher1936/iris_corrected.csv','iris_corrected')
        self.assertEqual(len(case['expected']['known_cells']),3)
        for item in case['expected']['known_cells']:
            self.assertEqual(raw[item['row']-1][item['column']-1],item['original'])
            self.assertEqual(fixed[item['row']-1][item['column']-1],item['corrected'])

    def test_positive_control_values_independently_satisfy_formulas(self):
        folder,_=self.corpus()
        rows=evidence.table(folder/'cases/C01_人工固定平移/人工固定平移.csv','人工固定平移')[1:]
        self.assertEqual(len(rows),35)
        for a,b in rows:self.assertAlmostEqual(float(b)-float(a),.3,10)
        rows=evidence.table(folder/'cases/C02_人工固定比例/人工固定比例.xlsx','测试数据')[1:]
        self.assertEqual(len(rows),35)
        for a,b in rows:self.assertAlmostEqual(b/a,2,10)
        rows=evidence.table(folder/'cases/C03_人工线性与重复/人工线性与重复.tsv','人工线性与重复')[1:]
        self.assertEqual(len(rows),35)
        for a,b,c in rows:
            self.assertAlmostEqual(float(b),float(a)*1.5+.7,10);self.assertEqual(a,c)


if __name__=='__main__':unittest.main()
