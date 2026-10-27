import uuid

from dotenv import load_dotenv
from openai import OpenAI

from harness.loop import run_loop
import logging
import os

from harness.role import PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE
from harness.selector import selector

SPEC = """
Build a simple API using golang. The APi is an health check for the service so it should respond to GET /health
"""

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
    plans: list[str] = []
    for role in (PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE):
        print(f"\n=== {role['name']} (t={role['temperature']}) ===")
        plan = run_loop(spec=SPEC, role=role, run_id=run_id, client=client)
        plans.append(plan)

    print(f"\n=== {len(plans)} plans ===")
    selected_plan, rational = selector(plans=plans, spec=SPEC, run_id=run_id, client=client)
    print(f"\n=== {selected_plan} selected plans ===")
    print(f"\n=== {rational} ===")

if __name__ == "__main__":
    main()
