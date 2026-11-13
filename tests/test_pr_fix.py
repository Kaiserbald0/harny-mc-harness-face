"""Offline tests for the machine PR-review loop: nit filtering, comment
rendering/parsing round-trip, thread resolution, and comment posting.
gh and LLM calls are mocked; no network. No venv pytest needed.

Run from repo root:  .venv/bin/python tests/test_pr_fix.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from unittest import mock

from harness.git import post_pr_comment
from harness.pr import PRComment, resolve_review_threads
from harness.pr_review import (
    filter_actionable,
    format_review_comment,
    normalize_pr_findings,
    threads_to_findings,
)

BLOCKER = {"rule": "R3", "severity": "blocker", "title": "Handler ignores ctx",
           "body": "The handler never respects request context cancellation.",
           "path": "main.go", "line": 42}
MAJOR = {"rule": "R2", "severity": "warning", "title": "Test asserts nothing",
         "body": "TestHealth always passes because it never calls the handler.",
         "path": "main_test.go", "line": 7}
NIT = {"rule": "R3", "severity": "minor", "title": "rename variable",
       "body": "x could be named better.", "path": "main.go", "line": 3}


class NormalizeTests(unittest.TestCase):
    def test_keeps_all_entries_and_maps_aliases(self):
        out = normalize_pr_findings([BLOCKER, MAJOR, NIT, "garbage"])
        self.assertEqual(len(out), 4)
        self.assertEqual(out[1]["severity"], "major")   # "warning" alias
        self.assertEqual(out[3]["severity"], "minor")   # non-dict coerced
        self.assertEqual(out[0]["title"], BLOCKER["title"])
        self.assertEqual(out[0]["line"], 42)

    def test_bad_severity_defaults_minor_and_line_coercion(self):
        out = normalize_pr_findings([
            {"rule": "R3", "severity": "catastrophic", "line": "12"},
        ])
        self.assertEqual(out[0]["severity"], "minor")
        self.assertEqual(out[0]["line"], 12)


class FilterTests(unittest.TestCase):
    def test_only_blocker_and_major_survive(self):
        normalized = normalize_pr_findings([BLOCKER, MAJOR, NIT])
        actionable = filter_actionable(normalized)
        self.assertEqual([f["title"] for f in actionable],
                         [BLOCKER["title"], MAJOR["title"]])

    def test_empty_input(self):
        self.assertEqual(filter_actionable([]), [])


class RoundTripTests(unittest.TestCase):
    def test_comment_then_thread_parses_back(self):
        body = format_review_comment(BLOCKER)
        self.assertIn("harny:finding rule=R3 severity=blocker", body)
        self.assertIn("**Handler ignores ctx**", body)
        self.assertIn("`main.go`:42", body)

        thread = PRComment(body=body[:500], author="me", path="main.go",
                           line=42, url="", thread_id="T_1")
        findings = threads_to_findings([thread])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule"], "R3")
        self.assertEqual(findings[0]["severity"], "blocker")
        self.assertIn("Handler ignores ctx", findings[0]["reason"])
        self.assertIn("main.go", findings[0]["reason"])

    def test_human_comment_without_marker_becomes_major(self):
        thread = PRComment(body="This breaks when the port is taken", author="human",
                           path="", line=None, url="")
        findings = threads_to_findings([thread])
        self.assertEqual(findings[0]["severity"], "major")
        self.assertEqual(findings[0]["rule"], "R?")

    def test_marker_inside_long_body_survives_500_char_truncation(self):
        finding = dict(BLOCKER, body="x" * 3000)
        body = format_review_comment(finding)
        thread = PRComment(body=body[:500], author="me", path="", line=None, url="")
        findings = threads_to_findings([thread])
        self.assertEqual(findings[0]["rule"], "R3")


class ResolveThreadsTests(unittest.TestCase):
    def _run(self, side_effect, thread_ids=None):
        thread_ids = ["T_1", "T_2", ""] if thread_ids is None else thread_ids
        with mock.patch("harness.pr._run", side_effect=side_effect) as m:
            return resolve_review_threads(Path("/nonexistent"), thread_ids), m

    def test_counts_resolved_and_failed(self):
        (resolved, failed), m = self._run([(0, "{}", ""), (1, "", "boom"), (0, "{}", "")])
        self.assertEqual((resolved, failed), (1, 2))  # empty id counts as failed
        self.assertEqual(m.call_count, 2)             # empty id never shells out

    def test_mutation_call_shape(self):
        _, m = self._run([(0, "{}", "")], thread_ids=["T_1"])
        cmd = m.call_args[0][0]
        self.assertEqual(cmd[:3], ["gh", "api", "graphql"])
        self.assertIn("resolveReviewThread", cmd[4])
        self.assertIn("threadId=T_1", cmd)


class PostCommentTests(unittest.TestCase):
    def test_success(self):
        with mock.patch("harness.git._run", return_value=(0, "", "")) as m:
            ok, msg = post_pr_comment(Path("/nonexistent"), 4, "hello")
        self.assertTrue(ok)
        cmd = m.call_args[0][0]
        self.assertEqual(cmd[:5], ["gh", "pr", "review", "4", "--comment"])

    def test_failure(self):
        with mock.patch("harness.git._run", return_value=(1, "", "no PR found")):
            ok, msg = post_pr_comment(Path("/nonexistent"), 4, "hello")
        self.assertFalse(ok)
        self.assertIn("no PR found", msg)


if __name__ == "__main__":
    unittest.main()
