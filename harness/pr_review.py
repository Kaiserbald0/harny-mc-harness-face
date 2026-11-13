"""Machine PR review: a skeptical agent that posts comment reviews on the PR.

Separate from harness/review.py: that reviewer feeds the pre-push fix loop;
this one writes for a public audience (comments posted under the author's own
GitHub identity) and must never post nits. Only blocker/major findings are
posted; minors are dropped in code, not just in the prompt.
"""

import logging
import re

from pathlib import Path

import openai

from harness.llm_call import call_json
from harness.parse import SEVERITY_ALIASES, VALID_SEVERITIES
from harness.pr import PRComment
from harness.role import Role
from harness.review import MAX_DIFF_CHARS, collect_review_input, format_verify_for_review
from harness.trace import RunStep
from harness.verify import VerifyResult

MAX_TITLE_CHARS = 200
MAX_BODY_CHARS = 2000

ACTIONABLE_SEVERITIES = ("blocker", "major")

_FINDING_MARKER = "<!-- harny:finding rule={rule} severity={severity} -->"


def normalize_pr_findings(raw: list) -> list[dict]:
    """Lenient normalizer for PR-review findings. Unlike normalize_findings,
    keeps title/body/path/line and never drops entries — call_json requires
    entry counts to match, so filtering happens after the call."""
    out: list[dict] = []
    for f in raw:
        if not isinstance(f, dict):
            f = {"reason": str(f)}
        sev = str(f.get("severity", "minor")).lower().strip()
        sev = SEVERITY_ALIASES.get(sev, sev)
        if sev not in VALID_SEVERITIES:
            logging.warning("unknown severity %r → defaulting to minor", sev)
            sev = "minor"
        line = f.get("line")
        try:
            line = int(line)
        except (TypeError, ValueError):
            line = None
        out.append({
            "rule": str(f.get("rule", "R?"))[:8],
            "severity": sev,
            "title": str(f.get("title", ""))[:MAX_TITLE_CHARS],
            "body": str(f.get("body", ""))[:MAX_BODY_CHARS],
            "path": str(f.get("path", ""))[:300],
            "line": line,
        })
    return out


def filter_actionable(findings: list[dict]) -> list[dict]:
    """The nit gate: only severities worth a public comment survive."""
    return [f for f in findings if f.get("severity") in ACTIONABLE_SEVERITIES]


def build_pr_review_message(
        spec: str,
        plan: str,
        files: dict[str, str],
        manifest: list[str],
        verify_result: VerifyResult,
        diff: str,
        truncated: list[str] | None = None,
) -> str:
    files_block = "\n\n".join(
        f'<file path="{path}">\n{content}\n</file>'
        for path, content in files.items()
    )
    manifest_block = "\n".join(manifest)
    verify_block = format_verify_for_review(verify_result)
    truncated_block = "\n".join(truncated or []) or "none"

    diff_block = diff[:MAX_DIFF_CHARS]
    if len(diff) > MAX_DIFF_CHARS:
        diff_block += f"\n... (truncated: {len(diff) - MAX_DIFF_CHARS} more chars)"

    return f"""<spec>
{spec.strip()}
</spec>

<plan>
{plan.strip()}
</plan>

<diff>
{diff_block.strip()}
</diff>

<changed_files>
{files_block}
</changed_files>

<truncated>
{truncated_block}
</truncated>

<manifest>
{manifest_block}
</manifest>

<deterministic_checks>
{verify_block}
</deterministic_checks>

Review the pull request. Output JSON only:
{{"findings": [{{"rule": "R1", "severity": "blocker", "title": "<short imperative summary>", "body": "<1-3 sentences of evidence, posted verbatim>", "path": "main.go", "line": 42}}]}}

If there are no substantive findings, output exactly:
{{"findings": []}}"""


def pr_review(
        spec: str,
        plan: str,
        path: Path,
        verify_result: VerifyResult,
        role: Role,
        run_id: str,
        files_written: list[str],
        client: openai.Client,
        diff: str,
) -> list[dict]:
    """One skeptical review pass over the PR's diff. Returns ALL findings
    (including minors) when the call succeeds; on truncation/parse failure
    returns [] — a malformed machine response must never become a posted
    comment. The trace row records the failure either way."""
    sandbox = Path(path).resolve()
    files, manifest, truncated = collect_review_input(sandbox, files_written)
    content = build_pr_review_message(
        spec=spec,
        plan=plan,
        files=files,
        manifest=manifest,
        verify_result=verify_result,
        diff=diff,
        truncated=truncated,
    )

    messages = [
        {"role": "system", "content": role.system_prompt},
        {"role": "user", "content": content},
    ]

    _, findings, ok = call_json(
        role=role,
        messages=messages,
        client=client,
        run_id=run_id,
        step=RunStep.PR_REVIEW,
        input_summary=spec[:500],
        parse_key="findings",
        normalizer=normalize_pr_findings,
    )
    if not ok:
        logging.warning("pr_review call failed (see trace); posting no comments")
        return []
    return findings


def format_review_comment(finding: dict) -> str:
    """Render a finding as a GitHub review comment body. Starts with an HTML
    comment carrying machine-readable rule/severity so threads_to_findings can
    map the thread back into implement()'s findings format; invisible when
    rendered."""
    marker = _FINDING_MARKER.format(
        rule=finding.get("rule", "R?"),
        severity=finding.get("severity", "major"),
    )
    title = finding.get("title") or finding.get("body", "")[:120]
    body = finding.get("body", "")
    where = ""
    if finding.get("path"):
        where = f"`{finding['path']}`" + (f":{finding['line']}" if finding.get("line") else "")
    parts = [marker, "", f"**{title}**", ""]
    if body and body != title:
        parts += [body, ""]
    if where:
        parts += [where, ""]
    return "\n".join(parts).strip()


_MARKER_RE = re.compile(r"<!--\s*harny:finding\s+rule=(\S+)\s+severity=(\S+)\s*-->")


def threads_to_findings(threads: list[PRComment]) -> list[dict]:
    """Map unresolved PR review threads back to implement()-shaped findings.

    Round-trips with format_review_comment. Comments without the marker
    (e.g. left by a human) are still fed to the fixer, as 'major'."""
    findings: list[dict] = []
    for t in threads:
        m = _MARKER_RE.search(t.body)
        rule, severity = (m.group(1), m.group(2)) if m else ("R?", "major")
        severity = SEVERITY_ALIASES.get(severity.lower(), severity)
        if severity not in VALID_SEVERITIES:
            severity = "major"
        visible = _MARKER_RE.sub("", t.body).strip()
        first_line = next((ln for ln in visible.splitlines() if ln.strip()), "")
        findings.append({
            "rule": rule[:8],
            "severity": severity,
            "reason": f"{first_line.strip('* ').strip()} — {t.path}"[:500] if t.path
                      else first_line.strip('* ').strip()[:500],
        })
    return findings
