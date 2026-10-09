# CHANGES.md

Three lines per assignment: what it added, what it removed, what it constrained.
Removals are logged like additions.

## Assignment 1
- **Added:** a loop (`agent/loop.py`), a model (Gemini 3.5 Flash-Lite, `settings.yaml`) and three tools (`read_issue`, `search_repo`, `post_comment`), used four ways: a direct call, a workflow, the agent and a workflow-first hybrid (`ways/`).
- **Removed:** nothing.
- **Constrained:** the loop, by three bounds checked in code before every model call: 8 model calls, 30,000 tokens and 180 seconds (`agent/bounds.yaml`).
