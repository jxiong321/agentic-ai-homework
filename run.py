"""Run a way of doing the triage task.

    python run.py --way agent --set dev --runs 1                  # one try on the dev issues
    python run.py --way workflow --set eval --runs 10             # Part B: 60 runs
    python run.py --way agent --backend never-stops --set dev     # test your bounds for free

Each run writes runs/<run_id>.jsonl. Success is not decided here: your
eval/check_triage.py reads the tracker for each run_id and decides.
"""

import argparse
import sys

from harness.runner import run_sweeps
from harness.tracker import Tracker


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--way", required=True, help="a module in ways/: direct, workflow, agent, hybrid")
    p.add_argument("--set", default="dev", choices=["dev", "eval"], help="which issues (default dev)")
    p.add_argument("--issues", help="comma-separated issue numbers; overrides --set")
    p.add_argument("--runs", type=int, default=1, help="sweeps over the issues (default 1)")
    p.add_argument("--start-sweep", type=int, default=1, help="number of the first sweep, to resume")
    p.add_argument("--backend", help="default: the provider in settings.yaml; never-stops tests your bounds for free")
    p.add_argument("--jobs", type=int, help="runs at once (default from settings.yaml)")
    p.add_argument("--over-budget", action="store_true", help="ignore the assignment's token ceiling (ask first)")
    a = p.parse_args(argv)

    issues = ([int(x) for x in a.issues.split(",")] if a.issues
              else Tracker().issue_numbers(a.set))
    sweeps = range(a.start_sweep, a.start_sweep + a.runs)
    rows = run_sweeps(a.way, issues, sweeps, a.backend, jobs=a.jobs, over_budget=a.over_budget)
    tokens = sum(r["total_tokens"] for r in rows)
    cost = sum(r["cost_usd"] for r in rows)
    errors = sum(1 for r in rows if r["error"])
    print(f"\n{len(rows)} runs, {tokens:,} tokens, ${cost:.4f}, {errors} with errors")
    return 1 if errors == len(rows) and rows else 0


if __name__ == "__main__":
    sys.exit(main())
