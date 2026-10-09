# Assignment 1 report · Four ways to triage an issue

Every number here also goes in `reports/LAB_01.json`, which the checker reads
(format: `checks/FORMATS.md`, section 7). Give each number its run count. Mark
any vendor figure you cite with its source type and date.

## Part 0 · The recorded trace
Measured by `eval/part0.py` on `fixtures/week01_recorded_run.jsonl` (one recorded run).

| Measure | Value |
|---|---|
| Model calls (distinct `message.id`) | 21 |
| Tool calls (distinct `tool_use` ids) | 23 |
| Prompt tokens (input + cache read + cache write, summed over calls) | 399,123 |
| Cache-read tokens | 388,338 |
| Cache-read share | 0.973 |
| First prompt | 13,445 |
| Last prompt | 24,188 |
| Cumulative over first | 29.69 |

The growth means that as the agent accumulates conversation history and tool results, each model call requires a larger prompt (since it has to read all of the previous context) which causes the cumulative token usage to grow faster than linearly (29x first vs. 21x first).

## Part A · Your loop's bounds
Your three bounds and why. Your worst case: *F*, *A*, *N*, and the cumulative
prompt tokens at your turn limit.

### Worst case: estimate, before any run
Estimated offline from `prompts/agent_system.md`, the three tool definitions, and
the tools run locally on the two dev issues (4191, 4192), at ~4 characters per token
(the same rule as `harness/scripted.py`). No model was called.

- *F* (system prompt ~254 tok + tool definitions ~190 tok + first user message):
  472 estimated, rounded up to **F ≈ 500** for tokenizer differences.
- *A* (one step's tool call plus its result): a `read_issue` step adds ~127 tokens,
  a `search_repo` step ~165 on average (~285 with a full 10-hit result), a
  `post_comment` step ~113. A typical read → search → search → post path averages
  ~143; rounded up to **A ≈ 200** to cover fuller search results and any text the
  model writes alongside its tool calls.
- *N* = `max_steps` = **8**.
- Cumulative prompt tokens at the turn limit: 8 × 500 + 200 × 8 × 7 / 2 =
  4,000 + 5,600 = **9,600**.

At an assumed ≤ 500 output tokens per call (≤ 4,000 over 8 calls), a run that hits
the turn limit spends about 13,600 tokens, under half of the 30,000 token budget.

### Worst case: measured, after Part B
To be replaced with *F* and *A* measured on the 60 evaluation agent runs
(`checks/FORMATS.md`, section 4); these go in `reports/LAB_01.json` `worst_case`.

## Part B · Results
The table for all three ways: passes out of 60, per issue out of 10, the spread
(lowest and highest sweep), issues solved in every run, tokens, p50 and p95
latency, cost, tool calls.

**Excluded runs.** 12 agent runs (sweeps 9 and 10, all six issues) crashed on Gemini
billing errors, one `429` quota error and eleven `402` "prepayment credits depleted",
before producing any answer: 11 made no model call, one made two, and none posted a
comment. They measure the account, not the agent, so their traces were moved to
`runs/excluded_billing_errors/` (kept as evidence, not read by the checker) and sweeps
9 and 10 were rerun on 2026-10-09 after billing was restored, with unchanged code and
settings.

## Part C · The decision
1. Find the diamond, for each way.
2. Your multipliers, and two differences from the vendor's 4×.
3. *f*, the blended cost, and the comparison with all-agent and all-workflow;
   then the slide's version, with *c*, *m* and *f* against the direct call.
4. Path entropy.
5. The four gates, one line of evidence each, and your verdict: agent,
   workflow or hybrid. If hybrid, where the line sits.
6. Your predictions: each one in `reports/PREDICTIONS_01.md` that missed, what
   you believed, and which trace shows why it was wrong.
7. The seven-layer audit: how many layers are empty (`ARCHITECTURE.md`).

### 1. Find the diamond

**Direct Call:** The direct call is a script because Python controls the entire sequence of actions. After Gemini generates its answer, Python automatically posts the comment. Gemini does not decide what happens next or when the process ends. There is no human approval required.

**Workflow:** The workflow is also controlled by Python. Although Gemini chooses what search terms to use, Python determines when the search happens and what happens afterward. In other words, Python gives Gemini the ability to choose what to search for, but not whether to search. Python also determines when the workflow ends. There is no human approval required.

**Bounded Agent:** The agent is different because Gemini decides which tools to use and what actions to take next. However, it is still bounded by Python, which enforces limits on model calls, tokens, and execution time. Both Gemini and Python can end the run: Gemini decides when it believes it has completed the task, but Python terminates the run if a limit is reached. There is no human approval required.

### 3. *f* and the blended cost
*f* is the share of the six evaluation issues where the workflow passes fewer than 5
of 10 runs and the agent 5 or more. The workflow falls below 5 on 4202 (2/10), 4204
(0/10) and 4206 (0/10), but the agent passes none of those three (0/10 each), so
**f = 0/6 = 0**. With *c* = $0.000317 (the workflow's mean cost per run, 60 runs) and
*m* = 6.68 (the agent's $0.002117 over *c*, 60 runs each):

- blended cost = *c* × [(1 − *f*) + *f* × *m*] = *c* = **$0.000317**, equal to the workflow cost;
- all-agent cost = *c* × *m* = **$0.002117**;
- all-workflow cost = *c* = **$0.000317**.

Under the assignment's threshold there is no issue the agent rescues, so the
theoretical blend routes nothing to the agent and costs exactly what the workflow
does. The agent's one clear advantage, 4203 (9/10 against the workflow's 6/10), falls
below the threshold because the workflow already passes it more than half the time.

## Part D · The hybrid
Your hand-off rule, and the Part B traces that led you to it (written before you
measure). Its row beside the three ways (the same columns as Part B's table), how many of
its runs handed the issue to the agent, and its measured cost per run beside your
blended cost from Part C, item 3. Does it change your Part C verdict? Which of
the four would you ship, and why?

### Hand-off rule (written before any hybrid run)
**Rule (R4):** run the workflow; if the file it chose does not exist in the
repository, discard its answer and hand the issue to the agent, starting fresh.
Otherwise post the workflow's answer. `file: none` never hands off, so questions
stay in the workflow. The rule reads only the chosen path and the repository, never
the issue number or the known answers. Implemented in `ways/hybrid.py`; the decision
is made before anything is posted, and a run can post at most one comment.

**Why this rule.** A file that does not exist is a clear indicator of an incorrect
answer. In the 60 workflow evaluation runs it fires on 7 failing runs and on none of
the 28 passing runs. It misses the other failures, but it is a relatively inexpensive
way to target cases where agent intervention might help. The agent starts fresh
rather than inheriting the workflow's search results, to avoid anchoring it to the
workflow's mistake.

**The Part B traces that led to it.** The workflow posted four paths that do not
exist: `src/export/` and `src/exporters/index.js` on 4202 (4 runs), and
`src/parser.js` and `src/import/parser.py` on 4203 (3 runs), where broad or overly
literal search terms left the right file out of the results and the model invented a
plausible path. Candidate rules, scored on the same 60 workflow runs:

| Candidate rule | Fires on passing runs | Fires on failing runs |
|---|---|---|
| Every search returned no matches | 0 / 28 | 3 / 32 |
| Any search returned no matches | 22 / 28 | 21 / 32 |
| Chosen file not in the search results | 6 / 28 | 22 / 32 |
| `file: none` with a label other than question | 0 / 28 | 0 / 32 |
| Chosen file named in the issue text | 0 / 28 | 10 / 32 |
| **Chosen file does not exist (R4, chosen)** | **0 / 28** | **7 / 32** |

**Expectation.** A hand-off only helps where the agent beats the workflow. In its 60
evaluation runs the agent also failed 4202, 4204 and 4206 (0/10 each) and passed 4203
in 9 of 10. Applying those rates to the hand-offs R4 would have made on the Part B
workflow runs (4 on 4202, 3 on 4203), R4 should lift the workflow's 28/60 to about
30.7/60, with roughly 7 of 60 runs handed off, at a mean cost of about $0.00056 per run
against the workflow's $0.00032. Most workflow failures (4204, 4206) choose a wrong
file that exists, which R4 does not catch.

## Assistance
Which AI tool, what it wrote, what you checked.

**Tool:** Claude Code (Claude Opus 5.5), used as a coding assistant and tutor. The
prompts and conversation are retained.

**What it wrote:** `eval/part0.py` (implementing my algorithm), `run_loop` in
`agent/loop.py`, `ways/agent.py`, `ways/direct.py`, `ways/workflow.py`,
`ways/hybrid.py`, `eval/check_triage.py`, `eval/summarize.py`, the prompts in
`prompts/`, and first drafts of the Part 0 table, the Part A worst-case estimate, the
Part D trace evidence and expected outcome (the rationale for the rule is mine), and
the `CHANGES.md` entry. It also scored candidate hand-off rules against the Part B
traces.

**What I decided and checked:** I made the architectural decisions: the Part 0
algorithm, the three bounds, the predictions, the hand-off rule (R4) and starting the
agent fresh on a hand-off. I wrote the Part 0 interpretation, Part C item 1 and the
seven-layer audit in `ARCHITECTURE.md`. I reviewed the code, and validated it with
`make test`, `make bounds-smoke`, `make check-01`, offline tests against scripted and
synthetic models, and runs on the two development issues before any evaluation run.
