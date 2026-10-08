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


def check(tracker, run_id: str, issue_number: int, answer: dict) -> bool:
    raise NotImplementedError("Assignment 1 Part B: the grounded check")
