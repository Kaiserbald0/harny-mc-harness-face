import json

from harness.tool import TOOL_REGISTRY


def dispatch_tool_call(tool_call) -> str:
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError as e:
        return f"ERROR: bad JSON args: {e}"

    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"ERROR: unknown tool: {name}"

    try:
        return str(fn(**args))
    except TypeError as e:
        return f"ERROR: bad args for {name}: {e}"
    except Exception as e:
        return f"ERROR: {name} raised {type(e).__name__}: {e}"
