# Assignment 1 report · Four ways to triage an issue

Every number here also goes in `reports/LAB_01.json`, which the checker reads
(format: `checks/FORMATS.md`, section 7). Give each number its run count. Mark
any vendor figure you cite with its source type and date.

## Part 0 · The recorded trace
Model calls, tool calls, prompt tokens and the cached share, first and last
prompt size, cumulative over first. One sentence on what the growth means.

## Part A · Your loop's bounds
Your three bounds and why. Your worst case: *F*, *A*, *N*, and the cumulative
prompt tokens at your turn limit.

## Part B · Results
The table for all three ways: passes out of 60, per issue out of 10, the spread
(lowest and highest sweep), issues solved in every run, tokens, p50 and p95
latency, cost, tool calls.

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

## Part D · The hybrid
Your hand-off rule, and the Part B traces that led you to it (written before you
measure). Its row beside the three ways (the same columns as Part B's table), how many of
its runs handed the issue to the agent, and its measured cost per run beside your
blended cost from Part C, item 3. Does it change your Part C verdict? Which of
the four would you ship, and why?

## Assistance
Which AI tool, what it wrote, what you checked.
