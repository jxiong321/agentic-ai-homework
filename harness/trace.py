"""The run trace: runs/<run_id>.jsonl, one JSON object per line.

The runner writes the first line (run_start) and the last (run_end). Your code
writes everything in between: call trace.model_call after every model call,
trace.tool_call after every tool call, and, in the agent's loop, trace.end
exactly once with the reason the loop stopped. checks/FORMATS.md has the
fields; the checker reads nothing else.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from harness.formats import TERMINAL_REASONS


class TraceWriter:
    def __init__(self, path: Path, run_id: str, meta: dict):
        self.path = Path(path)
        self.run_id = run_id
        self._t0 = time.monotonic()
        self._lock = threading.Lock()
        self._ended = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w")
        self._write({"type": "run_start", **meta})

    def _write(self, record: dict) -> None:
        record = {"run_id": self.run_id, "t": round(time.monotonic() - self._t0, 3), **record}
        with self._lock:
            self._fh.write(json.dumps(record, default=str) + "\n")
            self._fh.flush()

    # -- for your code ----------------------------------------------------------------
    def model_call(self, step: int, response) -> None:
        """Record one model call. `response` is what ModelClient.create returned."""
        self._write({
            "type": "model_call",
            "step": step,
            "model": response.model,
            "stop_reason": response.stop_reason,
            "latency_s": round(response.latency_s, 3),
            "usage": response.usage.as_dict(),
            "cost_usd": response.cost_usd,
            "tool_calls": [{"name": c.name, "input": c.input} for c in response.tool_calls],
            "text": response.text[:2000],
        })

    def tool_call(self, step: int, call, result) -> None:
        """Record one tool call. `call` is a ToolCall; `result` is what ToolRegistry.call returned."""
        self._write({
            "type": "tool_call",
            "step": step,
            "name": call.name,
            "input": call.input,
            "is_error": result.is_error,
            "latency_s": round(result.latency_s, 3),
            "result_chars": len(result.content),
            "result_excerpt": result.content[:300],
        })

    def end(self, terminal_reason: str, detail: str = "") -> None:
        """Record why the loop stopped. Call it once, from your harness code, never from the model's words."""
        if terminal_reason not in TERMINAL_REASONS:
            raise ValueError(f"unknown terminal_reason {terminal_reason!r}; see harness.formats.TERMINAL_REASONS")
        if self._ended:
            raise RuntimeError("trace.end() was already called for this run")
        self._ended = True
        self._write({"type": "end", "terminal_reason": terminal_reason, "detail": detail})

    # -- for the runner ---------------------------------------------------------------
    @property
    def ended(self) -> bool:
        return self._ended

    def run_end(self, totals: dict, error: str | None) -> None:
        if not self._ended:
            self.end("crashed" if error else "completed",
                     detail="written by the runner" + ("; your way raised, see run_end.error" if error else ""))
        self._write({"type": "run_end", "elapsed_s": round(time.monotonic() - self._t0, 3),
                     "totals": totals, "error": error})
        with self._lock:
            self._fh.close()


def read_trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
