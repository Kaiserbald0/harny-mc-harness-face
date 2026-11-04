import json
import logging
from pathlib import Path

import openai
import time

from harness.parse import parse_json_loose, normalize_findings
from harness.role import Role
from harness.trace import log_step, StepStatus, RunStep
from harness.verify import VerifyResult


def review(
        spec: str,
        plan: str,
        path: Path,
        verify_result: VerifyResult,
        role: Role,
        run_id: str,
        files_written: list[str],
        client: openai.Client
) -> list[dict]:
    t0 = time.time()
    sandbox = Path(path).resolve()
    files, manifest, truncated = collect_review_input(sandbox, files_written)
    content = build_review_message(
        spec=spec,
        plan=plan,
        files=files,
        manifest=manifest,
        verify_result=verify_result,
        truncated=truncated,
    )

    print(f"\n=== content: \n {content} ===")

    messages = [
        {"role": "system", "content": role.system_prompt},
        {"role": "user", "content": content},
    ]

    resp = client.chat.completions.create(
        model=role.model,
        temperature=role.temperature,
        messages=messages,
        response_format={"type": "json_object"},
    )
    msg = resp.choices[0].message
    usage = resp.usage
    cost = getattr(usage, "cost_details", None) or {}
    status = StepStatus.OK if usage else StepStatus.ERROR
    duration_ms = int((time.time() - t0) * 1000)

    print(f"review: finish_reason={resp.choices[0].finish_reason} "
          f"content_len={len(msg.content or '')} "
          f"reasoning_len={len(msg.reasoning or '') if hasattr(msg, 'reasoning') else 0}"
          f"content={msg.content or ''} "
    )

    try:
        decision = parse_json_loose(msg.content or "")
        raw = decision.get("findings", [])
        if not isinstance(raw, list):
            raise ValueError(f"findings is {type(raw).__name__}")
        findings = normalize_findings(raw)
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        logging.warning("review parse failed: %s", e)
        findings = [{"rule": "PARSE", "severity": "blocker", "reason": str(e)}]

    log_step(
        run_id=run_id,
        step=RunStep.REVIEW,
        turn=0,
        role=role.name,
        model=role.model,
        temperature=role.temperature,
        input_summary=spec[:500],
        output=msg.content or "",
        findings=findings,
        completion_tokens=usage.completion_tokens if usage else None,
        prompt_tokens=usage.prompt_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        upstream_inference_cost=cost.get("upstream_inference_cost"),
        upstream_inference_completions_cost=cost.get("upstream_inference_completions_cost"),
        upstream_inference_prompt_cost=cost.get("upstream_inference_prompt_cost"),
        duration_ms=duration_ms,
        finish_reason=resp.choices[0].finish_reason,
        model_served=resp.model,
        status=status,
    )
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


def collect_review_input(sandbox: Path, written: list[str]) -> tuple[dict[str, str], list[str], list[str]]:
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

def build_review_message(spec: str, plan: str, files: dict[str, str], manifest: list[str], verify_result, truncated: list[str] | None = None) -> str:
    files_block = "\n\n".join(
        f'<file path="{path}">\n{content}\n</file>'
        for path, content in files.items()
    )
    manifest_block = "\n".join(manifest)
    verify_block = format_verify_for_review(verify_result)
    truncated_block = "\n".join(truncated or []) or "none"

    return f"""<spec>
{spec.strip()}
</spec>

<plan>
{plan.strip()}
</plan>

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