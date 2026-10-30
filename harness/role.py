import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from harness.tool_schemas import ALL_TOOL_SCHEMAS

load_dotenv()

PLANNER_BASE = """You are a planning agent. Given a coding spec, produce an
implementation plan as a numbered list of steps.

How to write a step:
- One action per step, imperative mood ("Add X", "Create Y", "Update Z").
- Concrete enough that an engineer could execute it without asking a follow-up.
  "Add a GET /health handler returning 200 with {\"status\":\"ok\"}" is good.
  "Handle the health endpoint" is not.
- When a general engineering concern applies to this specific spec, express it
  as a concrete step. Write "Add a test that POST /health returns 405", not
  "Add tests". Generic restatements of principles are noise — do not include
  them.
- If a concern does not apply to this spec (e.g. backwards compatibility for a
  greenfield service), do not include a step for it.

Output format:
- A numbered list starting at 1. Nothing else.
- No preamble, no reasoning, no trailing commentary, no markdown headers,
  no bold, no code blocks.
- Every step is one line.
"""

PLANNER_CONSERVATIVE_PROMPT = PLANNER_BASE + """
Bias: minimal. Produce the smallest plan that satisfies the spec. Prefer the
fewest steps, the simplest approach, and the fewest moving parts. Every step
must be traceable to an explicit requirement in the spec. If in doubt whether
a step is needed, leave it out.
"""

PLANNER_EXPLORATIVE_PROMPT = PLANNER_BASE + """
Bias: thorough. Produce a plan that anticipates what a reviewer would ask
about: edge cases, error paths, and failure modes the spec implies but does
not state. Prefer explicit over implicit. If two approaches are viable,
choose the one that is easier to verify.
"""
class Role(BaseModel):
    name: str
    model: str
    temperature: float
    system_prompt: str
    tools: list[dict] = Field(default_factory=list)

    model_config = {"frozen": True}

PLANNER_CONSERVATIVE = Role(
    name="planner_conservative",
    model=os.getenv("PLANNER_CONSERVATIVE_MODEL"),
    temperature=0.2,
    system_prompt=PLANNER_CONSERVATIVE_PROMPT,
)

PLANNER_EXPLORATIVE = Role(
    name="planner_explorative",
    model=os.getenv("PLANNER_EXPLORATIVE_MODEL"),
    temperature=0.9,
    system_prompt=PLANNER_EXPLORATIVE_PROMPT
)

TOOL_TESTER = Role(
    name="tool_tester",
    model=os.getenv("TOOL_TESTER_MODEL"),
    temperature=0.0,
    system_prompt= """You are a test agent. Use the available tools to
explore the sandbox. Start by listing the current directory. Then read one
file if present. When you have done both, reply with the single word DONE
and nothing else.""",
    tools=ALL_TOOL_SCHEMAS,
)

IMPLEMENTER_SYSTEM_PROMPT = """You are a software engineer. You receive a spec and a plan. Your job is
to write code that implements the plan, then stop.

When the plan is fully implemented:
- Reply with a short text message (no tool calls) summarising the files you wrote.
- Do NOT keep rewriting files that are already correct.
- Do NOT read a file and then immediately write it back with the same content.
- Do NOT add files the plan does not mention (e.g. README, go.mod if not asked).

If a file you wrote has an error, read it, then write the corrected version once.
If the corrected version is already correct, reply with text and stop.

The plan is complete when every step has a corresponding file on disk. At that point,
stop.
"""

IMPLEMENTER = Role(
    name="implementer",
    model=os.getenv("IMPLEMENTATION_MODEL"),
    temperature=0.0,
    system_prompt=IMPLEMENTER_SYSTEM_PROMPT,
    tools=ALL_TOOL_SCHEMAS,
)