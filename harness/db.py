import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.trace import TraceRow

_PRAGMAS = (
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA busy_timeout = 5000;",
    "PRAGMA foreign_keys = ON;",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    spec          TEXT NOT NULL,
    status        TEXT NOT NULL,          -- running | complete | failed | stuck
    created_at    REAL NOT NULL,
    completed_at  REAL,
    pr_number     INTEGER,
    pr_url        TEXT
);

CREATE TABLE IF NOT EXISTS trace_rows (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   TEXT NOT NULL REFERENCES runs(run_id),
    ts                       REAL NOT NULL,
    turn                     INTEGER NOT NULL,
    step                     TEXT NOT NULL,
    status                   TEXT NOT NULL,
    role                     TEXT,
    model                    TEXT,
    model_served             TEXT,
    temperature              REAL,
    input_summary            TEXT,
    output                   TEXT,
    finish_reason            TEXT,
    completion_tokens        INTEGER,
    prompt_tokens            INTEGER,
    total_tokens             INTEGER,
    upstream_inference_cost  REAL,
    upstream_inference_completions_cost REAL,
    upstream_inference_prompt_cost      REAL,
    duration_ms              REAL,
    tool_calls_json          TEXT,       -- JSON array or NULL
    violations_json          TEXT,       -- JSON array or NULL
    findings_json            TEXT,       -- JSON array or NULL
    chosen_index             INTEGER,
    chosen_role              TEXT,
    chosen_plan              TEXT
);

CREATE INDEX IF NOT EXISTS idx_trace_run_step ON trace_rows(run_id, step);
CREATE INDEX IF NOT EXISTS idx_trace_status   ON trace_rows(status);
CREATE INDEX IF NOT EXISTS idx_trace_ts       ON trace_rows(ts);
"""

# Column order used for INSERT and SELECT in export_run_jsonl.
_TRACE_COLUMNS = (
    "run_id", "ts", "turn", "step", "status", "role", "model", "model_served",
    "temperature", "input_summary", "output", "finish_reason",
    "completion_tokens", "prompt_tokens", "total_tokens",
    "upstream_inference_cost", "upstream_inference_completions_cost",
    "upstream_inference_prompt_cost", "duration_ms",
    "tool_calls_json", "violations_json", "findings_json",
    "chosen_index", "chosen_role", "chosen_plan",
)

_JSON_LIST_COLUMNS = {
    "tool_calls_json": "tool_calls",
    "violations_json": "violations",
    "findings_json": "findings",
}

_init_lock = threading.Lock()  # guards lazy creation of the writer connection
_lock = threading.Lock()       # guards statement execution (INSERT / UPDATE)
_writer: sqlite3.Connection | None = None


def _db_path() -> str:
    default = str(Path(__file__).resolve().parent.parent / "trace.db")
    return os.environ.get("HARNY_DB", default)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    for pragma in _PRAGMAS:
        conn.execute(pragma)


def init_db(db_path: str | None = None) -> str:
    """Create tables if missing. Returns the resolved db path."""
    path = db_path or _db_path()
    conn = sqlite3.connect(path)
    try:
        _apply_pragmas(conn)
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return path


def get_writer() -> sqlite3.Connection:
    """Return the process-wide writer connection. Idempotent."""
    global _writer
    if _writer is None:
        with _init_lock:
            if _writer is None:
                conn = sqlite3.connect(_db_path())
                _apply_pragmas(conn)
                conn.executescript(_SCHEMA)
                _writer = conn
    return _writer


def get_reader() -> sqlite3.Connection:
    """Return a read-only connection (mode=ro). For the UI later; useful now for tests."""
    uri = f"file:{_db_path()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    _apply_pragmas(conn)
    return conn


def create_run(run_id: str, spec: str) -> None:
    """Insert a row into runs with status='running'."""
    conn = get_writer()
    with _lock:
        conn.execute(
            "INSERT INTO runs (run_id, spec, status, created_at) VALUES (?, ?, 'running', ?)",
            (run_id, spec, time.time()),
        )
        conn.commit()


def finish_run(
    run_id: str,
    status: str,
    pr_number: int | None = None,
    pr_url: str | None = None,
) -> None:
    """Update runs.status and completed_at. status in {complete, failed, stuck}."""
    conn = get_writer()
    with _lock:
        conn.execute(
            "UPDATE runs SET status = ?, completed_at = ?,"
            " pr_number = COALESCE(?, pr_number),"
            " pr_url = COALESCE(?, pr_url)"
            " WHERE run_id = ?",
            (status, time.time(), pr_number, pr_url, run_id),
        )
        conn.commit()


def insert_trace_row(row: "TraceRow") -> None:
    """Insert one validated TraceRow. Called from log_step()."""
    data = row.model_dump(mode="json")
    values = []
    for col in _TRACE_COLUMNS:
        if col in _JSON_LIST_COLUMNS:
            raw = data[_JSON_LIST_COLUMNS[col]]
            values.append(json.dumps(raw) if raw is not None else None)
        else:
            values.append(data[col])
    placeholders = ", ".join("?" for _ in _TRACE_COLUMNS)
    conn = get_writer()
    with _lock:
        conn.execute(
            f"INSERT INTO trace_rows ({', '.join(_TRACE_COLUMNS)}) VALUES ({placeholders})",
            tuple(values),
        )
        conn.commit()


def export_run_jsonl(run_id: str, out_path: Path) -> Path:
    """Write artifacts/<run_id>/trace.jsonl from the DB, rows ordered by ts."""
    from harness.trace import TraceRow  # local import: trace.py imports this module

    reader = get_reader()
    try:
        cur = reader.execute(
            f"SELECT {', '.join(_TRACE_COLUMNS)} FROM trace_rows"
            " WHERE run_id = ? ORDER BY ts",
            (run_id,),
        )
        lines = []
        for record in cur.fetchall():
            kwargs = dict(zip(_TRACE_COLUMNS, record))
            for json_col, field_name in _JSON_LIST_COLUMNS.items():
                raw = kwargs.pop(json_col)
                kwargs[field_name] = json.loads(raw) if raw is not None else None
            lines.append(TraceRow(**kwargs).model_dump_json())
    finally:
        reader.close()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for line in lines:
            f.write(line + "\n")
    return out_path
