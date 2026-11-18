// Shared formatting helpers for epoch-second timestamps and durations.

export function formatTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString()
}

/** "2m 45s" style duration from a span in seconds. */
export function formatSpan(from: number, to: number): string {
  const total = Math.max(0, Math.round(to - from))
  const m = Math.floor(total / 60)
  const s = total % 60
  if (m === 0) return `${s}s`
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/** First non-empty line of a spec, for table snippets. */
export function specSummary(spec: string): string {
  const line = spec.split('\n').map((l) => l.trim()).find(Boolean)
  return line ?? '(empty spec)'
}

export function shortId(runId: string): string {
  return runId.slice(0, 8)
}
