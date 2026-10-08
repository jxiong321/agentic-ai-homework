"""The formats a checker reads. checks/FORMATS.md documents each one in prose."""

from __future__ import annotations

import re

LABELS = ("bug", "feature", "question", "docs")

# Why a run ended. Written by the harness loop, never reported by the model.
TERMINAL_REASONS = (
    "model_stopped",  # the model ended its turn without asking for a tool
    "turn_limit",     # the loop reached its maximum number of steps
    "token_budget",   # the loop's own token budget was reached
    "wall_clock",     # the loop ran out of time
    "tool_error",     # a tool failed in a way the loop could not continue from
    "refusal",        # the model declined (stop_reason "refusal")
    "completed",      # written by the runner for ways that have no loop
    "crashed",        # written by the runner when your way raised; see run_end.error
)

_LABEL_LINE = re.compile(r"^\s*label\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_FILE_LINE = re.compile(r"^\s*file\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def normalize_path(path: str | None) -> str | None:
    """Canonical form of a file answer: relative to fixtures/repo, forward slashes, or 'none'."""
    if path is None:
        return None
    p = path.strip().strip("`'\"").strip()
    p = p.replace("\\", "/")
    for prefix in ("./", "fixtures/repo/", "repo/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
    p = p.rstrip(".,;")
    if p.lower() in ("none", "n/a", "-", ""):
        return "none"
    return p


def parse_triage_comment(body: str) -> tuple[str | None, str | None]:
    """Read the first 'label:' and 'file:' lines of a triage comment.

    Keys are case-insensitive. Backticks and a leading './' around the path are
    ignored. A missing line comes back as None.
    """
    label_match = _LABEL_LINE.search(body or "")
    file_match = _FILE_LINE.search(body or "")
    label = label_match.group(1).strip().strip("`'\"").lower() if label_match else None
    file = normalize_path(file_match.group(1)) if file_match else None
    return label, file


def format_triage_comment(label: str, file: str | None, note: str = "") -> str:
    """The comment body the assignment expects: two lines, then anything you like."""
    body = f"label: {label}\nfile: {normalize_path(file) or 'none'}"
    return f"{body}\n\n{note.strip()}" if note.strip() else body
