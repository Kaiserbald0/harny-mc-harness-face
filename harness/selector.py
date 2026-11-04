import logging

import openai

from harness.llm_call import call_json
from harness.role import Role
from harness.trace import RunStep

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
    role = Role(name="selector", model=model, temperature=TEMPERATURE, system_prompt=SYSTEM_PROMPT)

    # parse_key="chosen": the decision is a scalar (1 or 2), so call_json wraps
    # it as a single-item list in `items`; the caller reads `decision` and
    # ignores `items`.
    decision, _, ok = call_json(
        role=role,
        messages=messages,
        client=client,
        run_id=run_id,
        step=RunStep.SELECTOR,
        input_summary=spec[:500],
        parse_key="chosen",
    )

    selected_plan_index = 0
    selected_plan = plans[0]
    rationale = ""
    if not ok:
        logging.warning("selector call failed (parse error or truncation); falling back to plans[0]")
        return selected_plan, rationale, selected_plan_index
    try:
        idx = int(decision.get("chosen")) - 1
    except (TypeError, ValueError) as e:
        logging.warning(
            "selector returned unusable chosen=%r; falling back to plans[0]: %s",
            decision.get("chosen"), e,
        )
        return selected_plan, rationale, selected_plan_index
    if not 0 <= idx < len(plans):
        logging.warning(
            "selector returned out-of-range chosen=%r for %d plans; falling back to plans[0]",
            decision.get("chosen"), len(plans),
        )
        return selected_plan, rationale, selected_plan_index
    return plans[idx], str(decision.get("rationale", "")), idx
