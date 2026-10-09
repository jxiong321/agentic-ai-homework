"""Way 1, the direct call. Nobody decides the next step: there is one step.

Read the issue (ctx.call_tool(0, "read_issue", {"number": ctx.issue_number})),
make ONE model call that gets the issue plus ctx.repo_summary and no tools, turn
its answer into a comment with harness.formats.format_triage_comment, and post it
with ctx.call_tool(1, "post_comment", ...). Your code posts the comment, not the
model.

Trace every model call (ctx.trace.model_call(step, response)). ctx.call_tool
calls a tool and traces it in one go; its step is the model call it belongs to,
0 before the first.
Keep your prompt in prompts/ and load it with ctx.prompt("direct.md").
"""

from harness.formats import format_triage_comment, parse_triage_comment


def run(ctx) -> None:
    issue = ctx.call_tool(0, "read_issue", {"number": ctx.issue_number}).content

    prompt = (ctx.prompt("direct.md")
              .replace("{repo_summary}", ctx.repo_summary)
              .replace("{issue}", issue))
    response = ctx.client.create(messages=[{"role": "user", "content": prompt}])
    ctx.trace.model_call(1, response)

    # An unparseable answer is still posted, so it is judged a failure rather than lost
    label, file = parse_triage_comment(response.text)
    body = format_triage_comment(label or "unknown", file)
    ctx.call_tool(1, "post_comment", {"number": ctx.issue_number, "body": body})
