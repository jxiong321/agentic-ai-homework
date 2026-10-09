"""Assignment 1, Part B: the grounded success check. This file is yours.

Write it once and use it for every way. The checker calls it with this
exact signature, including on planted runs designed to catch a check that
trusts the agent:

    check(tracker, run_id, issue_number, answer) -> bool

    tracker       harness.tracker.Tracker; tracker.comments(run_id=..., issue=...)
    run_id        the run being judged
    issue_number  the issue it worked on
    answer        {"label": ..., "file": ...} from fixtures/answers.yaml

Success is read from the tracker, never from anything the agent said. Use
harness.formats.parse_triage_comment and normalize_path, so that your check and
the course checker read comments the same way.
"""

from harness.formats import normalize_path, parse_triage_comment


def check(tracker, run_id: str, issue_number: int, answer: dict) -> bool:
    # Only what the tracker holds counts: exactly one comment from this run on this issue
    comments = tracker.comments(run_id=run_id, issue=issue_number)
    if len(comments) != 1:
        return False
    label, file = parse_triage_comment(comments[0]["body"])
    return (label == str(answer["label"]).strip().lower()
            and file == normalize_path(answer["file"] or "none"))
