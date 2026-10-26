import logging
import os
import time
import uuid

from dotenv import load_dotenv
from openai import OpenAI

from harness.trace import log_step, RunStep, StepStatus

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

RUN_ID = str(uuid.uuid4())

def run_loop(spec: str, role: dict, max_turns: int = 3) -> str:
    logging.info("Starting harness loop")

    messages = [
        {"role": "system", "content": role["system_prompt"]},
        {"role": "user", "content": spec},
    ]

    final_text = ""
    for turn in range(max_turns):
        t0 = time.time()
        resp = client.chat.completions.create(
            model=role["model"],
            temperature=role["temperature"],
            messages=messages,
        )
        duration_ms = int((time.time() - t0) * 1000)

        msg = resp.choices[0].message
        usage = resp.usage
        cost = getattr(usage, "cost_details", None) or {}
        status = StepStatus.OK if usage else StepStatus.ERROR
        if msg.content == "":
            status = StepStatus.EMPTY

        log_step(
            run_id=RUN_ID,
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
            status=status
        )

        final_text = msg.content or ""
        # No tools yet → first text response is the answer. Break.
        break

    return final_text