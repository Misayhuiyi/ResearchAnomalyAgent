import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


class PaperAuditMVPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        sample = (ROOT / "samples" / "fixed_shift_demo.csv").read_bytes()
        cls.result = app.scan_bytes(
            "fixed_shift_demo.csv",
            sample,
            "review",
            runtime_dir=Path(cls.temp_dir.name),
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_engine_version_is_available(self):
        self.assertIn("paperconan", app.engine_version().lower())
        self.assertNotIn("unavailable", app.engine_version().lower())

    def test_sample_detects_35_row_fixed_offset(self):
        matches = [item for item in self.result["findings"] if item["kind"] == "constant_offset"]
        self.assertTrue(matches, "合成样例应命中固定平移")
        self.assertEqual(35, matches[0]["n"])
        self.assertIn("0.3", matches[0]["rule"])
        self.assertEqual(["control", "treated"], matches[0]["columns"])
        self.assertEqual("固定差值", matches[0]["title_cn"])
        self.assertIn("均高 0.3", matches[0]["summary_cn"])
        self.assertIn("35 行", matches[0]["summary_cn"])

    def test_sample_detects_fixed_ratio(self):
        matches = [item for item in self.result["findings"] if item["kind"] == "constant_ratio"]
        self.assertTrue(matches, "合成样例应命中固定比例")
        self.assertEqual(35, matches[0]["n"])
        self.assertEqual(2.0, matches[0]["raw"]["ratio"])
        self.assertEqual("固定倍数", matches[0]["title_cn"])
        self.assertIn("2 倍", matches[0]["summary_cn"])

    def test_scan_reports_complete_coverage_and_evidence(self):
        self.assertEqual("complete", self.result["scan_status"])
        self.assertEqual(1, self.result["summary"]["files"])
        self.assertEqual(1, self.result["summary"]["sheets"])
        fixed = next(item for item in self.result["findings"] if item["kind"] == "constant_offset")
        self.assertGreaterEqual(len(fixed["evidence"]["rows"]), 8)
        self.assertIn("control", fixed["evidence"]["headers"])
        self.assertNotEqual(fixed["evidence"]["headers"], fixed["evidence"]["rows"][0]["values"])
        self.assertTrue(self.result["artifacts"]["user_report"].endswith("/report.html"))

    def test_rounded_values_include_exact_cell_locations(self):
        finding = next(
            item
            for item in self.result["findings"]
            if item["kind"] == "identical_after_rounding" and item["raw"]["rounded_to"] == 0.5
        )
        cells = {
            (cell["row_idx"], cell["column"], cell["original"], cell["displayed"])
            for cell in finding["evidence"]["focus_cells"]
        }
        self.assertEqual(
            {
                (2, "treated", 0.45, 0.5),
                (12, "control", 0.47, 0.5),
                (27, "treated", 0.53, 0.5),
                (27, "scaled", 0.46, 0.5),
            },
            cells,
        )
        self.assertEqual(["treated", "control", "scaled"], finding["columns"])

    def test_user_report_is_readable_and_hides_internal_terms(self):
        report_path = Path(self.temp_dir.name) / self.result["scan_id"] / "report.html"
        report = report_path.read_text(encoding="utf-8")
        self.assertIn("科研数据筛查报告", report)
        self.assertIn("fixed_shift_demo.csv", report)
        self.assertIn("均高 0.3", report)
        self.assertIn("完整原始数值", report)
        self.assertIn(">27<", report)
        for value in ("0.45", "0.47", "0.53", "0.46"):
            self.assertIn(value, report)
        self.assertNotIn("PaperConan", report)
        self.assertNotRegex(report, r"FD-\d+")

    def test_result_is_json_serializable(self):
        encoded = json.dumps(self.result, ensure_ascii=False)
        self.assertIn("需要人工核对的数据规律", encoded)
        self.assertIn("scan_id", encoded)

    def test_rejects_unsupported_extension(self):
        with self.assertRaisesRegex(app.DemoError, "不支持"):
            app.validate_upload("payload.exe", b"hello", "review")

    def test_rejects_path_traversal_filename(self):
        with self.assertRaisesRegex(app.DemoError, "文件名不合法"):
            app.validate_upload("../sample.csv", b"a,b\n1,2\n", "review")

    def test_background_job_reaches_succeeded_with_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = (ROOT / "samples" / "fixed_shift_demo.csv").read_bytes()
            job = app.start_scan_job(
                "fixed_shift_demo.csv",
                sample,
                "review",
                runtime_dir=Path(temp_dir),
            )
            self.assertEqual("queued", job["status"])
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                current = app.get_scan_job(job["job_id"])
                if current["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.05)
            else:
                self.fail("后台扫描任务未在 30 秒内结束")
            self.assertEqual("succeeded", current["status"], current.get("error"))
            self.assertEqual("complete", current["result"]["scan_status"])
            self.assertEqual(job["job_id"], current["job_id"])
            self.assertTrue(current["started_at"])
            self.assertTrue(current["finished_at"])

    def test_background_job_rejects_invalid_input_before_queueing(self):
        with self.assertRaisesRegex(app.DemoError, "不支持"):
            app.start_scan_job("payload.exe", b"hello", "review")

    def test_unknown_background_job_returns_clear_error(self):
        with self.assertRaisesRegex(app.DemoError, "不存在"):
            app.get_scan_job("0" * 12)

    def test_frontend_uses_background_job_contract(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/jobs'", html)
        self.assertIn("waitForJob", html)
        self.assertIn("/api/jobs/${jobId}", html)
        self.assertEqual(3, html.count('data-view="'))
        self.assertIn("currentResult.artifacts?.user_report", html)
        self.assertNotIn("为什么需要查看", html)
        self.assertNotIn("常见正常原因", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
