from dotenv import load_dotenv
from harness.loop import run_loop
import logging
import os

from harness.role import PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE

SPEC = """
Read /etc/hostname using the read_file tool.
"""

def main():
    load_dotenv()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    for role in (PLANNER_CONSERVATIVE, PLANNER_EXPLORATIVE):
        print(f"\n=== {role['name']} (t={role['temperature']}) ===")
        print(run_loop(spec=SPEC, role=role))

if __name__ == "__main__":
    main()
