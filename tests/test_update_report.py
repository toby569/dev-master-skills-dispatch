"""Verify optional AI summaries without contacting a provider."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from internal.update_report import UpdateReport


class UpdateReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.report = UpdateReport(Path(temp.name))
        self.report.record("first", "一项变动", changed=True, patch="first patch")
        self.report.record("second", "另一项变动", changed=True, patch="second patch")
        self.output = io.StringIO()

    def test_no_cli_prints_the_saved_report_path(self):
        with patch("shutil.which", return_value=None), patch("subprocess.run") as run, redirect_stdout(self.output):
            self.report.finish(no_ai=False)
        run.assert_not_called()
        self.assertIn(str(self.report.path), self.output.getvalue())
        self.assertIn("AI 摘要不可用", self.output.getvalue())
        self.assertIn("first patch", self.report.path.read_text(encoding="utf-8"))

    def test_no_ai_skips_provider_detection(self):
        with patch("shutil.which") as which, redirect_stdout(self.output):
            self.report.finish(no_ai=True)
        which.assert_not_called()
        self.assertIn(str(self.report.path), self.output.getvalue())

    def test_an_available_cli_summarizes_all_saved_changes(self):
        def summarize(cmd, *, input, **options):
            self.assertIn("first patch", input)
            self.assertIn("second patch", input)
            self.assertIn("second patch", self.report.path.read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(cmd, 0, stdout="汇总结果")

        for provider in ("codex", "claude"):
            with self.subTest(provider=provider), patch("shutil.which", side_effect=lambda name: name if name == provider else None), \
                    patch("subprocess.run", side_effect=summarize) as run, redirect_stdout(self.output):
                self.report.finish(no_ai=False)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][0], provider)
                self.assertIn(f"[AI 摘要 · {provider}]\n汇总结果", self.report.path.read_text(encoding="utf-8"))
                self.assertIn("汇总结果", self.output.getvalue())

    def test_failed_and_timed_out_clis_leave_details_available(self):
        results = [subprocess.CompletedProcess([], 1, stdout=""), subprocess.TimeoutExpired("claude", 180)]
        with patch("shutil.which", side_effect=lambda name: name), patch("subprocess.run", side_effect=results) as run, \
                redirect_stdout(self.output):
            self.report.finish(no_ai=False)
        self.assertEqual([call.args[0][0] for call in run.call_args_list], ["codex", "claude"])
        self.assertIn(f"AI 摘要不可用，请查看更新明细：{self.report.path}", self.output.getvalue())
        self.assertIn("second patch", self.report.path.read_text(encoding="utf-8"))
