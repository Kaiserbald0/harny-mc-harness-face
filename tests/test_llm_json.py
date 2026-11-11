"""Regression tests for strict parse_key validation in call_json.

Offline: the OpenAI client is mocked. No live LLM calls.
Run from repo root:  PYTHONPATH=. .venv/bin/python tests/test_llm_json.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from harness.llm_call import call_json
from harness.parse import normalize_findings
from harness.role import Role
from harness.trace import RunStep


ROLE = Role(name="tester", model="mock", temperature=0.0, system_prompt="sys")


def make_client(content, finish_reason="stop"):
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    usage = SimpleNamespace(
        completion_tokens=1, prompt_tokens=1, total_tokens=2, cost_details=None
    )
    resp = SimpleNamespace(choices=[choice], usage=usage, model="mock")
    create = mock.Mock(return_value=resp)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def call(content, parse_key="findings", normalizer=normalize_findings):
    client = make_client(content)
    with mock.patch("harness.llm_call.log_step"):
        return call_json(
            role=ROLE, messages=[], client=client, run_id="test",
            step=RunStep.REVIEW, parse_key=parse_key, normalizer=normalizer,
        )


class CallJsonValidationTests(unittest.TestCase):
    def test_empty_object_is_invalid(self):
        decision, items, ok = call("{}")
        self.assertFalse(ok)
        self.assertEqual(items[0]["severity"], "blocker")

    def test_null_findings_is_invalid(self):
        decision, items, ok = call('{"findings": null}')
        self.assertFalse(ok)
        self.assertEqual(items[0]["severity"], "blocker")

    def test_malformed_entries_are_invalid(self):
        decision, items, ok = call('{"findings": ["malformed"]}')
        self.assertFalse(ok)
        self.assertEqual(items[0]["severity"], "blocker")

    def test_empty_findings_list_is_valid(self):
        decision, items, ok = call('{"findings": []}')
        self.assertTrue(ok)
        self.assertEqual(items, [])

    def test_valid_nonempty_findings(self):
        payload = {
            "findings": [
                {"rule": "R1", "severity": "major", "reason": "missing tests"}
            ]
        }
        decision, items, ok = call(json.dumps(payload))
        self.assertTrue(ok)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["rule"], "R1")

    def test_selector_scalar_chosen_is_valid(self):
        decision, items, ok = call(
            '{"chosen": 2, "rationale": "better"}',
            parse_key="chosen", normalizer=None,
        )
        self.assertTrue(ok)
        self.assertEqual(decision["chosen"], 2)
        self.assertEqual(items, [2])


if __name__ == "__main__":
    unittest.main()
