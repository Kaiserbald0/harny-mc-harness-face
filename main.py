import uuid

from dotenv import load_dotenv
from openai import OpenAI
import logging
import os

from harness.get_plans import get_plans
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
    plans = get_plans(spec=SPEC, run_id=run_id, client=client)
    print(f"\n=== {len(plans)} plans ===")
    selected_plan, rational = selector(plans=plans, spec=SPEC, run_id=run_id, client=client)
    print(f"\n=== {selected_plan} selected plans ===")
    print(f"\n=== {rational} ===")

if __name__ == "__main__":
    main()
