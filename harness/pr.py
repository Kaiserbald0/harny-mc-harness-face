import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


def _run(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError as e:
        return -2, "", str(e)


@dataclass
class PRComment:
    body: str
    author: str
    path: str
    line: int | None
    url: str


@dataclass
class PRState:
    number: int
    state: str               # OPEN, CLOSED, MERGED
    is_draft: bool
    mergeable: str           # MERGEABLE, CONFLICTING, UNKNOWN
    merge_state_status: str  # CLEAN, DIRTY, BLOCKED, BEHIND, UNSTABLE, DRAFT, UNKNOWN
    review_decision: str     # APPROVED, CHANGES_REQUESTED, REVIEW_REQUIRED, ""
    head_ref_oid: str
    status_check_rollup: list[dict] = field(default_factory=list)
    url: str = ""
    unresolved_comments: list[PRComment] = field(default_factory=list)


_REVIEW_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          comments(first: 1) {
            nodes { body author { login } path line url }
          }
        }
      }
    }
  }
}
"""


def _fetch_unresolved_comments(sandbox: Path, pr_number: int) -> list[PRComment]:
    rc, out, err = _run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        sandbox,
    )
    if rc != 0:
        logging.warning("gh repo view failed: %s", err[:300])
        return []
    repo = out.strip()
    if "/" not in repo:
        logging.warning("unexpected repo name %r", repo)
        return []
    owner, name = repo.split("/", 1)
    rc, out, err = _run(
        ["gh", "api", "graphql",
         "-f", f"query={_REVIEW_THREADS_QUERY}",
         "-f", f"owner={owner}",
         "-f", f"name={name}",
         "-F", f"number={pr_number}"],
        sandbox,
    )
    if rc != 0:
        logging.warning("gh api graphql failed: %s", err[:300])
        return []
    try:
        d = json.loads(out)
        threads = d["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logging.warning("graphql response unparsable: %s — %r", e, out[:300])
        return []
    comments = []
    for t in threads:
        if t.get("isResolved"):
            continue
        nodes = (t.get("comments") or {}).get("nodes") or []
        if not nodes:
            continue
        c = nodes[0]
        comments.append(PRComment(
            body=(c.get("body") or "")[:500],
            author=(c.get("author") or {}).get("login") or "",
            path=c.get("path") or "",
            line=c.get("line"),
            url=c.get("url") or "",
        ))
    return comments


def poll_pr_state(sandbox: Path, pr_number: int) -> PRState | None:
    rc, out, err = _run(
        ["gh", "pr", "view", str(pr_number), "--json",
         "number,state,isDraft,mergeable,mergeStateStatus,reviewDecision,"
         "headRefOid,statusCheckRollup,url"],
        sandbox,
    )
    if rc != 0:
        logging.warning("gh pr view failed: %s", err[:300])
        return None
    try:
        d = json.loads(out)
    except json.JSONDecodeError as e:
        logging.warning("gh pr view returned non-JSON: %s — %r", e, out[:300])
        return None
    state = d.get("state", "") or ""
    return PRState(
        number=d.get("number", pr_number),
        state=state,
        is_draft=bool(d.get("isDraft")),
        mergeable=d.get("mergeable", "") or "",
        merge_state_status=d.get("mergeStateStatus", "") or "",
        review_decision=d.get("reviewDecision", "") or "",
        head_ref_oid=d.get("headRefOid", "") or "",
        status_check_rollup=d.get("statusCheckRollup") or [],
        url=d.get("url", "") or "",
        unresolved_comments=_fetch_unresolved_comments(sandbox, pr_number) if state == "OPEN" else [],
    )


@dataclass
class CompletionResult:
    complete: bool
    state: str
    blockers: list[str] = field(default_factory=list)


def check_completion(pr: PRState, unresolved_threads: int | None = None) -> CompletionResult:
    if unresolved_threads is None:
        unresolved_threads = len(pr.unresolved_comments)
    # Terminal states first.
    if pr.state == "MERGED":
        return CompletionResult(True, "MERGED")
    if pr.state == "CLOSED":
        return CompletionResult(True, "CLOSED", ["PR closed without merge"])
    if pr.state != "OPEN":
        return CompletionResult(False, "UNKNOWN", [f"state={pr.state!r}"])

    # Structural blockers.
    if pr.is_draft:
        return CompletionResult(False, "DRAFT", ["PR is draft"])
    if pr.mergeable == "CONFLICTING" or pr.merge_state_status == "DIRTY":
        return CompletionResult(False, "CONFLICTING", ["merge conflict"])
    if pr.merge_state_status == "BEHIND":
        return CompletionResult(False, "BEHIND", ["branch behind base; needs update"])

    # CI.
    failing = [
        c for c in pr.status_check_rollup
        if (c.get("conclusion") or "").upper() in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")
    ]
    if failing:
        names = ", ".join(c.get("name") or c.get("context") or "?" for c in failing[:5])
        return CompletionResult(False, "CI_FAILED", [f"failing checks: {names}"])

    # In-progress CI — wait, don't act.
    pending = [
        c for c in pr.status_check_rollup
        if (c.get("status") or "").upper() in ("QUEUED", "IN_PROGRESS", "PENDING")
        or (c.get("conclusion") is None and c.get("state") in ("PENDING", "EXPECTED"))
    ]
    if pending:
        return CompletionResult(False, "CI_PENDING", [f"{len(pending)} check(s) pending"])

    # Review feedback.
    if pr.review_decision == "CHANGES_REQUESTED":
        return CompletionResult(False, "CHANGES_REQUESTED", ["formal change request"])
    if unresolved_threads > 0:
        blocker = f"{unresolved_threads} unresolved thread(s)"
        if pr.unresolved_comments:
            c = pr.unresolved_comments[0]
            where = f"{c.path}:{c.line}" if c.path else "PR"
            preview = c.body[:120] + ("…" if len(c.body) > 120 else "")
            blocker += f" — first: [{where}] {preview!r}"
        return CompletionResult(False, "UNRESOLVED_THREADS", [blocker])

    # Positive terminal.
    if pr.review_decision == "APPROVED" and pr.merge_state_status == "CLEAN":
        return CompletionResult(True, "MERGE_READY")
    if pr.merge_state_status == "CLEAN":
        # No review policy on this repo (or no required reviewers).
        return CompletionResult(True, "MERGE_READY")

    if pr.merge_state_status == "BLOCKED":
        return CompletionResult(False, "BLOCKED", ["branch protection blocks merge"])
    if pr.review_decision == "REVIEW_REQUIRED":
        return CompletionResult(False, "REVIEW_REQUIRED", ["waiting for reviewer"])

    return CompletionResult(False, "UNKNOWN",
                            [f"mergeable={pr.mergeable} merge_state={pr.merge_state_status} review={pr.review_decision}"])


# Completion states that mean "nothing to do but wait" — keep polling.
_POLL_CONTINUE_STATES = {"CI_PENDING", "REVIEW_REQUIRED", "BLOCKED", "UNKNOWN"}


def wait_for_merge_ready(
    sandbox: Path,
    pr_number: int,
    timeout_seconds: float = 7200,
    interval_seconds: float = 60,
) -> tuple[PRState | None, CompletionResult]:
    """Poll until the PR is merge-ready, needs orchestrator action, or times out.

    Returns the most recent PRState (None if no snapshot was ever fetched)
    and the CompletionResult that ended the wait.
    """
    deadline = time.monotonic() + timeout_seconds
    last_state: PRState | None = None
    last_completion: CompletionResult | None = None

    while True:
        snapshot = poll_pr_state(sandbox, pr_number)
        if snapshot is None:
            logging.warning("PR %s: poll failed (transient); retrying", pr_number)
        else:
            last_state = snapshot
            completion = check_completion(snapshot)
            last_completion = completion
            if completion.state not in _POLL_CONTINUE_STATES:
                return snapshot, completion

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval_seconds, remaining))

    if last_completion is not None:
        detail = "; ".join(last_completion.blockers) or "no blockers"
        blockers = [
            f"timed out after {timeout_seconds:.0f}s waiting for PR {pr_number} "
            f"to become merge-ready; last state={last_completion.state}: {detail}"
        ]
    else:
        blockers = [
            f"timed out after {timeout_seconds:.0f}s waiting for PR {pr_number} "
            "to become merge-ready; no snapshot ever fetched"
        ]
    return last_state, CompletionResult(False, "TIMEOUT", blockers)