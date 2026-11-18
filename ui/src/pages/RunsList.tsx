import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRuns, type Run } from '../api'
import { formatSpan, formatTime, shortId, specSummary } from '../format'

function RunsList() {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    listRuns()
      .then(setRuns)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }

  useEffect(load, [])

  return (
    <section id="page">
      <div className="page-header">
        <h2>Runs</h2>
        <button onClick={load} disabled={runs === null && error === null}>
          Refresh
        </button>
      </div>

      {error !== null && <p className="error">Failed to load runs: {error}</p>}
      {runs === null && error === null && <p>Loading…</p>}

      {runs !== null && runs.length === 0 && <p>No runs yet.</p>}

      {runs !== null && runs.length > 0 && (
        <table className="runs-table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Status</th>
              <th>Spec</th>
              <th>Created</th>
              <th>Duration</th>
              <th>PR</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id}>
                <td>
                  <Link to={`/runs/${run.run_id}`}>
                    <code>{shortId(run.run_id)}</code>
                  </Link>
                </td>
                <td>
                  <span className={`badge badge-${run.status}`}>{run.status}</span>
                </td>
                <td className="spec-cell">{specSummary(run.spec)}</td>
                <td>{formatTime(run.created_at)}</td>
                <td>
                  {run.completed_at !== null
                    ? formatSpan(run.created_at, run.completed_at)
                    : '—'}
                </td>
                <td>
                  {run.pr_url !== null ? (
                    <a href={run.pr_url} target="_blank" rel="noreferrer">
                      #{run.pr_number}
                    </a>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default RunsList
