"""Regression tests for delivery gating in main.py.

Offline: all LLM/git/verify stages are mocked. No push or PR can happen.
Run from repo root:  PYTHONPATH=. .venv/bin/python tests/test_delivery.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import main
from harness.implement import ImplementationResult
from harness.pr import CompletionResult
from harness.verify import VerifyResult


def finished_result(files=("main.go",)):
    return ImplementationResult(
        finished=True, stopped_reason="finished",
        files_written=list(files), turns_used=2, final_text="ok",
    )


def unfinished_result():
    return ImplementationResult(
        finished=False, stopped_reason="max_turns",
        files_written=["main.go"], turns_used=10, final_text="",
    )


VERIFY_PASS = VerifyResult(run=True, passed=True, summary="ok")
VERIFY_FAIL = VerifyResult(run=True, passed=False, summary="go test: FAIL")

BLOCKER = {"rule": "R1", "severity": "blocker", "reason": "broken"}


def run_main():
    main.main()


class DeliveryGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.addCleanup(os.chdir, self._old_cwd)

        commit = SimpleNamespace(sha="abc123def", committed=True)
        patchers = [
            mock.patch("main.OpenAI"),
            mock.patch("main.git.ensure_repo"),
            mock.patch("main.git.create_branch", return_value="harny/test"),
            mock.patch("main.git.commit_all", return_value=commit),
            mock.patch("main.git.diff_against", return_value="diff --git a/main.go"),
            mock.patch("main.git.changed_files", return_value=["main.go"]),
            mock.patch("main.get_plans", return_value=["plan1", "plan2"]),
            mock.patch("main.selector", return_value=("plan1", "rationale", 0)),
            mock.patch("main.run_revision", return_value="plan1"),
            mock.patch("main.load_skills", return_value=[]),
            mock.patch("main.log_step"),
            mock.patch("main.sandbox_root", return_value=Path(self._tmp.name) / "sandbox"),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        self.push_branch = mock.patch("main.git.push_branch").start()
        self.push_branch.return_value = (True, "pushed")
        self.addCleanup(self.push_branch.stop)
        self.open_pr = mock.patch("main.git.open_pr").start()
        self.open_pr.return_value = (1, "https://example/pr/1")
        self.addCleanup(self.open_pr.stop)
        self.wait = mock.patch("main.wait_for_merge_ready").start()
        self.wait.return_value = (None, CompletionResult(True, "MERGE_READY"))
        self.addCleanup(self.wait.stop)

    def _run(self, implement_side_effect, verify_result, findings):
        with mock.patch("main.implement", side_effect=implement_side_effect), \
                mock.patch("main.verify", return_value=verify_result), \
                mock.patch("main.review", return_value=findings):
            run_main()

    def test_unfinished_initial_implementation_never_delivers(self):
        with self.assertRaises(RuntimeError):
            self._run([unfinished_result()], VERIFY_PASS, [])
        self.push_branch.assert_not_called()
        self.open_pr.assert_not_called()

    def test_unfinished_fix_implementation_never_delivers(self):
        with self.assertRaises(RuntimeError):
            self._run(
                [finished_result(), unfinished_result()],
                VERIFY_FAIL, [],
            )
        self.push_branch.assert_not_called()
        self.open_pr.assert_not_called()

    def test_failed_final_verification_never_delivers(self):
        with self.assertRaises(RuntimeError):
            self._run(
                [finished_result(), finished_result()],
                VERIFY_FAIL, [],
            )
        self.push_branch.assert_not_called()
        self.open_pr.assert_not_called()

    def test_remaining_blocker_findings_never_deliver(self):
        with self.assertRaises(RuntimeError):
            self._run(
                [finished_result(), finished_result()],
                VERIFY_PASS, [BLOCKER],
            )
        self.push_branch.assert_not_called()
        self.open_pr.assert_not_called()

    def test_successful_run_delivers(self):
        self._run([finished_result()], VERIFY_PASS, [])
        self.push_branch.assert_called_once()
        self.open_pr.assert_called_once()
        self.wait.assert_called_once()

    def test_no_pr_number_skips_polling(self):
        self.open_pr.return_value = (None, "")
        self._run([finished_result()], VERIFY_PASS, [])
        self.push_branch.assert_called_once()
        self.wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
