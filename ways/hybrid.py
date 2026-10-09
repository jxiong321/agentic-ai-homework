"""Way 4, the hybrid. The workflow answers first; the agent takes over only when the
workflow's answer cannot be right.

Hand-off rule (R4): the workflow chose a file that does not exist in the repository.
`file: none` never hands off. The rule reads only what the run produced (the chosen
path) and the repository itself, never the issue number or the known answers.

The decision is made before anything is posted, so a run posts the workflow's
comment or hands off, never both. On a hand-off the agent starts fresh, exactly as
ways/agent.py runs it (its steps restart at 1), without the workflow's search
results, so it is not anchored to the workflow's mistake.
"""

from dataclasses import replace

from harness.formats import format_triage_comment
from tools import ToolResult
from ways import agent
from ways.workflow import choose, gather


class OneComment:
    """Wraps a tool registry so a run can post at most one comment."""

    def __init__(self, tools):
        self._tools = tools
        self.schemas = tools.schemas
        self.posted = False

    def call(self, name, tool_input):
        if name == "post_comment" and self.posted:
            return ToolResult("Error: a comment has already been posted on this issue in this run.", True, 0.0)
        result = self._tools.call(name, tool_input)
        if name == "post_comment" and not result.is_error:
            self.posted = True
        return result


def file_missing(ctx, file) -> bool:
    """R4: the workflow named a path that is not a file inside the repository."""
    if file in (None, "none"):
        return False
    repo = (ctx.root / "fixtures" / "repo").resolve()
    path = (repo / file).resolve()
    return not (path.is_relative_to(repo) and path.is_file())


def run(ctx) -> None:
    ctx = replace(ctx, tools=OneComment(ctx.tools))
    issue, search_results = gather(ctx)
    label, file = choose(ctx, issue, search_results)
    if file_missing(ctx, file):
        agent.run(ctx)  # the loop writes trace.end, which is how hand-offs are counted
        return
    body = format_triage_comment(label or "unknown", file)
    ctx.call_tool(2, "post_comment", {"number": ctx.issue_number, "body": body})
