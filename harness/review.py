import logging
from pathlib import Path

import openai

from harness.llm_call import call_json
from harness.parse import normalize_findings
from harness.role import Role
from harness.trace import RunStep
from harness.verify import VerifyResult

MAX_DIFF_CHARS = 30_000

def review(
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
    sandbox = Path(path).resolve()
    files, manifest, truncated = collect_review_input(sandbox, files_written)
    content = build_review_message(
        spec=spec,
        plan=plan,
        files=files,
        manifest=manifest,
        verify_result=verify_result,
        truncated=truncated,
        diff=diff
    )

    logging.debug("review content: %s", content)

    messages = [
        {"role": "system", "content": role.system_prompt},
        {"role": "user", "content": content},
    ]

    _, findings, _ = call_json(
        role=role,
        messages=messages,
        client=client,
        run_id=run_id,
        step=RunStep.REVIEW,
        input_summary=spec[:500],
        parse_key="findings",
        normalizer=normalize_findings,
    )
    # call_json logs the standard row (output=raw content, findings attached).
    # Diff metadata (diff_bytes, truncation, file counts) is recorded in the
    # GIT trace row written by main.py, so no override row is needed here.
    return findings

MAX_FILE_CHARS = 8000
MAX_TOTAL_CHARS = 60000

def _read_files(sandbox: Path, candidates: list[str]) -> tuple[dict[str, str], list[str]]:
    files: dict[str, str] = {}
    truncated: list[str] = []
    total = 0
    for path in candidates:
        p = Path(path)
        if not p.is_absolute():
            p = sandbox / p
        if not p.is_file():
            logging.warning("review input: file %s not found under %s", path, sandbox)
            continue
        content = p.read_text(errors="replace")
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS]
            truncated.append(path)
        if total + len(content) > MAX_TOTAL_CHARS:
            truncated.append(f"{path} (total cap)")
            continue
        files[path] = content
        total += len(content)
    return files, truncated


def collect_review_input(
        sandbox: Path,
        written: list[str]
) -> tuple[dict[str, str], list[str], list[str]]:
    sandbox = Path(sandbox).resolve()

    manifest = sorted(
        str(p.relative_to(sandbox))
        for p in sandbox.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(sandbox).parts)
    )

    files, truncated = _read_files(sandbox, list(dict.fromkeys(written)))  # dedupe, preserve order
    if not files and manifest:
        # The implementer recorded no resolvable writes (e.g. sandbox reused
        # across runs, so it no-op'd) — review everything instead of nothing.
        logging.warning(
            "review input: none of files_written resolved; falling back to all %d files in the sandbox manifest",
            len(manifest),
        )
        files, truncated = _read_files(sandbox, manifest)
    return files, manifest, truncated

def format_verify_for_review(v: VerifyResult) -> str:
    if not v.run:
        return f"ran: no\nreason: {v.summary}"
    return f"ran: yes\nsummary: {v.summary}"

def build_review_message(
        spec: str,
        plan: str,
        files: dict[str, str],
        manifest: list[str],
        verify_result,
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

    diff_truncated = len(diff) > MAX_DIFF_CHARS
    diff_block = diff[:MAX_DIFF_CHARS]
    if diff_truncated:
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

Review the above. Output JSON only: {{"findings": [{{"rule": "...", "severity": "...", "reason": "..."}}]}}"""