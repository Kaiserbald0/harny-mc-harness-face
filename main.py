import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import logging
import os

from harness.get_plans import get_plans
from harness.implement import implement
from harness.review import review
from harness.role import PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE, IMPLEMENTER, REVIEWER, IMPLEMENTER_FIX
from harness.run_revision import run_revision
from harness.selector import selector
from harness.verify import verify

SPEC = """
Build a simple API using golang. The APi is an health check for the service so it should respond to GET /health
"""

MAX_FIX_CYCLES = 2

def main():
    load_dotenv()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    run_id = str(uuid.uuid4())
    roles_list = [PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE]
    plans = get_plans(spec=SPEC, roles=roles_list, run_id=run_id, client=client)
    print(f"\n=== {len(plans)} plans ===")
    selected_plan, rational, selected_index = selector(
        plans=plans,
        spec=SPEC,
        run_id=run_id,
        client=client,
        model=os.getenv("SELECTOR_MODEL")
    )
    print(f"\n=== {len(plans)} plans ===")
    print(f"\n=== selected plan: \n {selected_plan} ===")
    print(f"\n=== rational: \n{rational} ===")
    chosen_role = roles_list[selected_index]
    revised_plan = run_revision(
        plan=selected_plan,
        role=chosen_role,
        spec=SPEC,
        run_id=run_id,
        client=client
    )
    print(f"\n=== revised plan: \n {revised_plan} ===")

    result = implement(
        plan=revised_plan,
        findings=[],
        client=client,
        run_id=run_id,
        role=IMPLEMENTER,
        max_turns=10,
    )

    if not result.finished:
        print(f"WARN: implementer did not finish after {result.turns_used} turns")
        print(f"      files written so far: {result.files_written}")
    else:
        print(f"implementer finished in {result.turns_used} turns")
        print(f"files: {result.files_written}")
        print(f"final text: {result.final_text[:200]}")

    for cycle in range(MAX_FIX_CYCLES):
        verify_result = verify(Path("sandbox"), run_id="test-verify-1", language="go")
        findings = review(
            spec=SPEC, plan=revised_plan, path=Path("sandbox"),
            verify_result=verify_result, role=REVIEWER,
            run_id=run_id, files_written=result.files_written, client=client,
        )
        blockers = [f for f in findings if f["severity"] in ("blocker", "major")]
        if not blockers and verify_result.passed:
            break
        if cycle == MAX_FIX_CYCLES - 1:
            print(f"WARN: still {len(blockers)} findings; proceeding anyway")
            break
        result = implement(
            plan=revised_plan,
            findings=findings,
            client=client,
            run_id=run_id,
            role=IMPLEMENTER_FIX,
            max_turns=10,
        )
        if not result.finished:
            print(f"WARN: implementer did not finish after {result.turns_used} turns")
            print(f"      files written so far: {result.files_written}")
        else:
            print(f"implementer fix cycle {cycle} finished in {result.turns_used} turns")
            print(f"files: {result.files_written}")
            print(f"final text: {result.final_text[:200]}")

if __name__ == "__main__":
    main()
