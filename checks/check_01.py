#!/usr/bin/env python3
"""Assignment 1 checker. Run it with `make check-01`.

It reads only the environment: your runs/ traces, the tracker's comments, your
reports/LAB_01.json and ARCHITECTURE.md, and it calls your code directly with a
scripted model. It never asks a model anything and never trusts a model's words.

Assignment 1 is scored out of 100. The checker awards the automated 80, over all four
ways (Part D's hybrid is the fourth); staff read Parts C and D for the other 20. It also prints integrity flags, which carry
no points and go to staff for review.
"""

from __future__ import annotations

import json
import math
import re
import sys
import tempfile
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from harness.backends import REAL_BACKENDS  # noqa: E402
from harness.client import ModelClient  # noqa: E402
from harness.formats import normalize_path, parse_triage_comment  # noqa: E402
from harness.pricing import PriceSheet  # noqa: E402
from harness.scripted import STUB_RESULT, NeverStops  # noqa: E402
from harness.settings import load_settings  # noqa: E402
from harness.trace import TraceWriter, read_trace  # noqa: E402
from harness.tracker import Tracker  # noqa: E402
from tools import ToolResult  # noqa: E402

WAYS = ("direct", "workflow", "agent", "hybrid")
RUNS_PER_ISSUE = 10
TOLERANCE = 0.01          # "within 1%"
WORST_CASE_SLACK = 1.15   # your message wrapping adds a little to each step

# Tokens the scripted model's run appends per step: its tool call plus the
# 1,600-character stub result, as the scripted token counter estimates them.
# Published in checks/FORMATS.md, section 4.
A_PUBLISHED = 463


@dataclass
class Section:
    name: str
    possible: float
    earned: float = 0.0
    notes: list[str] = field(default_factory=list)
    manual: bool = False

    def note(self, text: str) -> None:
        self.notes.append(text)


def within(value, target, tol=TOLERANCE) -> bool:
    if value is None or target is None:
        return False
    return abs(value - target) <= max(tol * abs(target), 1.0 if isinstance(target, int) else 1e-9)


# --------------------------------------------------------------------------------------
# Part 0: the recorded run, recomputed
# --------------------------------------------------------------------------------------

PART0_FIELDS = ("model_calls", "tool_calls", "prompt_tokens", "cache_read_tokens", "first_prompt", "last_prompt")


def part0_key() -> dict:
    calls, tool_calls = {}, 0
    for line in (ROOT / "fixtures" / "week01_recorded_run.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event.get("type") == "assistant":
            message = event["message"]
            calls[message["id"]] = message.get("usage", {})
            tool_calls += sum(1 for b in message.get("content", []) if b.get("type") == "tool_use")
    usages = list(calls.values())

    def prompt(u):
        return u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)

    return {"model_calls": len(usages), "tool_calls": tool_calls,
            "prompt_tokens": sum(prompt(u) for u in usages),
            "cache_read_tokens": sum(u.get("cache_read_input_tokens", 0) for u in usages),
            "first_prompt": prompt(usages[0]), "last_prompt": prompt(usages[-1])}


def check_part0(report: dict) -> Section:
    s = Section("Part 0 recomputes", 5)
    key, mine = part0_key(), report.get("part0") or {}
    wrong = [f for f in PART0_FIELDS if not within(mine.get(f), key[f])]
    s.earned = 5.0 * (len(PART0_FIELDS) - len(wrong)) / len(PART0_FIELDS)
    if wrong:
        s.note(f"part0 fields that do not match the recording: {', '.join(wrong)} "
               "(count model calls by distinct message.id; prompt = input + cache read + cache write)")
    return s


# --------------------------------------------------------------------------------------
# Bounds: your loop against a model that never stops
# --------------------------------------------------------------------------------------

class StubTools:
    """One tool that always returns the same 1,600 characters."""
    schemas = [{
        "name": "search_repo",
        "description": "Search the code.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }]

    def call(self, name, tool_input):
        return ToolResult(STUB_RESULT, False, 0.0)


def _run_scripted(bounds, backend, tmp: Path, label: str):
    from agent.loop import run_loop

    trace_path = tmp / f"{label}.jsonl"
    trace = TraceWriter(trace_path, f"check-{label}", {"lab": "01", "way": "check", "backend": "never-stops"})
    client = ModelClient(backend, PriceSheet(ROOT / "pricing.yaml"))
    start = time.monotonic()
    run_loop(client, StubTools(), "You are a test harness.", "Find the export code.", bounds, trace)
    elapsed = time.monotonic() - start
    return read_trace(trace_path), client, elapsed


def check_bounds(report: dict) -> Section:
    s = Section("Bounds hold", 20)
    try:
        from agent.loop import Bounds, load_bounds
        mine = load_bounds()
    except Exception as exc:
        s.note(f"could not load agent/bounds.yaml: {exc}")
        return s
    settings = load_settings(ROOT / "settings.yaml")
    if min(mine.max_steps, mine.max_tokens, mine.wall_clock_s) <= 0:
        s.note("agent/bounds.yaml still has a zero: set all three bounds")
        return s
    if mine.max_tokens >= settings.session_token_ceiling:
        s.note(f"max_tokens {mine.max_tokens:,} must sit below the harness ceiling "
               f"{settings.session_token_ceiling:,}, so that your loop ends the run first")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 1. The step limit, with your own max_steps. 12 points.
        try:
            n = mine.max_steps
            records, _, _ = _run_scripted(Bounds(n, 10**12, 3600.0), NeverStops(), tmp, "turns")
            calls = [r for r in records if r["type"] == "model_call"]
            ends = [r for r in records if r["type"] == "end"]
            reason = ends[0]["terminal_reason"] if len(ends) == 1 else None
            ok_count = len(calls) == n
            ok_reason = reason == "turn_limit"
            if not ok_count:
                s.note(f"turn limit: expected exactly {n} model_call records, found {len(calls)}")
            if not ok_reason:
                s.note(f"turn limit: expected one end record with turn_limit, found {[e['terminal_reason'] for e in ends]}")
            ok_worst = False
            if calls:
                f_measured = calls[0]["usage"]["prompt_tokens"]
                worst = n * f_measured + A_PUBLISHED * n * (n - 1) / 2
                spent = sum(c["usage"]["prompt_tokens"] for c in calls)
                ok_worst = spent <= worst * WORST_CASE_SLACK
                s.note(f"turn limit: cumulative prompt {spent:,} against worst case {worst:,.0f} "
                       f"(F={f_measured}, A={A_PUBLISHED}, N={n}){'' if ok_worst else ': OVER'}")
            s.earned += 4.0 * ok_count + 4.0 * ok_reason + 4.0 * ok_worst
        except NotImplementedError:
            s.note("agent/loop.py: run_loop is not written yet")
            return s
        except Exception:
            s.note("turn-limit test raised:\n" + traceback.format_exc(limit=3))

        # 2. The token budget. 3 points.
        try:
            budget = 60_000
            records, client, _ = _run_scripted(Bounds(10_000, budget, 3600.0), NeverStops(), tmp, "tokens")
            calls = [r for r in records if r["type"] == "model_call"]
            ends = [r["terminal_reason"] for r in records if r["type"] == "end"]
            last = (calls[-1]["usage"]["prompt_tokens"] + 30) if calls else 0
            ok = ends == ["token_budget"] and client.total_tokens <= budget + last
            s.earned += 3.0 * ok
            if not ok:
                s.note(f"token budget {budget:,}: ended {ends}, spent {client.total_tokens:,}; "
                       "expected token_budget, stopping before the call after the budget is reached")
        except Exception:
            s.note("token-budget test raised:\n" + traceback.format_exc(limit=3))

        # 3. The wall clock. 3 points.
        try:
            wall = 1.0
            records, _, elapsed = _run_scripted(Bounds(10_000, 10**12, wall), NeverStops(delay_s=0.2), tmp, "clock")
            ends = [r["terminal_reason"] for r in records if r["type"] == "end"]
            ok = ends == ["wall_clock"] and elapsed <= wall + 0.2 + 0.5
            s.earned += 3.0 * ok
            if not ok:
                s.note(f"wall clock {wall}s with 0.2s calls: ended {ends} after {elapsed:.2f}s")
        except Exception:
            s.note("wall-clock test raised:\n" + traceback.format_exc(limit=3))

    # 4. Your reported worst case is the formula applied to your own F and A. 2 points.
    wc = report.get("worst_case") or {}
    try:
        n, f, a, cum = (int(wc["N"]), float(wc["F"]), float(wc["A"]), float(wc["cumulative_prompt_tokens"]))
        expected = n * f + a * n * (n - 1) / 2
        ok = n == mine.max_steps and within(cum, expected)
        s.earned += 2.0 * ok
        if not ok:
            s.note(f"reports/LAB_01.json worst_case: N should be your max_steps ({mine.max_steps}) and "
                   f"cumulative_prompt_tokens should be N*F + A*N*(N-1)/2 = {expected:,.0f}")
    except (KeyError, TypeError, ValueError):
        s.note("reports/LAB_01.json worst_case is not filled in")
    return s


# --------------------------------------------------------------------------------------
# Runs: read every trace, and decide success from the tracker
# --------------------------------------------------------------------------------------

def load_runs(eval_issues: set[int]) -> tuple[dict, list[str]]:
    runs: dict[str, list[dict]] = {w: [] for w in WAYS}
    notes = []
    for path in sorted((ROOT / "runs").glob("*.jsonl")):
        if path.name.startswith("_"):
            continue
        try:
            records = read_trace(path)
        except json.JSONDecodeError:
            notes.append(f"{path.name}: not valid JSON lines, skipped")
            continue
        start = records[0] if records and records[0]["type"] == "run_start" else None
        end = records[-1] if records and records[-1]["type"] == "run_end" else None
        if not start or start.get("lab") != "01" or start.get("way") not in WAYS:
            continue
        if start.get("backend") == "never-stops" or start.get("issue") not in eval_issues:
            continue
        if not end:
            notes.append(f"{path.name}: no run_end record (the run did not finish), skipped")
            continue
        runs[start["way"]].append({
            "run_id": start["run_id"], "issue": start["issue"], "sweep": start["sweep"],
            "backend": start["backend"],
            "model_calls": [r for r in records if r["type"] == "model_call"],
            "tool_calls": [r for r in records if r["type"] == "tool_call"],
            "run_end": end,
        })
    return runs, notes


def grounded_pass(tracker: Tracker, run: dict, answer: dict) -> bool:
    comments = tracker.comments(run_id=run["run_id"], issue=run["issue"])
    if len(comments) != 1:
        return False
    label, file = parse_triage_comment(comments[0]["body"])
    return label == answer["label"] and file == normalize_path(answer["file"])


def summarize(runs: list[dict], passed: dict[str, bool], issues: list[int]) -> dict:
    per_issue_runs = defaultdict(int)
    per_issue_pass = defaultdict(int)
    per_sweep = defaultdict(int)
    for r in runs:
        per_issue_runs[r["issue"]] += 1
        per_issue_pass[r["issue"]] += passed[r["run_id"]]
        per_sweep[r["sweep"]] += passed[r["run_id"]]
    sweeps = sorted({r["sweep"] for r in runs})

    def mean(values):
        return sum(values) / len(values) if values else None

    return {
        "runs": len(runs),
        "passes": sum(passed[r["run_id"]] for r in runs),
        "per_issue": {str(i): per_issue_pass[i] for i in issues},
        "sweep_min": min((per_sweep[s] for s in sweeps), default=None),
        "sweep_max": max((per_sweep[s] for s in sweeps), default=None),
        "all_ten": sum(1 for i in issues if per_issue_runs[i] >= RUNS_PER_ISSUE and per_issue_pass[i] == per_issue_runs[i]),
        "mean_prompt_tokens": mean([sum(c["usage"]["prompt_tokens"] for c in r["model_calls"]) for r in runs]),
        "mean_output_tokens": mean([sum(c["usage"]["output_tokens"] for c in r["model_calls"]) for r in runs]),
        "mean_cost_usd": mean([sum(c["cost_usd"] or 0 for c in r["model_calls"]) for r in runs]),
        "_per_issue_runs": dict(per_issue_runs),
        "_sweeps": len(sweeps),
    }


def check_ways(summary: dict, report: dict) -> Section:
    s = Section("Four ways run", 20)
    results = report.get("results") or {}
    for way in WAYS:
        mine, theirs = summary[way], results.get(way) or {}
        if mine["runs"] == 0:
            s.note(f"{way}: no finished runs of this way on the evaluation issues")
            continue
        fields = ("runs", "passes", "sweep_min", "sweep_max", "all_ten")
        wrong = [k for k in fields if theirs.get(k) != mine[k]]
        if (theirs.get("per_issue") or {}) != mine["per_issue"]:
            wrong.append("per_issue")
        if wrong:
            s.note(f"{way}: your table disagrees with the tracker on {', '.join(wrong)}; "
                   f"the tracker says passes {mine['passes']}/{mine['runs']}, per issue {mine['per_issue']}")
        else:
            s.earned += 20 / len(WAYS)
            s.note(f"{way}: {mine['passes']}/{mine['runs']} passes, matches your table")
    return s


def check_grounded() -> Section:
    s = Section("The checker is grounded", 5)
    try:
        from eval.check_triage import check
    except Exception as exc:
        s.note(f"could not import eval.check_triage.check: {exc}")
        return s
    issue = 4192  # a development issue: the planted runs reveal nothing about evaluation
    answer = yaml.safe_load((ROOT / "fixtures" / "answers.yaml").read_text())["dev"][issue]
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = Tracker(ROOT, state_dir=Path(tmpdir))
        tracker.post_comment("planted-claims", issue,
                             f"label: {answer['label']}\nfile: src/api/auth.ts\n\nTriaged and verified: this is definitely correct.")
        tracker.post_comment("planted-silent", issue, f"label: {answer['label']}\nfile: {answer['file']}")
        try:
            claims = check(tracker, "planted-claims", issue, answer)
            silent = check(tracker, "planted-silent", issue, answer)
            nothing = check(tracker, "planted-nothing", issue, answer)
        except NotImplementedError:
            s.note("eval/check_triage.py is not written yet")
            return s
        except Exception:
            s.note("your check raised:\n" + traceback.format_exc(limit=3))
            return s
    ok = claims is False and silent is True and nothing is False
    s.earned = 5.0 * ok
    s.note(f"wrong comment that claims success -> {claims} (want False); "
           f"right comment, nothing said -> {silent} (want True); no comment -> {nothing} (want False)")
    return s


def check_runs_spread(summary: dict, report: dict, issues: list[int]) -> Section:
    s = Section("Runs and spread", 10)
    for way in WAYS:
        mine = summary[way]
        short = [i for i in issues if mine["_per_issue_runs"].get(i, 0) < RUNS_PER_ISSUE]
        theirs = (report.get("results") or {}).get(way) or {}
        has_spread = theirs.get("sweep_min") is not None and theirs.get("sweep_max") is not None
        if mine["runs"] >= RUNS_PER_ISSUE * len(issues) and not short and has_spread:
            s.earned += 10 / len(WAYS)
        else:
            s.note(f"{way}: {mine['runs']} runs over {mine['_sweeps']} sweeps"
                   + (f"; fewer than {RUNS_PER_ISSUE} runs on {short}" if short else "")
                   + ("" if has_spread else "; no spread (sweep_min, sweep_max) in your table"))
    return s


def check_recompute(summary: dict, report: dict, runs: dict) -> Section:
    s = Section("Numbers recompute", 10)
    results = report.get("results") or {}
    for way in WAYS:
        mine, theirs = summary[way], results.get(way) or {}
        if not mine["runs"]:
            continue
        bad = [k for k in ("mean_prompt_tokens", "mean_output_tokens", "mean_cost_usd")
               if not within(theirs.get(k), mine[k])]
        missing = [r["run_id"] for r in runs[way]
                   if sum(c["usage"]["prompt_tokens"] + c["usage"]["output_tokens"] for c in r["model_calls"])
                   != r["run_end"]["totals"]["total_tokens"]]
        if not bad and not missing:
            s.earned += 10 / len(WAYS)
        if bad:
            s.note(f"{way}: {', '.join(bad)} differ from your traces by more than 1% "
                   f"(traces give prompt {mine['mean_prompt_tokens']:,.0f}, output {mine['mean_output_tokens']:,.0f}, "
                   f"cost ${mine['mean_cost_usd']:.5f})")
        if missing:
            s.note(f"{way}: {len(missing)} runs spent tokens their trace does not record "
                   f"(a model call without trace.model_call), e.g. {missing[0]}")
    return s


REF = re.compile(r"`([\w./-]+):(\d+)`")


def integrity_flags(answers: dict) -> list[str]:
    """Evaluation answers found where they should not be. No points: staff decide.

    Tuning on the evaluation issues is against the assignment's rules, and an answer
    path inside a prompt or in the code of a way is the plainest sign of it."""
    flags = []
    paths = {a["file"] for a in answers.values() if a["file"] != "none"}
    places = [p for d in ("prompts", "ways", "agent") for p in sorted((ROOT / d).rglob("*")) if p.is_file()]
    for place in places:
        try:
            text = place.read_text()
        except UnicodeDecodeError:
            continue
        rel = place.relative_to(ROOT).as_posix()
        for path in sorted(paths):
            if path in text:
                flags.append(f"`{rel}` contains the evaluation answer `{path}`")
        if "answers.yaml" in text:
            flags.append(f"`{rel}` reads the answer file; only eval/ should")
    return flags


def check_audit() -> Section:
    s = Section("Audit", 10)
    path = ROOT / "ARCHITECTURE.md"
    if not path.exists():
        s.note("ARCHITECTURE.md is missing")
        return s
    refs = REF.findall(path.read_text())
    if not refs:
        s.note("ARCHITECTURE.md cites no `file:line` references")
        return s
    good = 0
    for file, line in refs:
        target = ROOT / file
        if file.startswith("prompts/"):
            s.note(f"`{file}:{line}` is a prompt file: a layer held only by a prompt is EMPTY")
        elif not target.is_file():
            s.note(f"`{file}:{line}`: no such file")
        elif int(line) < 1 or int(line) > len(target.read_text().splitlines()):
            s.note(f"`{file}:{line}`: the file has no line {line}")
        else:
            good += 1
    s.earned = 10.0 * good / len(refs)
    s.note(f"{good} of {len(refs)} references resolve to code outside prompts/")
    return s


# --------------------------------------------------------------------------------------

def main() -> int:
    report_path = ROOT / "reports" / "LAB_01.json"
    try:
        report = json.loads(report_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"reports/LAB_01.json could not be read ({exc}); checking what can be checked without it.\n")
        report = {}

    answers = yaml.safe_load((ROOT / "fixtures" / "answers.yaml").read_text())["eval"]
    answers = {int(k): v for k, v in answers.items()}
    issues = sorted(answers)
    tracker = Tracker(ROOT)
    runs, load_notes = load_runs(set(issues))
    passed = {r["run_id"]: grounded_pass(tracker, r, answers[r["issue"]]) for way in WAYS for r in runs[way]}
    summary = {way: summarize(runs[way], passed, issues) for way in WAYS}

    sections = [
        check_part0(report),
        check_bounds(report),
        check_ways(summary, report),
        check_grounded(),
        check_runs_spread(summary, report, issues),
        check_recompute(summary, report, runs),
        Section("Decision (Parts C, D)", 20, manual=True, notes=["read by staff from reports/LAB_01.md"]),
        check_audit(),
    ]
    backends = sorted({r["backend"] for way in WAYS for r in runs[way]})
    print(f"Assignment 1 check · runs read from runs/ · backends seen: {', '.join(backends) or 'none'}")
    if any(b not in REAL_BACKENDS for b in backends):
        print("  note: runs from a scripted or simulated backend are not a measurement of a model")
    unpriced = sum(1 for way in WAYS for r in runs[way] for c in r["model_calls"] if c.get("cost_usd") is None)
    if unpriced:
        print(f"  note: {unpriced} model calls have no price, so their cost counts as 0: "
              "add your model's line to pricing.yaml, with its source and read date")
    for note in load_notes[:5]:
        print(f"  note: {note}")
    print()
    auto_earned = auto_possible = 0.0
    for sec in sections:
        score = "staff" if sec.manual else f"{sec.earned:4.1f} / {sec.possible:g}"
        print(f"{sec.name:<26} {score}")
        for note in sec.notes:
            for i, line in enumerate(note.splitlines()):
                print(f"{'    - ' if i == 0 else '      '}{line}")
        if not sec.manual:
            auto_earned += sec.earned
            auto_possible += sec.possible
    print(f"\nAutomated: {auto_earned:.1f} / {auto_possible:g}   (plus up to 20 from staff for Parts C and D)")
    flags = integrity_flags(answers)
    print("\nIntegrity flags (no points; staff review): " + ("none" if not flags else ""))
    for flag in flags:
        print(f"    - Integrity flag: {flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
