import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uuid
from harness import git

run_id = str(uuid.uuid4())
path = f"/tmp/git-test-{run_id[:8]}"
sandbox = Path(path)
sandbox.mkdir(exist_ok=True)

git.ensure_repo(sandbox)
git.create_branch(sandbox, "ai/test")
(sandbox / "hello.txt").write_text("hi\n")
c = git.commit_all(sandbox, "test: hello")
print(path)
print(c)
print(git.diff_against(sandbox))
print(git.changed_files(sandbox))