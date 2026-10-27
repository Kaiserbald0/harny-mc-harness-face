import logging
import time

import openai
from dotenv import load_dotenv

from harness.tool_dispatcher import dispatch_tool_call
from harness.trace import log_step, RunStep, StepStatus

load_dotenv()


def run_loop(spec: str, role: dict, client: openai.Client, run_id: str, max_turns: int = 3) -> str:
    logging.info("Starting harness loop")

    messages = [
        {"role": "system", "content": role["system_prompt"]},
        {"role": "user", "content": spec},
    ]
    tools = role.get("tools", [])

    final_text = ""
    for turn in range(max_turns):
        t0 = time.time()
        kwargs = {
            "model": role["model"],
            "temperature": role["temperature"],
            "messages": messages
        }
        if tools:
            kwargs["tools"] = tools

        resp = client.chat.completions.create(**kwargs)
        duration_ms = int((time.time() - t0) * 1000)

        msg = resp.choices[0].message
        usage = resp.usage
        cost = getattr(usage, "cost_details", None) or {}
        status = StepStatus.OK if usage else StepStatus.ERROR
        if msg.content == "":
            status = StepStatus.EMPTY
        tool_calls = msg.tool_calls or []

        log_step(
            run_id=run_id,
            step=RunStep.PLANNER,
            turn=turn,
            role=role["name"],
            model=role["model"],
            temperature=role["temperature"],
            input_summary=spec[:500],
            output=msg.content or "",
            completion_tokens=usage.completion_tokens if usage else None,
            prompt_tokens=usage.prompt_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            upstream_inference_cost=cost["upstream_inference_cost"] if cost else None,
            upstream_inference_completions_cost=cost["upstream_inference_completions_cost"] if cost else None,
            upstream_inference_prompt_cost=cost["upstream_inference_prompt_cost"] if cost else None,
            duration_ms=duration_ms,
            finish_reason=resp.choices[0].finish_reason,
            model_served=resp.model,
            status=status,
            tool_calls=[
                {"name": tc.function.name, "args": tc.function.arguments,
                 "result_preview": None}  # filled below
                for tc in tool_calls
            ],
        )

        if not tool_calls:
            final_text = msg.content or ""
            break
            # Append the assistant message with tool_calls, then each tool result.
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            result = dispatch_tool_call(tc)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:2000],  # cap what goes back into context
            })

    return final_text
