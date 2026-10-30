import os
import time
from enum import Enum

from pydantic import BaseModel, Field
from typing import Any

TRACE_PATH = os.getenv("TRACE_PATH", "trace.jsonl")
if not TRACE_PATH:
    raise ValueError("TRACE_PATH environment variable is not set")

class StepStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    RETRY = "retry"
    EMPTY = "empty"

class RunStep(str, Enum):
    PLANNER = "planner"
    SELECTOR = "selector"
    CRITIC = "critic"
    REVISE = "revise"
    IMPLEMENTATION = "implementation"
    VERIFY = "verify"

class TraceRow(BaseModel):
    ts: float = Field(default_factory=time.time)
    run_id: str
    turn: int
    step: RunStep = RunStep.PLANNER
    status: StepStatus = StepStatus.OK
    role: str
    model: str
    temperature: float
    completion_tokens: int | None = None
    prompt_tokens: int | None = None
    total_tokens: int | None = None
    upstream_inference_cost: float | None = None
    upstream_inference_completions_cost: float | None = None
    upstream_inference_prompt_cost: float | None = None
    duration_ms: float | None = None
    input_summary: str = Field(min_length=1, max_length=500)
    output: str
    finish_reason: str | None = None
    model_served: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    chosen_index: int | None = None
    chosen_role: str | None = None
    violations: list[dict] | None = None

def log_step(**fields):
    row = TraceRow(**fields)
    with open(TRACE_PATH, "a") as f:
        f.write(row.model_dump_json() + "\n")
