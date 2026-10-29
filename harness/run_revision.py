import os

from dotenv import load_dotenv

from harness.critique import critique
from harness.revise import revise
from harness.role import Role

MAX_REVISE_CYCLES = 2

def run_revision(plan: str, role: Role, spec: str, run_id: str, client) -> str:
    load_dotenv()
    selected_plan = plan
    for cycle in range(MAX_REVISE_CYCLES + 1):
        violations = critique(selected_plan, spec, run_id, client, turn=cycle, model=os.getenv("CRITIC_MODEL"))
        blockers = [v for v in violations if v.get("severity") in ("blocker", "major")]
        if not blockers:
            break
        if cycle == MAX_REVISE_CYCLES:
            print(f"WARN: still {len(blockers)} blockers after {MAX_REVISE_CYCLES} cycles; proceeding anyway")
            break
        selected_plan = revise(plan=selected_plan, role=role, violations=violations, spec=spec, run_id=run_id, client=client, turn=cycle)
    return selected_plan

