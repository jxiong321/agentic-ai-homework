"""Assignment 1, Part A: the smallest tool-using loop you can write. This file is yours.

The contract (checks/FORMATS.md, section 3). The checker calls run_loop
directly, with a scripted model that never stops, a stub tool registry and its
own bounds, so keep this exact signature:

    run_loop(client, tools, system, user_message, bounds, trace) -> str

    client        harness.client.ModelClient: client.create(system=, messages=, tools=)
                  returns a ModelResponse; client.total_tokens is this run's running total
    tools         a registry: tools.schemas (definitions), tools.call(name, input) -> ToolResult
    system        the system prompt, a string
    user_message  the first user turn, a string
    bounds        a Bounds (below): max_steps, max_tokens, wall_clock_s
    trace         harness.trace.TraceWriter
    returns       the model's last text, possibly empty

Your loop must:
  1. Enforce all three bounds itself, in code, before each model call.
  2. Call trace.model_call(step, response) after every model call and
     trace.tool_call(step, call, result) after every tool call. Steps count from 1.
  3. Call trace.end(reason) exactly once, with the harness's reason for stopping:
     model_stopped, turn_limit, token_budget, wall_clock, tool_error or refusal.
     The model never reports its own ending.
  4. Append each assistant turn unchanged (response.assistant_message()) and send
     all of a step's tool results back in one user turn (harness.client.tool_result).

"turn_limit" means the loop made exactly max_steps model calls. "token_budget"
means client.total_tokens had reached bounds.max_tokens when the loop checked,
before its next call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from harness.client import tool_result


@dataclass(frozen=True)
class Bounds:
    max_steps: int        # model calls per run
    max_tokens: int       # prompt plus output tokens per run, from client.total_tokens
    wall_clock_s: float   # seconds per run


def load_bounds(path: Path | str = Path(__file__).parent / "bounds.yaml") -> Bounds:
    data = yaml.safe_load(Path(path).read_text())
    return Bounds(int(data["max_steps"]), int(data["max_tokens"]), float(data["wall_clock_s"]))


def run_loop(client, tools, system: str, user_message: str, bounds: Bounds, trace) -> str:
    start = time.monotonic()
    messages = [{"role": "user", "content": user_message}]
    last_text = ""
    step = 0

    while True:
        # The bounds are checked here, in code, before every model call
        elapsed = time.monotonic() - start
        if step >= bounds.max_steps:
            trace.end("turn_limit", f"{step} model calls")
            return last_text
        if client.total_tokens >= bounds.max_tokens:
            trace.end("token_budget", f"{client.total_tokens} >= {bounds.max_tokens} tokens")
            return last_text
        if elapsed >= bounds.wall_clock_s:
            trace.end("wall_clock", f"{elapsed:.1f}s >= {bounds.wall_clock_s}s")
            return last_text

        step += 1
        response = client.create(system=system, messages=messages, tools=tools.schemas)
        trace.model_call(step, response)
        messages.append(response.assistant_message())
        if response.text:
            last_text = response.text

        if response.stop_reason == "refusal":
            trace.end("refusal", f"step {step}")
            return last_text
        calls = response.tool_calls
        if not calls:
            trace.end("model_stopped", f"stop_reason {response.stop_reason}")
            return last_text

        # Run every tool the model asked for this step; send the results back as one user turn.
        # An is_error result goes back to the model to recover from; a tool that raises ends the run.
        results = []
        for call in calls:
            try:
                result = tools.call(call.name, call.input)
            except Exception as exc:
                trace.end("tool_error", f"{call.name} raised {type(exc).__name__}: {exc}")
                return last_text
            trace.tool_call(step, call, result)
            results.append(tool_result(call, result.content, result.is_error))
        messages.append({"role": "user", "content": results})
