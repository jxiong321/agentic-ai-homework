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
| Model | | | |
| Harness | | | |
| Tools | | | |
| Memory & State | | | |
| Control & Policy | | | |
| Observability | | | |
| Evaluation | | | |

**Empty layers:** … of 7. Slide 46 expects four to be missing from a first build:
memory and state, control and policy, observability, and evaluation. How does
yours compare?
