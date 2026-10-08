"""Scripted models: test your loop without spending a token.

NeverStops asks for a tool on every call and never ends its turn, so the only
thing that can stop a run is your loop's bounds. The Assignment 1 checker runs your
loop against it. You can too:

    python run.py --way agent --backend never-stops --set dev --runs 1

Token counts from scripted models are estimates: one token per four characters
of the request's JSON. They are not the real model's counts, which is fine for
testing bounds and not fine for anything you report.
"""

from __future__ import annotations

import json
import math
import time

from harness.client import Usage

# NeverStops' output per call, in estimated tokens (its tool call).
NEVER_STOPS_OUTPUT_TOKENS = 30

# The stub tool result the checker gives NeverStops: 1,600 characters.
STUB_RESULT = ("stub result " * 134)[:1600]


def estimate_tokens(obj) -> int:
    return math.ceil(len(json.dumps(obj, sort_keys=True, default=str)) / 4)


def _input_for(tool: dict) -> dict:
    props = (tool.get("input_schema") or {}).get("properties", {})
    if "query" in props:
        return {"query": "export"}
    if "number" in props:
        return {"number": 4191}
    return {}


class NeverStops:
    """Always calls the first tool it is offered. Optional delay per call, in seconds."""

    name = "never-stops"

    def __init__(self, settings=None, delay_s: float = 0.0):
        self.delay_s = delay_s
        self.calls = 0

    def create(self, *, system, messages, tools):
        if self.delay_s:
            time.sleep(self.delay_s)
        self.calls += 1
        prompt = estimate_tokens({"system": system, "tools": tools, "messages": messages})
        if tools:
            block = {"type": "tool_use", "id": f"toolu_scripted_{self.calls:04d}",
                     "name": tools[0]["name"], "input": _input_for(tools[0])}
            return [block], "tool_use", "never-stops", Usage(prompt, NEVER_STOPS_OUTPUT_TOKENS)
        # Offered no tools, it has nothing to ask for and says so.
        return ([{"type": "text", "text": "I would call a tool, but none was offered."}],
                "end_turn", "never-stops", Usage(prompt, NEVER_STOPS_OUTPUT_TOKENS))
