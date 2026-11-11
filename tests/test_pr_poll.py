"""Offline tests for bounded polling in harness.pr.wait_for_merge_ready.

poll_pr_state, sleep, and the monotonic clock are mocked. No gh calls.
Run from repo root:  .venv/bin/python tests/test_pr_poll.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from unittest import mock

from harness.pr import PRComment, PRState, wait_for_merge_ready


def make_pr(**over):
    base = dict(
        number=4,
        state="OPEN",
        is_draft=False,
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        review_decision="",
        head_ref_oid="abc",
    )
    base.update(over)
    return PRState(**base)


MERGE_READY_PR = make_pr()
MERGED_PR = make_pr(state="MERGED")
CLOSED_PR = make_pr(state="CLOSED")
DRAFT_PR = make_pr(is_draft=True, merge_state_status="DRAFT")
CONFLICTING_PR = make_pr(mergeable="CONFLICTING", merge_state_status="DIRTY")
BEHIND_PR = make_pr(merge_state_status="BEHIND")
CI_FAILED_PR = make_pr(
    merge_state_status="UNSTABLE",
    status_check_rollup=[{"name": "ci", "conclusion": "FAILURE"}],
)
CI_PENDING_PR = make_pr(status_check_rollup=[{"name": "ci", "status": "QUEUED"}])
CHANGES_REQUESTED_PR = make_pr(review_decision="CHANGES_REQUESTED")
REVIEW_REQUIRED_PR = make_pr(
    mergeable="", merge_state_status="", review_decision="REVIEW_REQUIRED"
)
BLOCKED_PR = make_pr(merge_state_status="BLOCKED")
UNKNOWN_PR = make_pr(mergeable="", merge_state_status="", review_decision="")
UNRESOLVED_THREADS_PR = make_pr(unresolved_comments=[
    PRComment(body="fix this", author="rev", path="main.go", line=1, url=""),
])


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class WaitForMergeReadyTests(unittest.TestCase):
    def _run(self, side_effect, timeout_seconds=120.0, interval_seconds=60.0):
        clock = FakeClock()
        with mock.patch("harness.pr.poll_pr_state", side_effect=side_effect) as poll, \
                mock.patch("harness.pr.time", clock):
            state, completion = wait_for_merge_ready(
                Path("/nonexistent"), 4,
                timeout_seconds=timeout_seconds, interval_seconds=interval_seconds,
            )
        return state, completion, poll, clock

    def test_immediate_merge_ready(self):
        state, completion, poll, clock = self._run([MERGE_READY_PR])
        self.assertTrue(completion.complete)
        self.assertEqual(completion.state, "MERGE_READY")
        self.assertIs(state, MERGE_READY_PR)
        self.assertEqual(poll.call_count, 1)
        self.assertEqual(clock.sleeps, [])

    def test_review_required_then_merge_ready(self):
        # Approval-only wait: no failures, no feedback — must keep polling.
        state, completion, poll, clock = self._run([REVIEW_REQUIRED_PR, MERGE_READY_PR])
        self.assertEqual(completion.state, "MERGE_READY")
        self.assertEqual(poll.call_count, 2)
        self.assertEqual(clock.sleeps, [60.0])

    def test_ci_pending_then_merge_ready(self):
        state, completion, poll, clock = self._run([CI_PENDING_PR, MERGE_READY_PR])
        self.assertEqual(completion.state, "MERGE_READY")
        self.assertEqual(poll.call_count, 2)
        self.assertEqual(clock.sleeps, [60.0])

    def test_waitable_states_keep_polling(self):
        for waitable in (BLOCKED_PR, UNKNOWN_PR):
            with self.subTest(state=waitable.review_decision or "UNKNOWN"):
                state, completion, poll, clock = self._run([waitable, MERGE_READY_PR])
                self.assertEqual(completion.state, "MERGE_READY")
                self.assertEqual(poll.call_count, 2)
                self.assertEqual(clock.sleeps, [60.0])

    def test_actionable_states_stop_immediately(self):
        cases = {
            "CONFLICTING": CONFLICTING_PR,
            "BEHIND": BEHIND_PR,
            "CI_FAILED": CI_FAILED_PR,
            "CHANGES_REQUESTED": CHANGES_REQUESTED_PR,
            "UNRESOLVED_THREADS": UNRESOLVED_THREADS_PR,
            "DRAFT": DRAFT_PR,
        }
        for expected, pr in cases.items():
            with self.subTest(state=expected):
                state, completion, poll, clock = self._run([pr])
                self.assertFalse(completion.complete)
                self.assertEqual(completion.state, expected)
                self.assertIs(state, pr)
                self.assertEqual(poll.call_count, 1)
                self.assertEqual(clock.sleeps, [])

    def test_closed_is_terminal(self):
        state, completion, poll, clock = self._run([CLOSED_PR])
        self.assertTrue(completion.complete)
        self.assertEqual(completion.state, "CLOSED")
        self.assertIs(state, CLOSED_PR)
        self.assertEqual(poll.call_count, 1)
        self.assertEqual(clock.sleeps, [])

    def test_merged_is_success(self):
        state, completion, poll, clock = self._run([MERGED_PR])
        self.assertTrue(completion.complete)
        self.assertEqual(completion.state, "MERGED")
        self.assertEqual(poll.call_count, 1)
        self.assertEqual(clock.sleeps, [])

    def test_transient_none_then_valid_snapshot(self):
        state, completion, poll, clock = self._run([None, MERGE_READY_PR])
        self.assertEqual(completion.state, "MERGE_READY")
        self.assertEqual(poll.call_count, 2)
        self.assertEqual(clock.sleeps, [60.0])

    def test_timeout_with_no_snapshot(self):
        state, completion, poll, clock = self._run(
            [None, None], timeout_seconds=60.0, interval_seconds=60.0,
        )
        self.assertIsNone(state)
        self.assertFalse(completion.complete)
        self.assertEqual(completion.state, "TIMEOUT")
        self.assertTrue(any("no snapshot" in b for b in completion.blockers))

    def test_timeout_after_snapshots(self):
        state, completion, poll, clock = self._run(
            lambda sandbox, n: REVIEW_REQUIRED_PR,
            timeout_seconds=60.0, interval_seconds=30.0,
        )
        self.assertIs(state, REVIEW_REQUIRED_PR)
        self.assertFalse(completion.complete)
        self.assertEqual(completion.state, "TIMEOUT")
        self.assertTrue(any("REVIEW_REQUIRED" in b for b in completion.blockers))
        # Sleeps clamp to the remaining time so the deadline is not overshot.
        self.assertEqual(clock.sleeps, [30.0, 30.0])


if __name__ == "__main__":
    unittest.main()
