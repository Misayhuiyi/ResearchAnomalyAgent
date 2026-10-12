"""Known arithmetic, counterexamples and unavailable conditions, not clinical judgements."""
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
import statistical_checks as checks


SAMPLE = ("分组,人数,总人数,百分比,样本量,标准差,标准误\n"
          "A,13,40,32.5%,25,10.00,2.00\n"
          "B,13,40,25.0%,25,10.00,3.00\n"
          "C,1,3,33.3%,10,1.20,0.38\n"
          "D,4,0,10.0%,1,1.00,1.00\n").encode("utf-8")


class StatisticsMathTests(unittest.TestCase):
    def percent(self, count, total, percent):
        return checks.calculate("count_percent", {"count": checks.number(count), "total": checks.number(total), "percent": checks.number(percent, percent=True)})

    def sd_se(self, n, sd, se):
        return checks.calculate("sd_se", {"n": checks.number(n), "sd": checks.number(sd), "se": checks.number(se)})

    def test_percent_exact_and_rounded_consistency(self):
        for values in [("13", "40", "32.5%"), ("1", "3", "33.3%"), ("0", "20", "0%"), ("20", "20", "100%")]:
            self.assertFalse(self.percent(*values)["mismatch"])

    def test_percent_concrete_mismatch_has_formula(self):
        result = self.percent("13", "40", "25.0%")
        self.assertTrue(result["mismatch"])
        self.assertEqual(Decimal("32.5"), Decimal(result["expected"]))
        self.assertIn("25.0%", result["summary"])

    def test_percent_halfway_is_not_false_positive(self):
        self.assertFalse(self.percent("1", "8", "12%")["mismatch"])
        self.assertFalse(self.percent("1", "8", "13%")["mismatch"])

    def test_invalid_count_denominator_and_missing_are_unchecked(self):
        for values in [("1", "0", "20%"), ("-1", "3", "20%"), ("4", "3", "20%"), ("1.2", "3", "40%"), ("1", "3", "")]:
            with self.subTest(values=values), self.assertRaises(checks.CannotCheck):
                self.percent(*values)

    def test_sd_se_exact_and_rounding_both_inputs(self):
        self.assertFalse(self.sd_se("25", "10.00", "2.00")["mismatch"])
        self.assertFalse(self.sd_se("10", "1.20", "0.38")["mismatch"])
        # SD is rounded to a whole unit: not enough precision to flag this SE.
        self.assertFalse(self.sd_se("4", "1", "0.74")["mismatch"])

    def test_sd_se_mismatch_and_nonapplicable_inputs(self):
        result = self.sd_se("25", "10.00", "3.00")
        self.assertTrue(result["mismatch"])
        self.assertEqual(Decimal(2), Decimal(result["expected"]))
        for values in [("1", "1", "1"), ("25", "-1", "1"), ("25", "1", "-1"), ("2.5", "1", "1")]:
            with self.assertRaises(checks.CannotCheck):
                self.sd_se(*values)

    def test_number_rejects_nonfinite_complex_and_extreme_values(self):
        for value in [True, None, "NaN", "inf", "<0.05", "1 ± 2", "1e99", "0.000000000000001", "1,000"]:
            with self.subTest(value=value), self.assertRaises(checks.CannotCheck):
                checks.number(value)

    def test_excel_percent_format_and_unknown_precision(self):
        cell = checks.number(0.325, "0.0%", percent=True)
        self.assertEqual(Decimal("32.5"), cell.value)
        self.assertIn("0.325", cell.original)
        self.assertIn("32.5%", cell.original)
        with self.assertRaises(checks.CannotCheck):
            checks.interval(checks.number(0.38, "General"))
        with self.assertRaises(checks.CannotCheck):
            checks.number(0.3, "0.0%")

    def test_aliases_are_explicit_and_ambiguous_columns_rejected(self):
        self.assertEqual({"count": 0, "total": 1, "percent": 2}, checks.mapping(["人数", "总人数", "百分比（%）"], "count_percent"))
        for headers in [["count", "total", "rate"], ["count", "total", "percentage", "percent"]]:
            with self.assertRaises(checks.CannotCheck):
                checks.mapping(headers, "count_percent")

    def test_explicit_selection_is_required_and_validated(self):
        self.assertEqual([], checks.selections(None))
        for value in [True, "sd_se", ["sd_se", "sd_se"], ["p_value"], [{}]]:
            with self.assertRaises(checks.CannotCheck):
                checks.selections(value)


class StatisticsPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "statistics.csv"
        self.csv.write_bytes(SAMPLE)

    def test_csv_finds_exact_originals_and_distinguishes_skips(self):
        findings, coverage = checks.check_file(self.csv, {"statistics"}, ["count_percent", "sd_se"])
        self.assertEqual(2, len(findings))
        self.assertEqual({3}, {item["evidence"]["rows"][0]["row_idx"] for item in findings})
        self.assertEqual(["13", "40", "25.0%"], findings[0]["evidence"]["rows"][0]["values"])
        self.assertEqual(["25", "10.00", "3.00"], findings[1]["evidence"]["rows"][0]["values"])
        for item in coverage:
            self.assertEqual("partial", item["status"])
            self.assertEqual(3, item["checked_rows"])
            self.assertEqual(1, item["skipped_rows"])

    def test_unselected_or_unread_file_is_not_reloaded(self):
        with patch.object(Path, "open", side_effect=AssertionError("Must not read")):
            self.assertEqual(([], []), checks.check_file(self.csv, {"statistics"}, []))
            findings, coverage = checks.check_file(self.csv, set(), ["sd_se"])
            self.assertEqual([], findings)
            self.assertEqual("insufficient", coverage[0]["status"])

    def test_unsupported_and_missing_header_are_not_zero_issue_success(self):
        findings, coverage = checks.check_file(self.root / "paper.pdf", {"table"}, ["sd_se"])
        self.assertEqual("unsupported", coverage[0]["status"])
        findings, coverage = checks.table_check("x.csv", "x", ["group", "value"], [{"row_idx": 2, "values": ["a", "2"]}], ["sd_se"])
        self.assertEqual("insufficient", coverage[0]["status"])
        self.assertEqual(0, coverage[0]["checked_rows"])

    def test_limits_disclose_partial_and_do_not_hide_total_hits(self):
        with patch.object(checks, "MAX_ROWS", 2):
            _, coverage = checks.check_file(self.csv, {"statistics"}, ["sd_se"])
            self.assertEqual("partial", coverage[0]["status"])
            self.assertIn("容量", "".join(coverage[0]["notes"]))
        rows = [{"row_idx": x, "values": ["25", "10.00", "3.00"]} for x in range(2, 6)]
        with patch.object(checks, "MAX_FINDINGS", 1):
            findings, coverage = checks.table_check("x.csv", "x", ["n", "sd", "se"], rows, ["sd_se"])
        self.assertEqual(1, len(findings))
        self.assertEqual(4, coverage[0]["findings_total"])
        self.assertEqual(1, coverage[0]["findings_shown"])

    def test_workbook_reader_preserves_formats_and_excludes_failed_sheet(self):
        def cell(value, fmt="General"):
            return SimpleNamespace(value=value, number_format=fmt)
        good = SimpleNamespace(title="Good", max_column=3, max_row=2,
            iter_rows=lambda: iter([[cell("count"), cell("total"), cell("percent")],
                                    [cell(13, "0"), cell(40, "0"), cell(0.25, "0.0%")]]))
        bad = MagicMock(title="Bad")
        workbook = MagicMock(worksheets=[good, bad])
        with patch.object(checks, "load_workbook", return_value=workbook):
            findings, coverage = checks.check_file(self.root / "x.xlsx", {"Good"}, ["count_percent"])
        self.assertEqual(1, len(findings))
        self.assertIn("0.25", findings[0]["evidence"]["rows"][0]["values"][2])
        bad.iter_rows.assert_not_called()
        workbook.close.assert_called_once()

    def test_fractional_excel_count_cannot_be_rounded_into_valid_integer(self):
        rows = [{"row_idx": 2, "values": [1.5, 4, 0.5], "formats": ["0", "0", "0%"]}]
        findings, coverage = checks.table_check("x.xlsx", "x", ["count", "total", "percent"], rows, ["count_percent"])
        self.assertFalse(findings)
        self.assertEqual(0, coverage[0]["checked_rows"])

    def test_real_scan_merges_results_and_persists_assumptions(self):
        result = app.scan_files([("statistics.csv", SAMPLE)], runtime_dir=self.root / "runs", extra_checks=["count_percent", "sd_se"])
        supplement = [finding for finding in result["findings"] if finding.get("rule_id")]
        self.assertEqual({"DET-05a", "DET-06a"}, {finding["rule_id"] for finding in supplement})
        self.assertEqual(len(result["findings"]), result["summary"]["findings"])
        self.assertEqual(len(result["findings"]), len({item["id"] for item in result["findings"]}))
        self.assertEqual("partial", result["scan_status"])
        self.assertIn("统计核对", "".join(result["coverage_notes_cn"]))
        report = (self.root / "runs" / result["scan_id"] / "report.html").read_text(encoding="utf-8")
        self.assertIn("统计核对范围", report)
        self.assertIn("25.0%", report)
        self.assertIn("用户确认的口径", report)
        saved = json.loads((self.root / "runs" / result["scan_id"] / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(["count_percent", "sd_se"], saved["extra_checks"])

    def test_general_format_is_unchecked_and_capacity_preserves_sheet_name(self):
        rows = [{"row_idx": 2, "values": [25, 10, 3], "formats": ["0", "General", "General"]}]
        findings, coverage = checks.table_check("x.xlsx", "x", ["n", "sd", "se"], rows, ["sd_se"])
        self.assertEqual([], findings)
        self.assertEqual("insufficient", coverage[0]["status"])
        self.assertIn("小数位", "".join(coverage[0]["notes"]))
        sheet = MagicMock(title="Large", max_column=checks.MAX_COLUMNS + 1, max_row=2)
        book = MagicMock(worksheets=[sheet])
        with patch.object(checks, "load_workbook", return_value=book):
            _, coverage = checks.check_file(self.root / "x.xlsx", {"Large"}, ["sd_se"])
        self.assertEqual("Large", coverage[0]["sheet"])
        sheet.iter_rows.assert_not_called()

    def test_missing_selected_columns_downgrades_scan_and_report(self):
        result = app.scan_files([("other.csv", b"group,value\nA,1\nB,2\nC,3\n")],
                                runtime_dir=self.root / "runs", extra_checks=["sd_se"])
        self.assertEqual("partial", result["scan_status"])
        self.assertEqual("insufficient", result["statistical_coverage"][0]["status"])
        report = (self.root / "runs" / result["scan_id"] / "report.html").read_text(encoding="utf-8")
        self.assertIn("未完成检查", report)
        # Legacy artifact import must not discard the supplementary-rule status.
        app.restore_scan_jobs(self.root / "runs")
        saved = app.job_store.list_jobs(self.root / "runs")
        self.assertEqual("partial", saved[0]["scan_status"])


if __name__ == "__main__":
    unittest.main()
