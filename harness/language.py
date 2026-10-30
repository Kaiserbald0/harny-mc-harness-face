from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Check:
    name: str
    cmd: list[str]
    # Optional: how to interpret a "successful" run that still has findings
    fail_if_output: bool = False   # gofmt -l: exit 0 but stdout = failure


@dataclass
class LanguageProfile:
    name: str
    detect: Callable[[Path], bool]         # does this dir look like {lang}?
    must_have: list[str]                   # required files at sandbox root
    checks: list[Check]                    # subprocess checks in order
    format_fix: list[str] = field(default_factory=list)   # e.g. ["gofmt", "-w", "."]


GO = LanguageProfile(
    name="go",
    detect=lambda p: (p / "go.mod").exists() or any(p.glob("*.go")),
    must_have=["go.mod"],
    checks=[
        Check("go test", ["go", "test", "./..."]),
        Check("go vet", ["go", "vet", "./..."]),
        Check("gofmt", ["gofmt", "-l", "."], fail_if_output=True),
    ],
    format_fix=["gofmt", "-w", "."],
)

PYTHON = LanguageProfile(
    name="python",
    detect=lambda p: (
        (p / "pyproject.toml").exists()
        or (p / "requirements.txt").exists()
        or any(p.glob("*.py"))
    ),
    must_have=[],   # pyproject.toml or requirements.txt, but either is fine
    checks=[
        Check("pytest", ["pytest", "-q"]),
        Check("ruff", ["ruff", "check", "."]),
    ],
    format_fix=["ruff", "format", "."],
)

TYPESCRIPT = LanguageProfile(
    name="typescript",
    detect=lambda p: (p / "package.json").exists() and (p / "tsconfig.json").exists(),
    must_have=["package.json", "tsconfig.json"],
    checks=[
        Check("tsc", ["npx", "tsc", "--noEmit"]),
        Check("vitest", ["npx", "vitest", "run"]),
        Check("eslint", ["npx", "eslint", "."]),
    ],
    format_fix=["npx", "prettier", "--write", "."],
)

PROFILES = {p.name: p for p in (GO, PYTHON, TYPESCRIPT)}