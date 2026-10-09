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

### The three bounds and why
I chose three bounds for the agent: a maximum of 8 model calls, 30,000 total tokens, and 180 seconds of wall-clock time (`agent/bounds.yaml`).

- **8 model calls.** A successful run might take around 4 model calls: read the issue with `read_issue`, search the repository with `search_repo`, post the answer with `post_comment`, and confirm the task is finished and stop. If the first attempt doesn't work, the agent may need another try, so I allowed double the calls of one successful run.
- **30,000 tokens.** I estimated 500 tokens for the initial system prompt and tool definitions, 463 tokens of added context per step (the A that `checks/FORMATS.md` publishes for the checker's stub tool, used as a conservative value), and 8 calls, which by the worst-case formula gives 16,964 prompt tokens. With an estimated 500 output tokens per call (4,000 over 8 calls), that is 20,964 tokens in total; the budget of 30,000 sits above that estimate and well below the harness ceiling of 400,000.
- **180 seconds.** With at most 8 model calls of 5–10 seconds each, a run should take 40–80 seconds, but the free tier is slow, so I allowed 180 seconds.

The model-call limit prevents the agent from searching indefinitely without reaching a conclusion, while the token limit controls costs and excessive context accumulation. The wall-clock limit prevents slow or stalled executions from continuing indefinitely. Together, these bounds make the agent's resource consumption more predictable, even when it fails to complete the task.

In `make bounds-smoke` (the scripted NeverStops model on both dev issues), every run ended on `turn_limit` after 8 model calls, having spent 7,556 tokens, so the step limit binds before the 30,000-token budget.

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
Measured by `eval/summarize.py` on the 60 agent evaluation runs, as defined in
`checks/FORMATS.md`, section 4 (also in `reports/LAB_01.json` `worst_case`):

- *F* = **441.0** tokens: the mean, over the 60 runs, of the first call's prompt tokens.
- *A* = **164.1** tokens: the mean increase in prompt tokens over all 323 pairs of
  consecutive calls.
- *N* = `max_steps` = **8**.
- Cumulative prompt tokens at the turn limit: 8 × 441.0 + 164.1 × 8 × 7 / 2 =
  3,528 + 4,595 = **8,123**.

Both measured values sit below the estimate (*F* ≈ 500, *A* ≈ 200, 9,600 cumulative),
so the measured worst case is about 15% lower. No agent run ended on `token_budget`:
the turn limit and the wall clock were the bounds that stopped runs.

## Part B · Results
The table for all three ways: passes out of 60, per issue out of 10, the spread
(lowest and highest sweep), issues solved in every run, tokens, p50 and p95
latency, cost, tool calls.

60 evaluation runs per way (10 sweeps × 6 issues), Gemini 3.5 Flash-Lite, computed by
`eval/summarize.py` from the traces and the tracker. Cached tokens were 0 for every way,
so all prompt tokens are uncached. Costs are priced from the `gemini-3.5-flash-lite` line
in `pricing.yaml`: $0.30 input, $2.50 output and $0.03 cached input per million tokens
(source: https://ai.google.dev/gemini-api/docs/pricing, read 2026-10-08). Latency includes
any wait the vendor's rate limits imposed, as the harness measures it.

| Way | Passes / 60 | Per issue (4201 · 4202 · 4203 · 4204 · 4205 · 4206), of 10 | Sweep min–max | Issues passed in all 10 | Mean prompt tokens | Mean output tokens | p50 latency (s) | p95 latency (s) | Mean cost / run | Tool calls mean (max) |
|---|---|---|---|---|---|---|---|---|---|---|
| Direct | 30/60 | 0 · 10 · 10 · 0 · 10 · 0 | 3–3 | 3 | 1,114 | 12.0 | 0.64 | 33.26 | $0.000364 | 2.00 (2) |
| Workflow | 28/60 | 10 · 2 · 6 · 0 · 10 · 0 | 2–4 | 2 | 889 | 20.1 | 1.20 | 59.89 | $0.000317 | 4.78 (5) |
| Agent | 28/60 | 10 · 0 · 9 · 0 · 9 · 0 | 2–3 | 1 | 5,874 | 142.0 | 4.71 | 107.52 | $0.002117 | 5.83 (8) |

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

### 2. Your multipliers

Our agent used an average of 6,016.4 tokens per run, compared with 1,125.7 tokens per run for the direct call. This gives a token multiplier of 5.34×, which is higher than Anthropic's reported ≈4× (Anthropic-reported, one team, its own workload, 2025; cited in the Week 1 lecture, slide 30).

There are three important methodological differences between our experiment and Anthropic's measurement:

1. Different models: Anthropic measured its own models, whereas we used Gemini 3.5 Flash-Lite. Different models may require different amounts of reasoning and tool use to complete similar tasks.

2. Different workloads: Anthropic's measurement reflected its own agent and chat usage, involving potentially different types and complexities of tasks. Our experiment focused specifically on six software issue-triage tasks, each repeated ten times. The complexity of these tasks may influence how many model calls and tokens an agent needs.

3. Different baselines: slide 30 compares agents with chat interactions, whereas we compare with a single direct call that receives the issue and a fixed repository summary, with no tools.

Therefore, our higher multiplier does not necessarily mean our agent is less efficient. The two measurements were obtained under different experimental conditions.

Finally, our agent had a mean cost of $0.002117 per run, compared with $0.000317 per run for the workflow.

m = $0.002117 / $0.000317 = 6.68×

Thus, our agent costs approximately 6.68 times as much as our workflow. We will use m = 6.68 in Question 3.

### 3. Where the agent earns it

The assignment defines f as the proportion of issues where the workflow succeeds fewer than 5/10 times, but the agent succeeds at least 5/10 times. None of our six issues meet both conditions, so f = 0. Although the agent outperformed the workflow on issue 4203 (9/10 versus 6/10), the workflow's success rate was still above the threshold.

Using the workflow as our baseline, with c = $0.000317 and m = 6.68, our theoretical blended cost is:

c × [(1 − f) + fm]
= 0.000317 × [(1 − 0) + 0(6.68)]
= $0.000317 per run

This equals the workflow's cost, compared with $0.002117 for running the agent on every issue. Moreover, both architectures achieved 28/60 successes. The agent costs an additional $0.001800 per run without producing any additional correct triages overall, so its incremental cost per additional success is undefined.

Using the lecture's original direct-call baseline, we instead obtain:

c = $0.000364
m = $0.002117 / $0.000364 = 5.82
f = 1/6

Blended cost = 0.000364 × [(5/6) + (1/6)(5.82)]
≈ $0.000656 per run

Here, f = 1/6 because issue 4201 meets both conditions: the direct call succeeds 0/10 times, while the agent succeeds 10/10 times.

For the fourth gate, the workflow is the more appropriate baseline, since it is the cheaper alternative we would deploy instead of the agent. Overall, the agent's additional cost does not appear justified. However, its better performance on issue 4203 motivates testing a selective hybrid in Part D.

### 4. Path entropy

Across 60 agent runs, we observed 9 distinct tool-call sequences, with the three most common accounting for 39/60 runs (65%).
All nine sequences have the same shape: read the issue, then some number of searches, then at most one post. The agent never reorders its tools; the only decision it actually varies is how many searches to run and when to stop.
The most common sequence, occurring in 20 runs, involved reading the issue and repeatedly searching the repository without ever posting a comment. These runs exhausted the eight-model-call limit.
This suggests that the agent's autonomy over when to continue searching versus when to commit to an answer is not always earning its cost. I hypothesize that when an issue is ambiguous and has several plausible explanations, Gemini struggles to determine when it has enough information, leading to excessive searching without completing the task.
Issues 4204 and 4206 provide evidence for this hypothesis. Both involve potentially misleading descriptions of the underlying problem, making it difficult to identify the responsible file. For issue 4204, the agent hit its turn limit in 9/10 runs; for issue 4206, it also hit the turn limit in 9/10 runs. Neither issue was successfully resolved in any of the ten runs. In most of those turn-limit runs the agent never posted a comment; in the rest (2 of 9 on 4204 and 1 of 9 on 4206) it posted an incorrect answer on its eighth and final call. This suggests that the agent continued investigating without reaching a decision, rather than knowing when to stop and commit to an answer.
Since a few sequences account for most runs, we could potentially replace some of these repeated search decisions with a predefined workflow while still allowing Gemini to choose the search terms. This could reduce unnecessary model calls and improve predictability.

### 5. The four gates

**Gate 1 — Task Variability: Does the task vary case to case?**
Although RepoMind handles different types of issues, the underlying task is relatively consistent: read an issue, search the repository, identify the responsible file, and post a comment. Most issues can therefore follow a predefined workflow. This could also prevent the agent from searching repeatedly without posting an answer, as observed in issues 4204 and 4206.

**Gate 2 — Damage Containment: Can you limit the damage of a mistake?**
The consequences of incorrect classifications are relatively minor because RepoMind can only read issues, search code, and post comments. It cannot directly modify the codebase. Although incorrect comments may waste developers' time, their effects are relatively contained, and humans can potentially correct them. The main exception is that comments are public while the code RepoMind searches is private: a careless comment could quote private code to the issue's author and cannot simply be un-posted, so the damage is limited but not zero.

**Gate 3 — Timely Detection and Reversibility: Will you catch it in time?**
Our implementation does not require human approval before posting. Missing comments and nonexistent file paths could be detected automatically, but identifying plausible yet incorrect files is more difficult. Since our evaluation system relies on known answers and does not provide safeguards during deployment, this gate is only partially satisfied.

**Gate 4 — Cost Justification: Is it worth the multiplier?**
The agent costs 6.68 times as much as the workflow, yet both achieved only 28/60 successful runs. In 23 runs, the agent failed to post a comment, frequently because it continued searching until reaching its execution limits. Therefore, its additional autonomy is not justified by its overall performance.

**Verdict — Hybrid**
I would choose a hybrid architecture. Although most tasks can be handled by a predictable workflow, the workflow's accuracy of 28/60 is relatively low. A fully autonomous agent is too expensive without improving overall accuracy, but it performs better on some issues, such as 4203.
A hybrid could preserve the workflow's fixed sequence while selectively giving the agent control when there is evidence of failure. Specifically, Python would handle issue reading, searching, and checking whether the selected file exists. If the file does not exist, the bounded agent would independently investigate and decide its next actions.
This approach could potentially improve accuracy without paying the full cost of autonomy on every run.

### 6. Our predictions

**Direct Call (Predicted 30/60; Actual 30/60)**
Although our overall prediction was exactly correct, we incorrectly predicted that issue 4203 would be the hardest because subtle CSV formatting problems would require examining individual files. Surprisingly, the direct call succeeded on all ten runs. In direct-4203-s01-347940, the model correctly identified src/ingest/parser.ts because the repository summary already described that file as responsible for parsing uploaded CSV statements. Therefore, inspecting individual files was unnecessary.
Instead, the direct call struggled with issues containing misleading surface clues. For example, in direct-4201-s01-30bc5d, it selected src/api/auth.ts because the issue mentioned password resets, even though the actual problem was in the email template.
We also predicted that the direct call would pass 4206 because its file would be easy to identify. It failed all ten runs: in direct-4206-s01-d0d6dc it chose src/export/csv.ts, the file the reporter blamed, while the actual cause is deduplication in src/ingest/dedupe.ts. The file only looked easy to identify because the reporter named it, and the reporter was wrong.

**Workflow (Predicted 40/60; Actual 28/60)**
We correctly predicted that issue 4206 would be particularly difficult: we reasoned that if the model identified the wrong file, the workflow could not reconsider its single search. The trace shows this happening, with a cause we had not anticipated: the reporter named the wrong file. In workflow-4206-s01-de0f0a, the model searched for the reporter's suggested file path, received no results, and selected that file anyway.
However, we underestimated the workflow's overall failure rate. Issue 4204 also failed in all ten runs. In workflow-4204-s01-88af5e, the correct file appeared in the search results, but the model still chose an incorrect one. This demonstrates that retrieving the correct information does not guarantee that the model will interpret it correctly.
The rest of the gap came from 4202 (2/10) and 4203 (6/10), where the model sometimes invented paths that do not exist, such as src/export/ in workflow-4202-s02-6d2ada and src/parser.js in workflow-4203-s04-4040fb.

**Agent (Predicted 40/60; Actual 28/60)**
We predicted that issue 4205 would be hardest because the agent might repeatedly search for a responsible file even though the issue was simply a question. However, it succeeded in 9/10 runs. In agent-4205-s01-486f9d, the model recognized that nothing was broken and correctly posted question / none. Its only unsuccessful run resulted from API rate-limit delays rather than excessive searching.
Instead, the agent struggled most with issues 4204 and 4206, succeeding in neither. In agent-4204-s02-343b46, it repeatedly searched for email and scheduling-related terms without investigating date-handling code. Similarly, in agent-4206-s01-c69094, it repeatedly searched export-related terms without investigating ingestion or deduplication. Both exhausted their model-call limits without posting.
The agent also failed all ten runs of 4202: in 6 runs it chose a wrong file instead of src/exportUtils.ts (src/export/csv.ts, src/export/ or src/api/reports.ts; for example src/export/csv.ts in agent-4202-s01-09e9cd, after searching CSV, export, xlsx, csv.ts and writeCsv), and in the other 4 it posted nothing.

**Overall Reflection**
Our predictions suggest that we initially overestimated the difficulty of technically specific problems and underestimated the difficulty of misleading or ambiguous descriptions. The direct call could sometimes identify the correct file from a repository summary alone, while the workflow could fail even when it retrieved the correct evidence. Most importantly, the agent's additional autonomy did not necessarily resolve ambiguity; sometimes it simply allowed the model to continue searching without committing to an answer.

### 7. The seven-layer audit

Our seven-layer audit found 0 empty layers, 3 partial layers, and 4 fully present layers. The partial layers were Harness, Memory & State, and Control & Policy. Unlike the lecture's example, which expects four missing layers in an initial implementation, our system implements at least part of every layer. However, important limitations remain, including incomplete context management, temporary memory, and limited policy enforcement. See `ARCHITECTURE.md` for the implementation details and line references.

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

### Hybrid analysis (after the 60 runs)

| Way | Passes / 60 | Per issue (4201 · 4202 · 4203 · 4204 · 4205 · 4206), of 10 | Sweep min–max | Issues passed in all 10 | Mean prompt tokens | Mean output tokens | p50 latency (s) | p95 latency (s) | Mean cost / run | Tool calls mean (max) |
|---|---|---|---|---|---|---|---|---|---|---|
| Direct | 30/60 | 0 · 10 · 10 · 0 · 10 · 0 | 3–3 | 3 | 1,114 | 12.0 | 0.64 | 33.26 | $0.000364 | 2.00 (2) |
| Workflow | 28/60 | 10 · 2 · 6 · 0 · 10 · 0 | 2–4 | 2 | 889 | 20.1 | 1.20 | 59.89 | $0.000317 | 4.78 (5) |
| Agent | 28/60 | 10 · 0 · 9 · 0 · 9 · 0 | 2–3 | 1 | 5,874 | 142.0 | 4.71 | 107.52 | $0.002117 | 5.83 (8) |
| **Hybrid** | **31/60** | 10 · 5 · 6 · 0 · 10 · 0 | 2–4 | 2 | 1,633 | 40.2 | 1.20 | 5.08 | $0.000590 | 5.32 (12) |

Hand-offs to the agent: 7 of 60 hybrid runs. Measured cost $0.000590 per run, against
the Part C blended cost of $0.000317.

Latency is not comparable across these rows. The direct, workflow and agent runs
(15:47 to 17:11) hit the vendor's rate limits: 5, 7 and 22 of their model calls took
over 20 seconds, one as long as 553 seconds. The hybrid ran after billing was restored,
and none of its calls took over 1 second. Its lower p95 reflects the API's waiting, not
the architecture.

**Handoff Rule:** I chose R4: the workflow runs by default, but if it selects a nonexistent file, a bounded agent takes over. This targets an identifiable workflow failure without introducing unnecessary autonomy.

**Performance:** The hybrid achieved 31/60 successes (51.7%), compared with 28/60 for both the workflow and agent. Its average cost was $0.000590 per run, approximately 1.86× the workflow's cost but 72% cheaper than the full agent.

**Handoff Analysis:** R4 triggered 7/60 times. All four handoffs on issue 4203 succeeded, with the agent correctly identifying src/ingest/parser.ts. However, all three handoffs on 4202 failed. The hybrid's improvement on 4202 (5/10 versus 2/10) came from workflow-only runs, suggesting normal model variation rather than successful escalation. R4 also missed incorrect answers referencing existing files, as seen in issues 4204 and 4206.

**Theoretical vs. Actual Cost:** Our Part C estimate was $0.000317 per run because f = 0, implying no handoffs. The actual cost was $0.000590 because R4 triggered seven agent investigations.

**Caveat:** We selected R4 using the evaluation issues themselves, so the hybrid's result is optimistic: it was measured on the same six issues its rule was chosen from. Further testing on unseen issues is needed.

**Verdict:** This changes our Part C verdict from hybrid to workflow. After evaluating the hybrid, I would ultimately choose the workflow. Although the hybrid achieved slightly higher accuracy (31/60 versus 28/60), it cost 86% more per run, and the improvement was not clearly attributable to successful agent handoffs. The workflow is cheaper, more predictable, and easier to debug. I would prioritize improving its search and file-selection steps rather than introducing additional autonomy.

## Assistance
Which AI tool, what it wrote, what you checked.

I used Claude Code to implement and debug the Python components, including the agent loop, evaluation scripts, hybrid architecture, automated analysis calculations, and report tables. Claude also helped inspect execution traces and identify patterns in the results. I made the architectural decisions, including selecting the handoff rule and evaluating the trade-offs between approaches. I used ChatGPT to understand the assignment concepts, interpret the experimental results, and refine my written explanations. The excluded-runs note and trace-based analyses were prepared with AI assistance and reviewed against the recorded data. Claude also wrote the prompts in `prompts/` and drafted the Part A worst-case sections, the Part D hand-off evidence and the `CHANGES.md` entry, which I reviewed.

**Conversation links:**
- ChatGPT: https://chatgpt.com/share/6ac97b79-7dfc-83ea-9409-7111e564df66
- Claude Code: the full conversation is exported to `reports/claude-transcripts/assignment1.txt`
