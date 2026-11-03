import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    id: str
    trigger: str                                       # short — what future retrieval matches on
    content: str                                       # long — what gets injected into the prompt
    scope: Literal["global", "repo", "path"] = "global"
    scope_value: str | None = None                     # repo URL or path pattern if scope != global
    created_from_run: str | None = None                # provenance
    use_count: int = 0
    success_count: int = 0
    status: Literal["staging", "active", "retired"] = "active"


MEMORY_ROOT = Path("memory")


def load_skills(scope: str | None = None) -> list[MemoryEntry]:
    """Load active skills. With N<15, inject-all beats retrieval."""
    entries: list[MemoryEntry] = []
    for p in (MEMORY_ROOT / "skills").glob("*.json"):
        try:
            entry = MemoryEntry.model_validate_json(p.read_text())
        except Exception as e:
            logging.warning("skipping malformed skill %s: %s", p.name, e)
            continue
        if entry.status != "active":
            continue
        if scope and entry.scope != scope and entry.scope != "global":
            continue
        entries.append(entry)
    return entries


def format_for_prompt(entries: list[MemoryEntry]) -> str:
    if not entries:
        return ""
    lines = ["<skills>",
             "The following skills were learned from prior runs. Apply them when relevant.",
             ""]
    for e in entries:
        lines.append(f"- [{e.id}] {e.content}")
    lines.append("</skills>")
    return "\n".join(lines)
