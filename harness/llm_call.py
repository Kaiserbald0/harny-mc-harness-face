"""Consolidated single-call LLM steps.

Every one-shot LLM node (selector, critic, review, revise) used to carry its
own copy of the call/parse/trace logic. The copies drifted; these two
functions are now the only implementation. Multi-turn, tool-using loops
(get_plans, implement) intentionally do not use this module.
"""

import json
import logging
import time
from typing import Callable

import openai

from harness.parse import parse_json_loose
from harness.role import Role
from harness.trace import StepStatus, log_step, RunStep


def _complete(role: Role, messages: list[dict], client: openai.Client):
    t0 = time.time()
    resp = client.chat.completions.create(
        model=role.model,
        temperature=role.temperature,
        messages=messages,
    )
    return resp, int((time.time() - t0) * 1000)


def _row_kwargs(
    role: Role,
    resp,
    duration_ms: int,
    turn: int,
    input_summary: str,
    content: str,
    finish_reason,
    status: StepStatus,
) -> dict:
    usage = resp.usage
    cost = getattr(usage, "cost_details", None) or {}
    return {
        "turn": turn,
        "role": role.name,
        "model": role.model,
        "temperature": role.temperature,
        "input_summary": input_summary,
        "output": content,
        "completion_tokens": usage.completion_tokens if usage else None,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "upstream_inference_cost": cost.get("upstream_inference_cost"),
        "upstream_inference_completions_cost": cost.get("upstream_inference_completions_cost"),
        "upstream_inference_prompt_cost": cost.get("upstream_inference_prompt_cost"),
        "duration_ms": duration_ms,
        "finish_reason": finish_reason,
        "model_served": resp.model,
        "status": status,
        "tool_calls": [],
    }


def call_json(
    role: Role,
    messages: list[dict],
    client: openai.Client,
    run_id: str,
    step: RunStep,
    turn: int = 0,
    input_summary: str = "",
    parse_key: str = "findings",
    normalizer: Callable[[list], list] | None = None,
) -> tuple[dict, list[dict], bool]:
    """One LLM call whose content is parsed as JSON.

    Returns (decision, items, ok): `decision` is the parsed object, `items` is
    decision[parse_key] as a list (scalars are wrapped as a single-item list,
    e.g. the selector's "chosen": 2), normalized when a normalizer is given.
    On truncation or parse/type failure — including a missing/null parse_key,
    a wrongly typed value for a normalized key, or malformed entries discarded
    by normalization — items is a single blocker dict and ok is False.
    Logs exactly one trace row either way.
    """
    resp, duration_ms = _complete(role, messages, client)
    content = resp.choices[0].message.content or ""
    finish_reason = resp.choices[0].finish_reason

    decision: dict = {}
    if finish_reason == "length":
        items = [{"rule": "TRUNCATED", "severity": "blocker", "reason": "response truncated"}]
        ok = False
    else:
        try:
            decision = parse_json_loose(content)
            if not isinstance(decision, dict):
                raise TypeError(f"expected JSON object, got {type(decision).__name__}")
            if parse_key not in decision or decision[parse_key] is None:
                raise ValueError(f"missing or null {parse_key!r} in response")
            raw = decision[parse_key]
            if not isinstance(raw, list):
                if normalizer is not None:
                    raise TypeError(
                        f"expected list for {parse_key!r}, got {type(raw).__name__}"
                    )
                raw = [raw]  # scalar, e.g. the selector's "chosen": 2
            items = normalizer(raw) if normalizer else raw
            if normalizer is not None and len(items) != len(raw):
                raise ValueError(
                    f"{parse_key!r} contained malformed entries discarded during normalization"
                )
            ok = True
        except (json.JSONDecodeError, AttributeError, ValueError, TypeError) as exc:
            logging.warning("parse failed for step=%s: %s — raw[:300]=%r", step, exc, content[:300])
            decision = {}
            items = [{"rule": "PARSE", "severity": "blocker", "reason": str(exc)}]
            ok = False

    if not ok:
        status = StepStatus.RETRY
    else:
        status = StepStatus.OK if resp.usage else StepStatus.ERROR
        if not content and not items:
            status = StepStatus.EMPTY

    row = _row_kwargs(role, resp, duration_ms, turn, input_summary, content, finish_reason, status)
    row[parse_key] = items
    log_step(run_id=run_id, step=step, **row)
    return decision, items, ok


def call_text(
    role: Role,
    messages: list[dict],
    client: openai.Client,
    run_id: str,
    step: RunStep,
    turn: int = 0,
    input_summary: str = "",
) -> tuple[str, bool]:
    """One LLM call whose content is returned unparsed. Logs one trace row."""
    resp, duration_ms = _complete(role, messages, client)
    content = resp.choices[0].message.content or ""
    finish_reason = resp.choices[0].finish_reason

    ok = finish_reason not in ("length", "error")
    if not ok:
        status = StepStatus.RETRY
    else:
        status = StepStatus.OK if resp.usage else StepStatus.ERROR
        if not content:
            status = StepStatus.EMPTY

    log_step(
        run_id=run_id,
        step=step,
        **_row_kwargs(role, resp, duration_ms, turn, input_summary, content, finish_reason, status),
    )
    return content, ok
