"""Way 2, the workflow. Your code decides every step, in advance, in this order:

    read_issue  ->  one call to extract search terms  ->  search_repo
                ->  one call to choose the label and the file  ->  post_comment

A fixed sequence, no loop: the model never chooses a tool. Trace every model
call (ctx.trace.model_call); call every tool through ctx.call_tool(step, name,
input), which traces it. Keep your prompts in prompts/.

Part D reuses this way: its first half (read, extract, search) and its second
half (choose, post) are easier to reuse as two functions.
"""


def run(ctx) -> None:
    raise NotImplementedError("Assignment 1 Part B: the workflow")
