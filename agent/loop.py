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

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Bounds:
    max_steps: int        # model calls per run
    max_tokens: int       # prompt plus output tokens per run, from client.total_tokens
    wall_clock_s: float   # seconds per run


def load_bounds(path: Path | str = Path(__file__).parent / "bounds.yaml") -> Bounds:
    data = yaml.safe_load(Path(path).read_text())
    return Bounds(int(data["max_steps"]), int(data["max_tokens"]), float(data["wall_clock_s"]))


def run_loop(client, tools, system: str, user_message: str, bounds: Bounds, trace) -> str:
    raise NotImplementedError("Assignment 1 Part A: write the loop")
