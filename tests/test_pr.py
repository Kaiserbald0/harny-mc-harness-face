import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.pr import poll_pr_state, check_completion
PR_NUMBER = 4

sandbox = Path("/Volumes/Projects/kaiserbald0/harny-mc-test")
pr = poll_pr_state(sandbox, PR_NUMBER)
print(pr)
print(f"unresolved comments: {len(pr.unresolved_comments)}")
for c in pr.unresolved_comments:
    print(f"- [{c.path}:{c.line}] {c.author}: {c.body[:100]!r} ({c.url})")
print(check_completion(pr))