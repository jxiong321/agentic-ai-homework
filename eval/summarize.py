"""Assignment 1, Parts B to D: build the tables in reports/LAB_01.json from your runs. This file is yours.

Read every trace in runs/ and the comments in the tracker, decide each run's
success with your eval/check_triage.check, and compute the `results` entry for
each way (direct, workflow, agent, hybrid) and the computed fields of `analysis`.
Write them into reports/LAB_01.json and leave every other field (part0,
worst_case, verdict) as you set it. Every field is defined in checks/FORMATS.md,
section 7. The checker recomputes the counts and means the same way, so compute
them here, from the traces, never by hand.

    python -m eval.summarize             # print the tables and write reports/LAB_01.json
    python -m eval.summarize --dry-run   # print only
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import yaml

from agent.loop import load_bounds
from eval.check_triage import check
from harness.trace import read_trace
from harness.tracker import Tracker

ROOT = Path(__file__).resolve().parents[1]
WAYS = ("direct", "workflow", "agent", "hybrid")
RUNS_PER_ISSUE = 10


# -- reading runs -----------------------------------------------------------------------

def load_runs(runs_dir: Path, eval_issues: set[int]) -> tuple[dict[str, list[dict]], list[str]]:
    """Every finished evaluation run of each way. Same selection as the checker: lab 01,
    a known way, a real backend (not never-stops), an evaluation issue, and a run_end line."""
    runs = {way: [] for way in WAYS}
    notes = []
    for path in sorted(Path(runs_dir).glob("*.jsonl")):
        if path.name.startswith("_"):
            continue
        records = read_trace(path)
        start = records[0] if records and records[0]["type"] == "run_start" else None
        end = records[-1] if records and records[-1]["type"] == "run_end" else None
        if not start or start.get("lab") != "01" or start.get("way") not in WAYS:
            continue
        if start.get("backend") == "never-stops" or start.get("issue") not in eval_issues:
            continue  # scripted runs and dev issues never enter the results
        if not end:
            notes.append(f"{path.name}: no run_end (the run did not finish), skipped")
            continue
        runs[start["way"]].append({
            "run_id": start["run_id"], "issue": start["issue"], "sweep": start["sweep"],
            "model": start.get("model"), "settings": start.get("settings"),
            "model_calls": [r for r in records if r["type"] == "model_call"],
            "tool_calls": [r for r in records if r["type"] == "tool_call"],
            "end_reason": next((r["terminal_reason"] for r in records if r["type"] == "end"), None),
            "run_end": end,
        })
    return runs, notes


# -- the numbers ------------------------------------------------------------------------

def mean(values):
    return sum(values) / len(values) if values else None


def nearest_rank(values, pct):
    """Nearest-rank percentile: the smallest value with at least pct% of values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(pct / 100 * len(ordered))) - 1]


def usage_sum(run, field):
    return sum(c["usage"][field] for c in run["model_calls"])


def way_results(runs: list[dict], passed: dict[str, bool], issues: list[int]) -> dict:
    """One `results` entry (checks/FORMATS.md, section 7)."""
    per_issue = {str(i): sum(passed[r["run_id"]] for r in runs if r["issue"] == i) for i in issues}
    runs_per_issue = Counter(r["issue"] for r in runs)
    per_sweep = Counter()
    for r in runs:
        per_sweep[r["sweep"]] += passed[r["run_id"]]  # += 0 still records a sweep with no passes
    tool_counts = [len(r["tool_calls"]) for r in runs]
    latencies = [r["run_end"]["elapsed_s"] for r in runs]
    return {
        "runs": len(runs),
        "passes": sum(passed[r["run_id"]] for r in runs),
        "per_issue": per_issue,
        "sweep_min": min(per_sweep.values(), default=None),
        "sweep_max": max(per_sweep.values(), default=None),
        "all_ten": sum(1 for i in issues
                       if runs_per_issue[i] >= RUNS_PER_ISSUE and per_issue[str(i)] == runs_per_issue[i]),
        "mean_prompt_tokens": mean([usage_sum(r, "prompt_tokens") for r in runs]),
        "mean_output_tokens": mean([usage_sum(r, "output_tokens") for r in runs]),
        "mean_cached_tokens": mean([usage_sum(r, "cache_read_input_tokens") for r in runs]),
        "p50_latency_s": nearest_rank(latencies, 50),
        "p95_latency_s": nearest_rank(latencies, 95),
        "mean_cost_usd": mean([sum(c["cost_usd"] or 0 for c in r["model_calls"]) for r in runs]),
        "mean_tool_calls": mean(tool_counts),
        "max_tool_calls": max(tool_counts, default=None),
    }


def completeness_warnings(runs: list[dict], issues: list[int]) -> list[str]:
    """Everything that makes a way's measurement less than ten clean sweeps over every issue."""
    warnings = []
    expected = RUNS_PER_ISSUE * len(issues)
    if len(runs) != expected:
        warnings.append(f"{len(runs)} runs, expected {expected}")
    per_issue = Counter(r["issue"] for r in runs)
    short = {i: per_issue[i] for i in issues if per_issue[i] != RUNS_PER_ISSUE}
    if short:
        warnings.append(f"runs per issue not {RUNS_PER_ISSUE}: {short}")
    per_sweep = Counter(r["sweep"] for r in runs)
    partial = {s: n for s, n in sorted(per_sweep.items()) if n != len(issues)}
    if partial:
        warnings.append(f"sweeps without exactly one run per issue (sweep: runs): {partial}")
    repeats = [k for k, n in Counter((r["issue"], r["sweep"]) for r in runs).items() if n > 1]
    if repeats:
        warnings.append(f"(issue, sweep) run more than once: {sorted(repeats)}")
    crashed = [r["run_id"] for r in runs if r["run_end"].get("error")]
    if crashed:
        warnings.append(f"{len(crashed)} runs raised (counted as runs, and fail): {crashed[:5]}")
    unpriced = sum(1 for r in runs for c in r["model_calls"] if c["cost_usd"] is None)
    if unpriced:
        warnings.append(f"{unpriced} unpriced model calls, counted as $0")
    models = {c["model"] for r in runs for c in r["model_calls"]}
    if len(models) > 1:
        warnings.append(f"more than one model served these runs: {sorted(models)}")
    if len({r["settings"] for r in runs}) > 1:
        warnings.append("settings.yaml changed between runs (more than one settings hash)")
    return warnings


def measured_worst_case(agent_runs: list[dict], n: int) -> dict:
    """`worst_case` (checks/FORMATS.md, section 4): F is the mean first-call prompt over the
    agent's runs, A the mean increase in prompt over every pair of consecutive calls, N max_steps."""
    firsts = [r["model_calls"][0]["usage"]["prompt_tokens"] for r in agent_runs if r["model_calls"]]
    growth = [later["usage"]["prompt_tokens"] - earlier["usage"]["prompt_tokens"]
              for r in agent_runs for earlier, later in zip(r["model_calls"], r["model_calls"][1:])]
    f, a = mean(firsts), mean(growth)
    return {"F": f, "A": a, "N": n, "cumulative_prompt_tokens": n * f + a * n * (n - 1) / 2}


LOOP_REASONS = {"model_stopped", "turn_limit", "token_budget", "wall_clock", "tool_error", "refusal"}


def compute_analysis(results: dict[str, dict], runs: dict[str, list[dict]], issues: list[int]) -> dict:
    """The computed `analysis` fields (checks/FORMATS.md, section 7), for whichever ways have
    runs. `verdict` is a decision, not a computation, so it is never written here."""
    analysis = {}
    direct, workflow, agent = results.get("direct"), results.get("workflow"), results.get("agent")
    if agent and direct:
        tokens = lambda r: r["mean_prompt_tokens"] + r["mean_output_tokens"]
        analysis["ratio_agent_over_direct_tokens"] = tokens(agent) / tokens(direct)
    if agent and workflow:
        c = workflow["mean_cost_usd"]
        m = agent["mean_cost_usd"] / c
        rescued = [i for i in issues
                   if workflow["per_issue"][str(i)] < 5 and agent["per_issue"][str(i)] >= 5]
        f = len(rescued) / len(issues)
        analysis.update({
            "m_agent_over_workflow_cost": m,
            "f": f,
            "blended_cost": c * ((1 - f) + f * m),
            "all_agent_cost": c * m,
            "workflow_cost": c,
        })
    if agent:
        # Each agent run's tool names in order; how many distinct paths, and how much the top three cover
        paths = Counter(tuple(t["name"] for t in r["tool_calls"]) for r in runs["agent"])
        analysis["path_entropy"] = {
            "distinct_sequences": len(paths),
            "top3_share": sum(n for _, n in paths.most_common(3)) / len(runs["agent"]),
        }
    if runs.get("hybrid"):
        # A hybrid run that reached the agent ends with the loop's reason, not the runner's "completed"
        analysis["hybrid_handoffs"] = sum(1 for r in runs["hybrid"] if r["end_reason"] in LOOP_REASONS)
    return analysis


# -- the report -------------------------------------------------------------------------

def update_report(report_path: Path, results: dict[str, dict], analysis: dict | None = None,
                  worst_case: dict | None = None) -> None:
    """Write only the given ways' results, analysis fields and worst case; keep everything else."""
    report = json.loads(Path(report_path).read_text())
    for way, entry in results.items():
        report["results"][way].update(entry)
    for key, value in (analysis or {}).items():
        report["analysis"][key] = value
    if worst_case:
        report["worst_case"].update(worst_case)
    Path(report_path).write_text(json.dumps(report, indent=2) + "\n")


def summarize(runs_dir: Path, tracker, answers: dict[int, dict], issues: list[int]):
    """Results, warnings and analysis for every way with at least one evaluation run."""
    runs, notes = load_runs(runs_dir, set(issues))
    results, warnings = {}, {}
    for way in WAYS:
        if not runs[way]:
            continue  # leave a way with no runs untouched, rather than write zeros
        passed = {r["run_id"]: check(tracker, r["run_id"], r["issue"], answers[r["issue"]])
                  for r in runs[way]}
        results[way] = way_results(runs[way], passed, issues)
        warnings[way] = completeness_warnings(runs[way], issues)
    worst_case = measured_worst_case(runs["agent"], load_bounds().max_steps) if runs["agent"] else None
    return results, warnings, notes, compute_analysis(results, runs, issues), worst_case


def print_table(results: dict, warnings: dict, notes: list[str]) -> None:
    fmt = lambda v, spec: "-" if v is None else format(v, spec)
    for way, r in results.items():
        uncached = r["mean_prompt_tokens"] - r["mean_cached_tokens"]
        print(f"\n{way}: {r['passes']}/{r['runs']} passes   per issue {r['per_issue']}")
        print(f"  sweeps min/max {r['sweep_min']}/{r['sweep_max']}   issues passed in all ten: {r['all_ten']}")
        print(f"  mean tokens: prompt {fmt(r['mean_prompt_tokens'], ',.1f')} "
              f"(cached {fmt(r['mean_cached_tokens'], ',.1f')}, uncached {fmt(uncached, ',.1f')}), "
              f"output {fmt(r['mean_output_tokens'], ',.1f')}")
        print(f"  latency p50 {fmt(r['p50_latency_s'], '.2f')}s  p95 {fmt(r['p95_latency_s'], '.2f')}s   "
              f"mean cost ${fmt(r['mean_cost_usd'], '.6f')}   "
              f"tool calls mean {fmt(r['mean_tool_calls'], '.2f')} max {r['max_tool_calls']}")
        for w in warnings[way]:
            print(f"  INCOMPLETE: {w}")
    for n in notes:
        print(f"note: {n}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Build reports/LAB_01.json results from runs/ and the tracker.")
    p.add_argument("--dry-run", action="store_true", help="print the tables without writing the report")
    a = p.parse_args(argv)

    tracker = Tracker(ROOT)
    issues = tracker.issue_numbers("eval")
    answers = yaml.safe_load((ROOT / "fixtures" / "answers.yaml").read_text())["eval"]
    results, warnings, notes, analysis, worst_case = summarize(ROOT / "runs", tracker, answers, issues)
    if not results:
        print("No finished evaluation runs in runs/; reports/LAB_01.json left unchanged.")
        return
    print_table(results, warnings, notes)
    print("\nanalysis:")
    for key, value in analysis.items():
        print(f"  {key}: {value}")
    print(f"\nworst case (agent runs): {worst_case}")
    if a.dry_run:
        print("\n--dry-run: reports/LAB_01.json left unchanged.")
        return
    update_report(ROOT / "reports" / "LAB_01.json", results, analysis, worst_case)
    print(f"\nwrote results for {', '.join(results)} to reports/LAB_01.json"
          + ("  (some ways are INCOMPLETE; see above)" if any(warnings.values()) else ""))


if __name__ == "__main__":
    main()
