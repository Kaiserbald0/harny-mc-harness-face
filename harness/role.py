from harness.tool_schemas import ALL_TOOL_SCHEMAS

SYSTEM_PROMPT = """You are a planning agent. Given a coding spec, produce a
short, concrete, step-by-step plan. Do not write code. Do not explain your
reasoning. Output only the plan as a numbered list.

Rules:
1. Security: call out any auth/permission implications.
2. Tests: every new behaviour must have a test.
3. Backwards compatibility: flag anything that breaks an existing API.
"""

PLANNER_CONSERVATIVE = {
    "name": "planner_conservative",
    "model": "cohere/north-mini-code:free",   # swap for whatever free model you like
    "temperature": 0.2,
    "system_prompt": SYSTEM_PROMPT,
    "tools": [],
}

PLANNER_EXPLORATIVE = {
    "name": "planner_explorative",
    "model": "recursive/flint-v1.0:free",
    "temperature": 0.9,
    "system_prompt": SYSTEM_PROMPT,
    "tools": [],
}

TOOL_TESTER = {
    "name": "tool_tester",
    "model": "recursive/flint-v1.0:free",   # must support tool calling
    "temperature": 0.0,
    "system_prompt": """You are a test agent. Use the available tools to
explore the sandbox. Start by listing the current directory. Then read one
file if present. When you have done both, reply with the single word DONE
and nothing else.""",
    "tools": ALL_TOOL_SCHEMAS,
}