"""Run one way of doing the task over a set of issues, several times.

For every run the runner (not your code, not the model):
  - makes a fresh run_id and a trace file, runs/<run_id>.jsonl, and writes its
    first line (run_start) and last line (run_end);
  - builds a metered client with the harness's hard per-run ceiling, and a tool
    registry bound to that run_id, so every comment is stamped with it;
  - calls ways/<way>.py's run(ctx);
  - appends the run's totals to runs/_ledger.jsonl, and refuses to start new
    runs once the assignment's token ceiling is spent.

A run that raises is recorded with its error and the sweep carries on.
"""

from __future__ import annotations

import importlib
import json
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from harness import ROOT
from harness.backends import REAL_BACKENDS, make_backend
from harness.client import BudgetExceeded, ModelClient, ToolCall
from harness.pricing import PriceSheet
from harness.settings import Settings, load_settings
from harness.trace import TraceWriter
from harness.tracker import Tracker
from tools import RunContext, ToolRegistry, default_tools

FREE_BACKENDS = {"never-stops"}
_ledger_lock = threading.Lock()


@dataclass
class WayContext:
    """What ways/<way>.py receives. Everything a run may touch is on here."""
    run_id: str
    issue_number: int
    client: ModelClient
    tools: ToolRegistry
    trace: TraceWriter
    tracker: Tracker
    settings: Settings
    root: Path

    def call_tool(self, step: int, name: str, tool_input: dict):
        """Call a tool from your own code, not at the model's request, and trace it.

        For the direct call and the workflow, where your code decides which tool
        runs. Returns the ToolResult (.content, .is_error). `step` is the step of the
        most recent model call, or 0 before the first."""
        call = ToolCall(id=f"code-{name}-{step}", name=name, input=tool_input)
        result = self.tools.call(name, tool_input)
        self.trace.tool_call(step, call, result)
        return result

    def prompt(self, name: str) -> str:
        """Read prompts/<name>. Keep every prompt you write in prompts/."""
        return (self.root / "prompts" / name).read_text()

    @property
    def repo_summary(self) -> str:
        """The fixed repository summary for the direct call. Do not edit the file."""
        return (self.root / "fixtures" / "repo_summary.md").read_text()


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    def spent_tokens(self) -> int:
        if not self.path.exists():
            return 0
        total = 0
        for line in self.path.read_text().splitlines():
            row = json.loads(line)
            if row.get("backend") not in FREE_BACKENDS:
                total += row.get("total_tokens", 0)
        return total

    def append(self, row: dict) -> None:
        with _ledger_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")


def run_once(way: str, issue: int, sweep: int, backend_name: str, *, settings: Settings,
             prices: PriceSheet, tracker: Tracker, root: Path, runs_dir: Path) -> dict:
    run_id = f"{way}-{issue}-s{sweep:02d}-{uuid.uuid4().hex[:6]}"
    backend = make_backend(backend_name, settings)
    model = settings.model if backend_name in REAL_BACKENDS else getattr(backend, "name", backend_name)
    trace = TraceWriter(runs_dir / f"{run_id}.jsonl", run_id, {
        "lab": "01", "way": way, "issue": issue, "sweep": sweep, "backend": backend_name,
        "model": model, "settings": settings.digest(), "price_sheet": prices.read_date,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    client = ModelClient(backend, prices, session_ceiling=settings.session_token_ceiling)
    tools = default_tools(RunContext(run_id=run_id, tracker=tracker, repo_root=root / "fixtures" / "repo"))
    ctx = WayContext(run_id, issue, client, tools, trace, tracker, settings, root)
    error = None
    try:
        importlib.import_module(f"ways.{way}").run(ctx)
    except BudgetExceeded as exc:
        error = f"BudgetExceeded: {exc}"
        if not trace.ended:
            trace.end("token_budget", detail="the harness ceiling stopped this run, not your loop")
    except NotImplementedError as exc:
        error = f"NotImplementedError: {exc}"
    except Exception as exc:  # the sweep goes on; the trace keeps the evidence
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"
    totals = client.totals()
    trace.run_end(totals, error)
    return {"run_id": run_id, "way": way, "issue": issue, "sweep": sweep, "backend": backend_name,
            "total_tokens": totals["total_tokens"], "cost_usd": totals["cost_usd"],
            "error": error.splitlines()[0] if error else None,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}


def run_sweeps(way: str, issues: list[int], sweeps: range, backend_name: str | None = None, *,
               jobs: int | None = None, over_budget: bool = False, root: Path = ROOT,
               log=print) -> list[dict]:
    settings = load_settings(root / "settings.yaml")
    backend_name = backend_name or settings.provider
    if not backend_name or (backend_name in REAL_BACKENDS and not settings.model):
        raise SystemExit("settings.yaml: choose your provider and model first "
                         "(the Assignment 1 handout, Getting started, step 2), then run `make ping`.")
    prices = PriceSheet(root / "pricing.yaml")
    tracker = Tracker(root)
    runs_dir = root / "runs"
    ledger = Ledger(runs_dir / "_ledger.jsonl")
    plan = [(sweep, issue) for sweep in sweeps for issue in issues]
    results: list[dict] = []
    stop = threading.Event()

    def task(item):
        sweep, issue = item
        if stop.is_set():
            return None
        if backend_name not in FREE_BACKENDS and not over_budget:
            spent = ledger.spent_tokens()
            if spent >= settings.lab_token_ceiling:
                stop.set()
                log(f"lab token ceiling reached ({spent:,} >= {settings.lab_token_ceiling:,}); "
                    "no new runs. Ask before passing --over-budget.")
                return None
        row = run_once(way, issue, sweep, backend_name, settings=settings, prices=prices,
                       tracker=tracker, root=root, runs_dir=runs_dir)
        ledger.append(row)
        flag = f"  ERROR {row['error']}" if row["error"] else ""
        log(f"{row['run_id']:<32} {row['total_tokens']:>9,} tok  ${row['cost_usd']:.4f}{flag}")
        return row

    with ThreadPoolExecutor(max_workers=max(1, jobs or settings.jobs)) as pool:
        for row in pool.map(task, plan):
            if row:
                results.append(row)
    return results
