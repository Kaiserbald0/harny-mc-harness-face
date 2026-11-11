"""Regression tests for sandbox escape via files_written / review input.

Offline: no LLM calls, uses mocks and temporary directories.
Run from repo root:  PYTHONPATH=. .venv/bin/python tests/test_sandbox_safety.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from harness.implement import implement
from harness.review import _read_files
from harness.role import Role


ROLE = Role(name="tester", model="mock", temperature=0.0, system_prompt="sys")


def _resp(content="", tool_calls=None, finish_reason="stop"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    usage = SimpleNamespace(
        completion_tokens=1, prompt_tokens=1, total_tokens=2, cost_details=None
    )
    return SimpleNamespace(choices=[choice], usage=usage, model="mock")


def _write_call(call_id, path, content):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name="write_file",
            arguments=json.dumps({"path": path, "content": content}),
        ),
    )


class FakeClient:
    """Returns queued responses, then a final text-only response."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        if self._responses:
            return self._responses.pop(0)
        return _resp(content="done")


def run_implement(tool_calls, dispatch_results):
    client = FakeClient([_resp(tool_calls=tool_calls)])
    with mock.patch("harness.implement.dispatch_tool_call") as dispatch, \
            mock.patch("harness.implement.log_step"):
        dispatch.side_effect = dispatch_results
        return implement(
            plan="plan", findings=[], role=ROLE,
            run_id="test", client=client, max_turns=5,
        )


class FilesWrittenTests(unittest.TestCase):
    def test_rejected_write_absent_from_files_written(self):
        result = run_implement(
            [_write_call("c1", "../evil.txt", "pwned")],
            ["ERROR: write_file raised ValueError: path escapes sandbox"],
        )
        self.assertEqual(result.files_written, [])

    def test_failed_write_absent_from_files_written(self):
        result = run_implement(
            [_write_call("c1", "ok.txt", "hello")],
            ["ERROR: write_file raised OSError: disk full"],
        )
        self.assertEqual(result.files_written, [])

    def test_successful_write_recorded(self):
        result = run_implement(
            [_write_call("c1", "src/main.go", "package main")],
            ["OK: wrote 12 chars to src/main.go"],
        )
        self.assertEqual(result.files_written, ["src/main.go"])


class ReviewPathConfinementTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.sandbox = (root / "sandbox").resolve()
        self.sandbox.mkdir()
        (self.sandbox / "main.go").write_text("package main\n")
        self.external = root / "secret.txt"
        self.external.write_text("top secret\n")
        # symlink inside the sandbox pointing outside it
        self.link = self.sandbox / "link.txt"
        try:
            self.link.symlink_to(self.external)
        except OSError:
            self.link = None

    def test_traversal_cannot_read_external_file(self):
        files, _ = _read_files(self.sandbox, ["../secret.txt"])
        self.assertNotIn("../secret.txt", files)
        self.assertNotIn(str(self.external), files)
        self.assertEqual(files, {})

    def test_absolute_external_path_cannot_be_read(self):
        files, _ = _read_files(self.sandbox, [str(self.external)])
        self.assertEqual(files, {})

    def test_symlink_escape_cannot_be_read(self):
        if self.link is None:
            self.skipTest("symlinks unavailable")
        files, _ = _read_files(self.sandbox, ["link.txt"])
        self.assertEqual(files, {})

    def test_valid_sandbox_file_remains_readable(self):
        files, truncated = _read_files(self.sandbox, ["main.go"])
        self.assertEqual(files, {"main.go": "package main\n"})
        self.assertEqual(truncated, [])


if __name__ == "__main__":
    unittest.main()
