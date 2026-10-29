import json
import logging
import time

import openai

from harness.role import Role
from harness.tool_dispatcher import dispatch_tool_call
from harness.tool_schemas import ALL_TOOL_SCHEMAS
from harness.trace import log_step, StepStatus, RunStep

from dataclasses import dataclass, field

@dataclass
class ImplementationResult:
    finished: bool
    files_written: list[str]
    turns_used: int
    final_text: str

def implement(plan: str, findings: list[dict], role: Role, run_id: str, client:openai.Client, max_turns: int = 5) -> ImplementationResult:
    logging.info("Starting implementation")
    user_content = f"<plan>\n{plan}\n</plan>"
    if findings:
        user_content += (
            f"\n\n<review_findings>\n{json.dumps(findings, indent=2)}\n</review_findings>"
            "\n\nAddress each finding above. Do not rewrite code that the findings do not mention."
        )
    messages = [
        {"role": "system", "content": role.system_prompt},
        {"role": "user", "content": user_content},
    ]

    tools = ALL_TOOL_SCHEMAS
    finished = False
    files_written: list[str] = []
    turns_used = 0
    final_text = ""

    for turn in range(max_turns):
        turns_used = turn + 1
        t0 = time.time()
        kwargs = {
            "model": role.model,
            "temperature": role.temperature,
            "messages": messages
        }
        if tools:
            kwargs["tools"] = tools

        resp = client.chat.completions.create(**kwargs)
        duration_ms = int((time.time() - t0) * 1000)

        msg = resp.choices[0].message
        usage = resp.usage
        cost = getattr(usage, "cost_details", None) or {}
        tool_calls = msg.tool_calls or []
        if not msg.content and not tool_calls:
            status = StepStatus.EMPTY
        else:
            status = StepStatus.OK if usage else StepStatus.ERROR

        log_step(
            run_id=run_id,
            step=RunStep.IMPLEMENTATION,
            turn=turn,
            role=role.name,
            model=role.model,
            temperature=role.temperature,
            input_summary=plan[:500],
            output=msg.content or "",
            completion_tokens=usage.completion_tokens if usage else None,
            prompt_tokens=usage.prompt_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            upstream_inference_cost=cost.get("upstream_inference_cost"),
            upstream_inference_completions_cost=cost.get("upstream_inference_completions_cost"),
            upstream_inference_prompt_cost=cost.get("upstream_inference_prompt_cost"),
            duration_ms=duration_ms,
            finish_reason=resp.choices[0].finish_reason,
            model_served=resp.model,
            status=status,
            tool_calls=[
                {"name": tc.function.name, "args": tc.function.arguments,
                 "result_preview": None}
                for tc in tool_calls
            ],
        )

        if not tool_calls:
            logging.info("implementation done")
            final_text = msg.content or ""
            finished = True
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
            if tc.function.name == "write_file":
                try:
                    args = json.loads(tc.function.arguments)
                    path = args.get("path")
                    if path:
                        files_written.append(path)
                except (json.JSONDecodeError, AttributeError):
                    pass
            result = dispatch_tool_call(tc)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:2000],
            })
        logging.info("tool call done")

    if not finished:
        logging.warning("implementer hit max_turns=%d without finishing", max_turns)
        log_step(
            run_id=run_id,
            step=RunStep.IMPLEMENTATION,
            turn=max_turns,
            role=role.name,
            model=role.model,
            temperature=role.temperature,
            input_summary=plan[:500],
            output=f"max_turns={max_turns} exceeded; last action was a tool call, not a completion",
            status=StepStatus.RETRY,
            completion_tokens=usage.completion_tokens if usage else None,
            prompt_tokens=usage.prompt_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            upstream_inference_cost=cost.get("upstream_inference_cost"),
            upstream_inference_completions_cost=cost.get("upstream_inference_completions_cost"),
            upstream_inference_prompt_cost=cost.get("upstream_inference_prompt_cost"),
            finish_reason=resp.choices[0].finish_reason,
            model_served=resp.model,
        )

    return ImplementationResult(
        finished=finished,
        files_written=files_written,
        turns_used=turns_used,
        final_text=final_text,
    )