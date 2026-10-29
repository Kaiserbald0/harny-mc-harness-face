import uuid

from dotenv import load_dotenv
from openai import OpenAI
import logging
import os

from harness.critique import critique
from harness.implement import implement
from harness.role import IMPLEMENTER

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
    plan = """1 Add a main Go file containing the HTTP server setup and health check handler.
2 Implement the health check handler for GET /health to return an HTTP 200 status with a JSON body containing a status of ok.
3 Register the health check handler for the /health path.
4 Add tests for the GET /health handler to verify the HTTP 200 status and expected response body.
5 Add tests to verify that unsupported methods on /health return a client error such as 405."""

    result = implement(
        plan=plan,
        findings=[],
        client=client,
        run_id=run_id,
        role=IMPLEMENTER
    )
    if not result.finished:
        print(f"WARN: implementer did not finish after {result.turns_used} turns")
        print(f"      files written so far: {result.files_written}")
    else:
        print(f"implementer finished in {result.turns_used} turns")
        print(f"files: {result.files_written}")
        print(f"final text: {result.final_text[:200]}")

if __name__ == "__main__":
    main()
