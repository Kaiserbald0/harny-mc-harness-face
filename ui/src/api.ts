export interface Run {
  run_id: string
  spec: string
  status: string
  created_at: number
  completed_at: number | null
  pr_number: number | null
  pr_url: string | null
}

export interface TraceRow {
  run_id: string
  ts: number
  turn: number
  step: string
  status: string
  role: string | null
  model: string | null
  model_served: string | null
  temperature: number | null
  input_summary: string | null
  output: string | null
  finish_reason: string | null
  completion_tokens: number | null
  prompt_tokens: number | null
  total_tokens: number | null
  duration_ms: number | null
  tool_calls: unknown[] | null
  violations: unknown[] | null
  findings: unknown[] | null
  chosen_index: number | null
  chosen_role: string | null
  chosen_plan: string | null
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`GET ${url} -> ${res.status}: ${body.slice(0, 200)}`)
  }
  return (await res.json()) as T
}

export function listRuns(): Promise<Run[]> {
  return getJson('/api/runs')
}

export function getRun(runId: string): Promise<Run> {
  return getJson(`/api/runs/${encodeURIComponent(runId)}`)
}

export function getRunTrace(
  runId: string,
): Promise<{ run_id: string; rows: TraceRow[] }> {
  return getJson(`/api/runs/${encodeURIComponent(runId)}/trace`)
}
