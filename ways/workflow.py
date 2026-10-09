"""Way 2, the workflow. Your code decides every step, in advance, in this order:

    read_issue  ->  one call to extract search terms  ->  search_repo
                ->  one call to choose the label and the file  ->  post_comment

A fixed sequence, no loop: the model never chooses a tool. Trace every model
call (ctx.trace.model_call); call every tool through ctx.call_tool(step, name,
input), which traces it. Keep your prompts in prompts/.

Part D reuses this way: its first half (read, extract, search) and its second
half (choose, post) are easier to reuse as two functions.
"""

from harness.formats import format_triage_comment, parse_triage_comment

MAX_TERMS = 3


def gather(ctx) -> tuple[str, str]:
    """First half: read the issue, ask for search terms (step 1), search for each.
    Returns the issue text and the combined search results."""
    issue = ctx.call_tool(0, "read_issue", {"number": ctx.issue_number}).content

    prompt = ctx.prompt("workflow_extract.md").replace("{issue}", issue)
    response = ctx.client.create(messages=[{"role": "user", "content": prompt}])
    ctx.trace.model_call(1, response)

    terms = [line.strip(" -*`'\"") for line in response.text.splitlines()]
    terms = [t for t in terms if t][:MAX_TERMS]
    results = []
    for term in terms:
        result = ctx.call_tool(1, "search_repo", {"query": term})
        results.append(f'search "{term}":\n{result.content}')
    return issue, "\n\n".join(results) or "No searches were run."


def choose(ctx, issue: str, search_results: str) -> tuple[str | None, str | None]:
    """Second half, part one: ask for the label and the file (step 2). Returns them parsed."""
    prompt = (ctx.prompt("workflow_choose.md")
              .replace("{search_results}", search_results)
              .replace("{issue}", issue))
    response = ctx.client.create(messages=[{"role": "user", "content": prompt}])
    ctx.trace.model_call(2, response)
    return parse_triage_comment(response.text)


def run(ctx) -> None:
    issue, search_results = gather(ctx)
    label, file = choose(ctx, issue, search_results)
    # An unparseable answer is still posted, so it is judged a failure rather than lost
    body = format_triage_comment(label or "unknown", file)
    ctx.call_tool(2, "post_comment", {"number": ctx.issue_number, "body": body})
