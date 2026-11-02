import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from harness.review import review
from harness.role import REVIEWER
from harness.verify import verify

SPEC = """
Build a simple API using golang. The APi is an health check for the service so it should respond to GET /health
"""

PLAN = """
1. Create a main.go file in the project directory  
2. Add a GET /health endpoint handler returning HTTP 200 with JSON response {"status":"ok"}  
3. Write a test covering GET /health returning 200 with correct body ===
"""
FILES_WRITTEN = ['main.go', 'main_test.go']

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

result = verify(Path("sandbox"), run_id=run_id, language="go")
print(result.passed)
print(result.summary)
for c in result.commands:
    print(c["cmd"], "->", c["exit"])

findings = review(
    spec=SPEC,
    plan=PLAN,
    run_id=run_id,
    verify_result=result,
    role=REVIEWER,
    client=client,
    path=Path("sandbox"),
    files_written=FILES_WRITTEN,
)

for finding in findings:
    print(finding)