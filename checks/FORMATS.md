# FORMATS.md · what the checkers read

Every format a checker parses is defined here and nowhere else. If an assignment's
handout and this file ever disagree, this file wins; tell your instructor.

## 1. The task, and the comment it produces

RepoMind reads an issue, finds the file most responsible, and posts **one**
comment whose first two lines are:

```
label: <bug | feature | question | docs>
file: <path relative to fixtures/repo, or none>
```

| Label | When | The file is |
|---|---|---|
| `bug` | something that should work does not | the file whose code is wrong |
| `feature` | a request for new behaviour | the file where the change would mainly go |
| `question` | the reporter asks how something works; nothing needs to change | `none` |
| `docs` | the documentation is wrong or missing | the document to fix |

Keys are case-insensitive; anything after the two lines is free text. The path is
read by `harness.formats.parse_triage_comment`: backticks, quotes and a leading
`./` or `fixtures/repo/` are ignored. Where your code posts the comment (the
direct call and the workflow), build it with `harness.formats.format_triage_comment`;
where the model posts it (the agent), the prompt must ask for exactly these two
lines. Read comments with `parse_triage_comment`, and you and the checker will
always agree on what a comment says.

Known answers are in `fixtures/answers.yaml`: six evaluation issues (4201 to
4206) and two development issues (4191, 4192).

## 2. The trace: `runs/<run_id>.jsonl`

One JSON object per line. Every line carries `run_id`, `type`, and `t` (seconds
since the run started). The runner writes the first and last lines; your code
writes the rest through `harness.trace.TraceWriter`.

| `type` | Written by | Fields |
|---|---|---|
| `run_start` | runner | `lab`, `way`, `issue`, `sweep`, `backend`, `model`, `settings` (hash), `price_sheet` (read date), `started` |
| `model_call` | you: `trace.model_call(step, response)` | `step`, `model` (the model that served it), `stop_reason`, `latency_s`, `usage` {`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `prompt_tokens`}, `cost_usd`, `tool_calls` [{`name`, `input`}], `text` |
| `tool_call` | you: `trace.tool_call(step, call, result)` in the loop, or `ctx.call_tool(step, name, input)` from your own code, which calls the tool and traces it | `step`, `name`, `input`, `is_error`, `latency_s`, `result_chars`, `result_excerpt` |
| `end` | you, in the loop: `trace.end(reason, detail)`; the runner writes one if you did not | `terminal_reason`, `detail` |
| `run_end` | runner | `elapsed_s`, `totals` {`model_calls`, `prompt_tokens`, `output_tokens`, `cache_read_tokens`, `total_tokens`, `cost_usd`, `unpriced_calls`, `models`}, `error` |

`prompt_tokens` is everything the model read on that call: uncached input plus
cache reads plus cache writes. `run_end.totals` comes from the metered client,
not from your trace, so a model call you forgot to trace shows up as a gap
between the two.

A **step** number is the model call a record belongs to: a tool call carries the
step of the most recent model call, or 0 before the first. In Part D's hybrid the agent's steps
restart at 1 when it takes over; nothing reads step numbers across a hand-off.

**Terminal reasons** (`harness.formats.TERMINAL_REASONS`): `model_stopped`,
`turn_limit`, `token_budget`, `wall_clock`, `tool_error`, `refusal`; `completed`,
written by the runner for a run no loop ended (the direct call, the workflow, and
a hybrid run that stayed in the workflow); and `crashed`, written by the runner
when your way raised (the error is in `run_end.error`). A hybrid run that reached
the agent ends with your loop's reason, which is how you count hand-offs.

## 3. The loop contract

```python
run_loop(client, tools, system, user_message, bounds, trace) -> str   # agent/loop.py
```

- `client`: `harness.client.ModelClient`. `client.create(system=, messages=, tools=)`
  returns a `ModelResponse` with `.content` (append it unchanged), `.stop_reason`,
  `.tool_calls` (each has `.id`, `.name`, `.input`), `.text`, `.usage`,
  `.assistant_message()`. `client.total_tokens` is the run's running total.
- `tools`: anything with `.schemas` (a list of tool definitions) and
  `.call(name, input)`, which returns a `ToolResult` with `.content`, `.is_error`
  and `.latency_s`. The checker passes its own stub here.
- `bounds`: `agent.loop.Bounds(max_steps, max_tokens, wall_clock_s)`, loaded from
  `agent/bounds.yaml`. The checker passes its own bounds too.
- Tool results go back as one user turn of `harness.client.tool_result(call,
  content, is_error)` blocks.
- These formats are the same whatever your model's vendor: the backend
  translates them for its API.

What the checker asserts:

- **turn limit**: exactly `max_steps` `model_call` lines, then one `end` with
  `turn_limit`;
- **token budget**: one `end` with `token_budget`, and at most one call after
  `client.total_tokens` reached the budget;
- **wall clock**: one `end` with `wall_clock`, and the loop returns within one
  call of the limit.

A **step** is one model call. (Week 12 uses "turn" for everything between two
user messages; the course calls that an episode.)

## 4. The scripted model, and the published A

`harness.scripted.NeverStops` asks for its first offered tool on every call and
never ends its turn. Its token counts are estimates, one token per four
characters of the request's JSON. For the bounds check the checker gives it one
stub tool returning a fixed 1,600-character result.

With that stub, each step appends **A = 463** tokens (its tool call plus the
result, as the estimate counts them). The checker measures *F* as the prompt
tokens of the first call in its own run, and requires your cumulative prompt
tokens at the turn limit to be at most

```
(N × F + A × N × (N − 1) / 2) × 1.15
```

The 15% absorbs differences in how you wrap tool results.

For your report, *F* and *A* are your own. In Part A, before any run, estimate them
from your prompt and tool definitions. After Part B, replace the estimate with
values measured on your 60 evaluation agent runs: *F* is the mean, over those
runs, of the first call's `prompt_tokens`; *A* is the mean, over every pair of
consecutive calls in those runs, of the increase in `prompt_tokens`. The checker
checks only that your `cumulative_prompt_tokens` is the formula applied to your
own `F`, `A` and `N`, with `N` your `max_steps`.

## 5. The tracker: `tracker/comments.jsonl`

One comment per line: `id`, `run_id`, `issue`, `body`, `posted_at`. The
`run_id` is stamped by the harness from the run that posted it; the model never
sees or sets it. The model also never sees comments: `read_issue` returns the
issue alone. `make reset` archives the file to `tracker/archive/` and starts
empty; the runner never deletes comments, so every run stays checkable.

## 6. The grounded check

```python
check(tracker, run_id, issue_number, answer) -> bool   # eval/check_triage.py
```

`answer` is `{"label": ..., "file": ...}` from `fixtures/answers.yaml`. The
checker calls your function on planted runs: a wrong comment whose run claims
success must return `False`; a right comment from a run that said nothing must
return `True`; a run with no comment must return `False`.

The checker's own rule, which your table must match: **a run passes when exactly
one comment carries its `run_id` on its issue, and that comment's label and file
both match the answer.**

## 7. `reports/LAB_01.json`

The template in `reports/` has every field. `results` has one entry per way:
`direct`, `workflow`, `agent` and `hybrid` (Part D). The checker compares these
exactly (counts) or within 1% (means):

| Field (per way, under `results`) | Definition |
|---|---|
| `runs` | finished runs of that way on the six evaluation issues (a run with a `run_end` line), excluding the scripted backend |
| `passes` | runs that pass by section 6's rule |
| `per_issue` | passes per issue, keyed by issue number as a string |
| `sweep_min`, `sweep_max` | passes within one sweep (one run per issue, grouped by `run_start.sweep`), lowest and highest over all sweeps |
| `all_ten` | a count (an integer, not a list): the number of issues with at least 10 runs, every one of which passed |
| `mean_prompt_tokens`, `mean_output_tokens` | mean over runs of the run's summed `model_call.usage` field |
| `mean_cost_usd` | mean over runs of the run's summed `model_call.cost_usd`, an unpriced call counting 0 |

Read by staff, not compared by the checker:

| Field | Definition |
|---|---|
| `mean_cached_tokens` | mean over runs of the run's summed `usage.cache_read_input_tokens`. Uncached prompt tokens are `mean_prompt_tokens` minus this. Nothing in the starter sets a cache breakpoint, so expect 0 |
| `p50_latency_s`, `p95_latency_s` | nearest-rank percentiles of `run_end.elapsed_s`, which includes any wait your vendor's rate limit imposed |
| `mean_tool_calls`, `max_tool_calls` | over runs, the number of `tool_call` records: every tool call, your code's and the model's |

Also required:

- `part0`: `model_calls` (distinct `message.id` values), `tool_calls`
  (`tool_use` blocks), `prompt_tokens` (input plus cache read plus cache write,
  summed over calls), `cache_read_tokens`, `cache_read_share`, `first_prompt`,
  `last_prompt`, `cumulative_over_first`. The checker recomputes six of them,
  `model_calls`, `tool_calls`, `prompt_tokens`, `cache_read_tokens`,
  `first_prompt` and `last_prompt`, from `fixtures/week01_recorded_run.jsonl`,
  each within 1%; staff read the two ratios.
- `worst_case` {`F`, `A`, `N`, `cumulative_prompt_tokens`}, where `N` is your
  `max_steps` and `cumulative_prompt_tokens` is `N·F + A·N(N−1)/2`.

`analysis`, read by staff alongside `reports/LAB_01.md`:

| Field | Definition |
|---|---|
| `ratio_agent_over_direct_tokens` | the agent's mean prompt plus output tokens per run, over the direct call's |
| `m_agent_over_workflow_cost` | *m*: the agent's `mean_cost_usd` over the workflow's |
| `f` | the share of the six evaluation issues where the workflow passes fewer than 5 of 10 runs and the agent 5 or more, a fraction between 0 and 1 |
| `blended_cost`, `all_agent_cost`, `workflow_cost` | *c* × [(1 − *f*) + *f* × *m*], *c* × *m*, and *c*, with *c* the workflow's `mean_cost_usd` |
| `path_entropy` | over the agent's evaluation runs, each run's tool names in order: `distinct_sequences`, the number of different sequences, and `top3_share`, the fraction of runs the three most common cover |
| `verdict` | `agent`, `workflow` or `hybrid`: your final verdict, after Part D |
| `hybrid_handoffs` | the number of hybrid runs that reached the agent (section 2) |

`part0.cache_read_share` and `part0.cumulative_over_first` are fractions and
ratios as plain numbers (0.973, not 97.3%).

## 8. `ARCHITECTURE.md` references

A reference is a file path and a line number joined by a colon, inside
backticks, relative to the repository root. The checker opens each one: the
file must exist, have that line, and not be under `prompts/`.

## 9. Budgets and the ledger

`settings.yaml` sets two hard ceilings the harness enforces outside your code:
`session_token_ceiling` per run (the client refuses the next call) and
`lab_token_ceiling` per lab (the runner refuses the next run). Every run appends
one line to `runs/_ledger.jsonl`: `run_id`, `way`, `issue`, `sweep`, `backend`,
`total_tokens`, `cost_usd`, `error`, `finished`. Runs on the scripted backend
are free and do not count toward the assignment's token ceiling.
