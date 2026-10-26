import os
from pathlib import Path

# Restricting everything to a sandbox root so HARNY can't nuke the whole disk.
SANDBOX_ROOT = Path(os.environ.get("HARNY_SANDBOX", "./sandbox")).resolve()


def _safe_path(path: str) -> Path:
    p = (SANDBOX_ROOT / path).resolve()
    if not str(p).startswith(str(SANDBOX_ROOT)):
        raise ValueError(f"path escapes sandbox: {path}")
    return p


def read_file(path: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"ERROR: file not found: {path}"
    return p.read_text()[:4000]  # cap, so a big file can't blow the context


def write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"OK: wrote {len(content)} chars to {path}"


def list_dir(path: str = ".") -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"ERROR: dir not found: {path}"
    entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
    return "\n".join(entries) or "(empty)"


TOOL_REGISTRY = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
}