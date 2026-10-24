import os
import time
from pydantic import BaseModel, Field

TRACE_PATH = os.getenv("TRACE_PATH", "trace.jsonl")
if not TRACE_PATH:
    raise ValueError("TRACE_PATH environment variable is not set")

class StepStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    RETRY = "retry"

class RunStep(str, Enum):
    PLANNER = "planner"
    SELECTOR = "selector"
    CRITIC = "critic"

class TraceRow(BaseModel):
    ts: float = Field(default_factory=time.time)
    run_id: str
    step: RunStep = RunStep.PLANNER
    status: StepStatus = StepStatus.OK
    role: str
    model: str
    temperature: float
    input_tokens: int
    output_tokens: int
    cost_estimated: float
    duration_ms: float | None = None
    input_summary: str = Field(min_length=1, max_length=500)
    output: str

def log_step(**fields):
    row = TraceRow(**fields)
    with open(TRACE_PATH, "a") as f:
        f.write(row.model_dump_json() + "\n")
