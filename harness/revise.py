import json

from harness.llm_call import call_text
from harness.role import Role
from harness.trace import RunStep

def revise(plan: str, role: Role, violations, spec: str, run_id: str, client, turn: int = 0) -> str:
    violations_json = json.dumps(violations, indent=2)
    messages = [
        {"role": "system", "content": role.system_prompt},
        {"role": "user", "content": f"<spec>\n{spec}\n</spec>\n\n<previous_plan>\n{plan}\n</previous_plan>\n\nA critic reviewed your plan and found these violations:\n<violations>\n{violations_json}\n</violations>Produce a revised plan that fixes these violations. Keep steps that were not implicated in any violation. For each step implicated in a violation, either revise it to satisfy the rule or remove it. Do not introduce new steps unless a violation cannot be fixed without one. Use the same output format as before: a numbered list, one line per step."},
    ]

    text, _ = call_text(
        role=role,
        messages=messages,
        client=client,
        run_id=run_id,
        step=RunStep.REVISE,
        turn=turn,
        input_summary=spec[:500],
    )
    return text
