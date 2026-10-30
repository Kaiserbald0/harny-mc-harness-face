from pathlib import Path
from harness.verify import verify

result = verify(Path("sandbox"), run_id="test-verify-1", language="go")
print(result.passed)
print(result.summary)
for c in result.commands:
    print(c["cmd"], "->", c["exit"])
