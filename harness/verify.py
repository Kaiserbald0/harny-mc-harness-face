import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from harness.language import PROFILES
from harness.trace import log_step, RunStep, StepStatus


@dataclass
class VerifyResult:
    run: bool
    passed: bool
    commands: list[dict] = field(default_factory=list)
    summary: str = ""


def _run(cmd: list[str], cwd: Path, name: str | None = None, timeout: int = 60) -> dict:
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return {
            "name": name or cmd[0],
            "cmd": " ".join(cmd),
            "exit": proc.returncode,
            "output_tail": (proc.stdout + proc.stderr)[-2000:],
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except subprocess.TimeoutExpired:
        return {
            "name": name or cmd[0],
            "cmd": " ".join(cmd),
            "exit": -1,
            "output_tail": f"TIMEOUT after {timeout}s",
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except FileNotFoundError:
        return {
            "name": name or cmd[0],
            "cmd": " ".join(cmd),
            "exit": -2,
            "output_tail": f"command not found: {cmd[0]}",
            "duration_ms": int((time.time() - t0) * 1000),
        }


def _skip(run_id: str, sandbox: Path, reason: str) -> VerifyResult:
    synthetic = {
        "name": "verify", "cmd": "skip", "exit": 0,
        "output_tail": reason, "duration_ms": 0,
    }
    log_step(
        run_id=run_id, step=RunStep.VERIFY, turn=0, role="verify",
        model="", temperature=0.0, input_summary=str(sandbox),
        output=reason, status=StepStatus.EMPTY, duration_ms=0,
    )
    logging.info("verify skipped: %s", reason)
    return VerifyResult(run=False, passed=False, commands=[synthetic], summary=reason)


def _fail(run_id: str, sandbox: Path, reason: str) -> VerifyResult:
    synthetic = {
        "name": "verify", "cmd": "check", "exit": 1,
        "output_tail": reason, "duration_ms": 0,
    }
    log_step(
        run_id=run_id, step=RunStep.VERIFY, turn=0, role="verify",
        model="", temperature=0.0, input_summary=str(sandbox),
        output=reason, status=StepStatus.ERROR, duration_ms=0,
    )
    logging.warning("verify failed: %s", reason)
    return VerifyResult(run=False, passed=False, commands=[synthetic], summary=reason)


def verify(sandbox: Path, run_id: str, language: str | None = None) -> VerifyResult:
    sandbox = Path(sandbox).resolve()

    if language:
        profile = PROFILES.get(language)
        if profile is None:
            return _fail(run_id, sandbox, f"no profile for language={language!r}")
    else:
        profile = next((p for p in PROFILES.values() if p.detect(sandbox)), None)
        if profile is None:
            return _skip(run_id, sandbox, "no language profile matched")

    missing = [f for f in profile.must_have if not (sandbox / f).exists()]
    if missing:
        return _fail(
            run_id, sandbox,
            f"missing required files for {profile.name}: {missing}",
        )

    results = [_run(c.cmd, sandbox, name=c.name) for c in profile.checks]
    for c, r in zip(profile.checks, results):
        if c.fail_if_output and r["exit"] == 0 and r["output_tail"].strip():
            r["exit"] = 1
            r["reason"] = f"{c.name} reported issues"

    passed = all(r["exit"] == 0 for r in results)
    summary = "; ".join(
        f"{r['name']}:{'ok' if r['exit'] == 0 else 'FAIL'}" for r in results
    )

    log_step(
        run_id=run_id, step=RunStep.VERIFY, turn=0, role="verify",
        model="", temperature=0.0, input_summary=str(sandbox),
        output=summary, status=StepStatus.OK if passed else StepStatus.ERROR,
        duration_ms=sum(r["duration_ms"] for r in results),
    )
    logging.info("verify: %s (passed=%s)", summary, passed)
    return VerifyResult(run=True, passed=passed, commands=results, summary=summary)