import json
import logging
import time

from harness.parse import parse_json_loose
from harness.trace import log_step, RunStep, StepStatus

TEMPERATURE = 0.0
SYSTEM_PROMPT = """You are a plan critic. You receive a spec and a plan. Your job is
to find violations of the rules below and report them. You do not rewrite the plan.
You do not suggest fixes. You do not write code.

Rules (report violations against these, by ID):
R1 Coverage: every explicit requirement in the spec must map to at least one step
   in the plan.
R2 Tests: the plan must include a step that adds or updates tests for new behaviour.
R3 Security: if the spec implies authentication, permissions, secrets, or handling
   external input, the plan must include a step addressing it.
R4 Backwards compatibility: if the spec modifies existing code, the plan must include
   a step to verify existing behaviour is preserved. If the spec is greenfield, this
   rule does not apply.
R5 Scope: the plan must not include steps the spec did not request or imply. If the
   spec describes the change as simple, minimal, or small, extra steps that go beyond
   the spec are a violation, not a virtue. Do not flag steps that add or update tests under R5 —
   test coverage is required by R2 and is never out of scope
R6 Executability: every step must describe an action that can actually be performed
   in the language and framework named by the spec. Common failures:
   - A step that describes a framework or language operation that does not exist
     (e.g., "add package X to a Go module" — packages are imported in source, not
     added to the module).
   - Two steps that perform the same action ("start the server" and "run the server").
   - A step that describes verification ("run the tests", "curl the endpoint") as if
     it were implementation.

Severity:
- blocker: executing the plan as written would fail to satisfy a requirement in the spec.
- major: the plan includes substantial work outside the scope of the spec, especially
  when the spec describes the change as simple, minimal, or small. A plan that is
  three times longer than necessary is not "more complete" — it is a scope violation.
- minor: a step is too vague to implement without guessing, or duplicates another step.

You can only check what is visible in the spec and the plan. You do not have access to
the repository. Do not report violations that would require reading code. If a rule
cannot be evaluated from the plan and spec alone, skip it.

Output JSON only, no prose before or after:
{"violations": [{"rule": "R1", "severity": "blocker", "reason": "<one sentence>"}]}

If there are no violations, output exactly:
{"violations": []}
"""

def critique(plan: str, spec: str, run_id: str, client, model: str, turn: int = 0) -> list[dict]:
    t0 = time.time()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"<spec>\n{spec}\n</spec>\n\n<plan>\n{plan}\n</plan>"},
    ]

    resp = client.chat.completions.create(
        model=model, temperature=TEMPERATURE, messages=messages,
    )
    msg = resp.choices[0].message
    usage = resp.usage
    cost = getattr(usage, "cost_details", None) or {}
    status = StepStatus.OK if usage else StepStatus.ERROR
    duration_ms = int((time.time() - t0) * 1000)

    try:
        decision = parse_json_loose(msg.content)
        violations = decision.get("violations", [])
        if not isinstance(violations, list):
            raise ValueError(f"violations is {type(violations).__name__}")
    except (json.JSONDecodeError, AttributeError, ValueError) as e:
        logging.warning("critic parse failed: %s", e)
        violations = [{"rule": "PARSE", "severity": "blocker", "reason": str(e)}]

    log_step(
        run_id=run_id,
        step=RunStep.CRITIC,
        turn=turn,
        role="critic",
        model=model,
        temperature=TEMPERATURE,
        input_summary=spec[:500],
        output=msg.content or "",
        completion_tokens=usage.completion_tokens if usage else None,
        prompt_tokens=usage.prompt_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        upstream_inference_cost=cost.get("upstream_inference_cost"),
        upstream_inference_completions_cost=cost.get("upstream_inference_completions_cost"),
        upstream_inference_prompt_cost=cost.get("upstream_inference_prompt_cost"),
        duration_ms=duration_ms,
        finish_reason=resp.choices[0].finish_reason,
        model_served=resp.model,
        status=status,
        tool_calls=[],
        violations=violations,
    )

    return violations
