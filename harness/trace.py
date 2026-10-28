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

class TraceRow(BaseModel):
    ts: float = Field(default_factory=time.time)
    run_id: str
    turn: int
    step: RunStep = RunStep.PLANNER
    status: StepStatus = StepStatus.OK
    role: str
    model: str
    temperature: float
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int
    upstream_inference_cost: float
    upstream_inference_completions_cost: float
    upstream_inference_prompt_cost: float
    duration_ms: float | None = None
    input_summary: str = Field(min_length=1, max_length=500)
    output: str
    finish_reason: str
    model_served: str
    tool_calls: list[dict[str, Any]] | None = None
    chosen_index: int | None = None
    chosen_role: str | None = None
    violations: list[dict] | None = None

def log_step(**fields):
    row = TraceRow(**fields)
    with open(TRACE_PATH, "a") as f:
        f.write(row.model_dump_json() + "\n")
