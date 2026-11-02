import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from harness.implement import implement
from harness.review import review
from harness.role import REVIEWER, IMPLEMENTER
from harness.verify import verify
from main import MAX_FIX_CYCLES

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
for c in result.commands:
    print(c["cmd"], "->", c["exit"])

result.files_written = FILES_WRITTEN

for cycle in range(MAX_FIX_CYCLES):
    verify_result = verify(Path("sandbox"), run_id="test-verify-1", language="go")
    findings = review(
        spec=SPEC, plan=PLAN, path=Path("sandbox"),
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
        plan=PLAN,
        findings=findings,
        client=client,
        run_id=run_id,
        role=IMPLEMENTER,
        max_turns=10,
    )
    if not result.finished:
        print(f"WARN: implementer did not finish after {result.turns_used} turns")
        print(f"      files written so far: {result.files_written}")
    else:
        print(f"implementer fix cycle {cycle} finished in {result.turns_used} turns")
        print(f"files: {result.files_written}")
        print(f"final text: {result.final_text[:200]}")
