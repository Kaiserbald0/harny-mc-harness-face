import json
import time
from harness.role import Role
from harness.trace import log_step, RunStep, StepStatus

def revise(plan: str, role: Role, violations, spec: str, run_id: str, client, turn: int = 0) -> str:
    t0 = time.time()
    violations_json = json.dumps(violations, indent=2)
    messages = [
        {"role": "system", "content": role.system_prompt},
        {"role": "user", "content": f"<spec>\n{spec}\n</spec>\n\n<previous_plan>\n{plan}\n</previous_plan>\n\nA critic reviewed your plan and found these violations:\n<violations>\n{violations_json}\n</violations>Produce a revised plan that fixes these violations. Keep steps that were not implicated in any violation. For each step implicated in a violation, either revise it to satisfy the rule or remove it. Do not introduce new steps unless a violation cannot be fixed without one. Use the same output format as before: a numbered list, one line per step."},
    ]

    resp = client.chat.completions.create(
        model=role.model, temperature=role.temperature, messages=messages,
    )
    msg = resp.choices[0].message
    usage = resp.usage
    cost = getattr(usage, "cost_details", None) or {}
    status = StepStatus.OK if usage else StepStatus.ERROR
    duration_ms = int((time.time() - t0) * 1000)

    log_step(
        run_id=run_id,
        step=RunStep.REVISE,
        turn=turn,
        role=role.name,
        model=role.model,
        temperature=role.temperature,
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
    )

    return msg.content or ""