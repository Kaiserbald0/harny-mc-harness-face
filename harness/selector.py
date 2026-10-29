import json
import logging
import time

import openai

from harness.trace import StepStatus, log_step, RunStep

SYSTEM_PROMPT = """You are a selector agent. You receive a spec and two candidate
plans, labelled PLAN 1 and PLAN 2. Choose the plan that is better for implementation.

Rules, in priority order:
1. Correctness: the plan must implement every requirement in the spec.
2. Completeness: the plan must cover tests, error handling, and security
   implications relevant to the spec.
3. Simplicity: prefer fewer steps and fewer moving parts, when 1 and 2 are equal.
4. Backwards compatibility: only if the spec modifies existing code, prefer
   plans that do not break existing behaviour.

When rules conflict, prefer correctness over completeness, and completeness
over simplicity. Do not write code. Do not paraphrase the plan.

Respond with JSON only, no prose before or after:
{"chosen": 1 or 2, "rationale": "<one sentence explaining the choice>"}
"""

TEMPERATURE = 0.2

def selector(plans: list[str], spec: str, run_id: str, client: openai.Client, model: str) -> tuple[str, str, int]:
    logging.info("Starting selector")

    user_prompt = ""
    i = 1
    for plan in plans:
        user_prompt += f"<plan id=\"{i}\">\n{plan}\n</plan>\n\n"
    user_prompt += f"<spec>\n{spec}\n</spec>\n"
    user_prompt += "Respond with JSON only: {\"chosen\": 1 or 2, \"rationale\": \"...\"}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    t0 = time.time()
    kwargs = {
        "model": model,
        "temperature": TEMPERATURE,
        "messages": messages
    }

    resp = client.chat.completions.create(**kwargs)
    duration_ms = int((time.time() - t0) * 1000)

    msg = resp.choices[0].message
    usage = resp.usage
    cost = getattr(usage, "cost_details", None) or {}
    status = StepStatus.OK if usage else StepStatus.ERROR
    if msg.content == "":
        status = StepStatus.EMPTY

    turn = 0

    selected_plan_index: int = 0
    selected_plan: str = plans[0]
    rationale: str = msg.content
    try:
        decision = json.loads(msg.content)
        idx = int(decision["chosen"]) - 1
        if 0 <= idx < len(plans):
            selected_plan = plans[idx]
            rationale = decision.get("rationale", "")
            selected_plan_index=idx
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass

    log_step(
        run_id=run_id,
        step=RunStep.SELECTOR,
        turn=turn,
        role="selector",
        model=model,
        temperature=TEMPERATURE,
        input_summary=spec[:500],
        output=msg.content or "",
        completion_tokens=usage.completion_tokens if usage else None,
        prompt_tokens=usage.prompt_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        upstream_inference_cost=cost["upstream_inference_cost"] if cost else None,
        upstream_inference_completions_cost=cost["upstream_inference_completions_cost"] if cost else None,
        upstream_inference_prompt_cost=cost["upstream_inference_prompt_cost"] if cost else None,
        duration_ms=duration_ms,
        finish_reason=resp.choices[0].finish_reason,
        model_served=resp.model,
        status=status,
        tool_calls=[],
        chosen_plan=selected_plan,
        chosen_index=selected_plan_index,
    )

    return selected_plan, rationale, selected_plan_index
