"""Minimal read-only HTTP API over trace.db for the UI app.

Run from the repo root:
    .venv/bin/uvicorn api.main:app --reload --port 8765

Read-only by design: the harness process owns the writer connection; we use
harness.db.get_reader(), which opens trace.db in mode=ro. WAL journal mode on
the DB lets both read and write proceed concurrently.
"""

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

# Make `from harness.db import ...` work when uvicorn is launched from the
# repo root (or from anywhere else).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.db import get_reader, _JSON_LIST_COLUMNS, _TRACE_COLUMNS  # noqa: E402

app = FastAPI(title="Harny runs API", version="0.1.0")


def _row_to_dict(columns: tuple[str, ...], record: tuple) -> dict:
    return dict(zip(columns, record))


@app.get("/api/runs")
def list_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """List runs, newest first. Optional ?status= filter."""
    reader = get_reader()
    try:
        query = (
            "SELECT run_id, spec, status, created_at, completed_at,"
            " pr_number, pr_url FROM runs"
        )
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = reader.execute(query, params)
        columns = ("run_id", "spec", "status", "created_at", "completed_at",
                   "pr_number", "pr_url")
        return [_row_to_dict(columns, r) for r in cur.fetchall()]
    finally:
        reader.close()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    """One run's summary row."""
    reader = get_reader()
    try:
        cur = reader.execute(
            "SELECT run_id, spec, status, created_at, completed_at,"
            " pr_number, pr_url FROM runs WHERE run_id = ?",
            (run_id,),
        )
        record = cur.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail=f"no run {run_id}")
        columns = ("run_id", "spec", "status", "created_at", "completed_at",
                   "pr_number", "pr_url")
        return _row_to_dict(columns, record)
    finally:
        reader.close()


@app.get("/api/runs/{run_id}/trace")
def get_run_trace(run_id: str):
    """All trace rows for one run, ordered by timestamp."""
    reader = get_reader()
    try:
        exists = reader.execute(
            "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail=f"no run {run_id}")

        cur = reader.execute(
            f"SELECT {', '.join(_TRACE_COLUMNS)} FROM trace_rows"
            " WHERE run_id = ? ORDER BY ts",
            (run_id,),
        )
        rows = []
        for record in cur.fetchall():
            row = _row_to_dict(_TRACE_COLUMNS, record)
            for json_col, field in _JSON_LIST_COLUMNS.items():
                raw = row.pop(json_col)
                row[field] = json.loads(raw) if raw is not None else None
            rows.append(row)
        return {"run_id": run_id, "rows": rows}
    finally:
        reader.close()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("API_PORT", "8765"))
    uvicorn.run("api.main:app", host="127.0.0.1", port=port, reload=True)
