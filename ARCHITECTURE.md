# ARCHITECTURE.md · RepoMind on the seven layers

Assignment 1, Part C item 7 (Week 1, slide 43). For each layer: what does this job,
and where is it enforced. Cite code as a file path and line number joined by a
colon, inside backticks; the checker opens every reference. A layer held only by a
sentence in a prompt (any file under `prompts/`) is **EMPTY**, and so is a layer
nothing does yet. Status is one of: present, partial (say what is missing), or
**EMPTY**. Keep this file current: later assignments fill it in.

What each layer is for (Week 1, slides 40 to 42):

- **Model**: reasoning, choosing tools, generating text.
- **Harness**: runs the loop, builds each prompt, trims old history.
- **Tools**: where the system acts on the world.
- **Memory & State**: what survives a step, a session, a restart.
- **Control & Policy**: what the system may do, and when it must ask.
- **Observability**: a step-by-step record of what it did.
- **Evaluation**: measuring quality, before and after release.

| Layer | What does this job | Where it is enforced | Status |
|---|---|---|---|
| Model | Gemini 3.5 Flash-Lite reasons about issues, generates labels and file paths, and selects tools in the agent architecture. Python invokes the model through the client. | `agent/loop.py:76` | present |
| Harness | Python runs the agent loop, sends requests to Gemini, executes requested tools, and maintains conversation history. However, it does not trim old history. | `agent/loop.py:62`, `agent/loop.py:76`, `agent/loop.py:78`, `agent/loop.py:95` | partial (no history trimming) |
| Tools | Three Python tools retrieve issues, search repository files, and post comments. | `tools/read_issue.py:19`, `tools/search_repo.py:41`, `tools/post_comment.py:25` | present |
| Memory & State | Python maintains conversation history within each run, allowing the model to use previous responses and tool results. However, this memory disappears when the run ends and cannot be restored after a restart. | `agent/loop.py:58`, `agent/loop.py:78`, `agent/loop.py:101` | partial (no persistent agent memory) |
| Control & Policy | Python enforces model-call, token, and wall-clock limits. However, there is no human approval mechanism before posting comments or comprehensive action policy. | `agent/loop.py:65`, `agent/loop.py:68`, `agent/loop.py:71` | partial (missing broader policy enforcement) |
| Observability | Execution traces record model calls, tool calls, and termination reasons, allowing us to reconstruct the agent's behavior. | `agent/loop.py:77`, `agent/loop.py:99`, `agent/loop.py:87` | present |
| Evaluation | Automated checks verify the correctness of posted comments, while the summarizer computes success rates, token usage, latency, costs, and tool calls. | `eval/check_triage.py:22`, `eval/summarize.py:84`, `eval/summarize.py:205` | present |

**Empty layers:** 0 of 7.

Slide 46 illustrates an agent that had a model, harness, and powerful tools, but lacked important safeguards. Its Control & Policy and Observability layers were explicitly marked empty, while Memory & State and Evaluation had nothing reported. In comparison, our RepoMind implementation has no completely empty layers, although three are partial. We enforce execution limits in Python rather than relying solely on prompts, record execution traces, and evaluate outputs using automated checks. However, our system still lacks persistent agent memory, comprehensive policy enforcement, and human approval before posting comments.
