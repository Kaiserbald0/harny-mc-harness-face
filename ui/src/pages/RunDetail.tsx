import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getRun, getRunTrace, type Run, type TraceRow } from '../api'
import {
  formatDurationMs,
  formatSpan,
  formatTime,
  shortId,
} from '../format'

function TraceEntry({ row }: { row: TraceRow }) {
  const summary = [
    formatTime(row.ts),
    `turn ${row.turn}`,
    row.step,
    row.role ?? '',
    row.model ?? '',
  ]
    .filter(Boolean)
    .join(' · ')

  const details: [string, unknown][] = [
    ['input', row.input_summary],
    ['output', row.output],
    ['tool calls', row.tool_calls],
    ['violations', row.violations],
    ['findings', row.findings],
    ['chosen plan', row.chosen_plan],
  ]

  return (
    <li className="trace-entry">
      <div className="trace-head">
        <span className={`badge badge-${row.status}`}>{row.status}</span>
        <span className="trace-summary">{summary}</span>
        <span className="trace-meta">
          {row.duration_ms !== null && formatDurationMs(row.duration_ms)}
          {row.total_tokens !== null && ` · ${row.total_tokens} tok`}
        </span>
      </div>
      {details.some(([, v]) => v !== null && v !== undefined && v !== '') && (
        <details>
          <summary>details</summary>
          {details
            .filter(([, v]) => v !== null && v !== undefined && v !== '')
            .map(([label, value]) => (
              <div key={label} className="trace-detail">
                <strong>{label}</strong>
                <pre>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>
              </div>
            ))}
        </details>
      )}
    </li>
  )
}

function RunDetail() {
  const { runId = '' } = useParams()
  const [run, setRun] = useState<Run | null>(null)
  const [trace, setTrace] = useState<TraceRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setRun(null)
    setTrace(null)
    setError(null)
    getRun(runId)
      .then(setRun)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
    getRunTrace(runId)
      .then((t) => setTrace(t.rows))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [runId])

  return (
    <section id="page">
      <p>
        <Link to="/">← all runs</Link>
      </p>

      {error !== null && <p className="error">Failed to load run: {error}</p>}

      {run === null && error === null && <p>Loading…</p>}

      {run !== null && (
        <>
          <div className="page-header">
            <h2>
              Run <code>{shortId(run.run_id)}</code>{' '}
              <span className={`badge badge-${run.status}`}>{run.status}</span>
            </h2>
            {run.pr_url !== null && (
              <a href={run.pr_url} target="_blank" rel="noreferrer">
                PR #{run.pr_number}
              </a>
            )}
          </div>
          <p className="run-meta">
            started {formatTime(run.created_at)}
            {run.completed_at !== null &&
              ` · took ${formatSpan(run.created_at, run.completed_at)}`}
          </p>
          <pre className="run-spec">{run.spec}</pre>
        </>
      )}

      {trace === null && error === null ? (
        <p>Loading trace…</p>
      ) : (
        trace !== null && (
          <>
            <h2 className="trace-title">Trace ({trace.length} rows)</h2>
            <ul className="trace-list">
              {trace.map((row, i) => (
                <TraceEntry key={i} row={row} />
              ))}
            </ul>
          </>
        )
      )}
    </section>
  )
}

export default RunDetail
