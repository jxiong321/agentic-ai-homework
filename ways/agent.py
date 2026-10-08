"""Way 3, the agent. The model decides, at runtime, what to call and when to stop.

Write this in Part A, task 5: `make bounds-smoke` runs it.

Load your bounds (agent.loop.load_bounds()), then call agent.loop.run_loop with
ctx.client, ctx.tools (all three tools), a system prompt from prompts/, and a
first user message naming the issue. The agent posts its own comment through
post_comment. Your loop writes the trace, including trace.end.
"""


def run(ctx) -> None:
    raise NotImplementedError("Assignment 1 Part A, task 5: the agent way")
