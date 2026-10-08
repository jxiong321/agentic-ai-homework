# RepoMind

The course's running system, built one layer at a time. RepoMind triages issues
for **Ledgerline**, a small reporting and export service: it reads an issue,
searches Ledgerline's private codebase, and posts a triage comment where the
issue's author can read it.

That combination is deliberate. RepoMind reads text anyone can write, reaches
code nobody outside the team should see, and writes somewhere public. Week 1
calls it the lethal trifecta. You build it this way on purpose, and Week 8 is
when you close it.

## Start here

You have two things: this repository, and the assignment handout from your instructor.
The handout says what to build and how it is graded; this file says how the
repository works. For Assignment 1, read the handout's "Getting started" first.

Everything that runs, meters and checks your work is built. The files you write
are stubs that raise `NotImplementedError` until you fill them in, so nothing
runs end to end on a fresh copy. That is expected.

### What you need

- Python 3.10 or later, `git` and `make`.
- An API key for a model you choose, from any vendor, that supports tool
  (function) calling. A cheap model is fine, and some vendors have a free tier.
  Never commit the key and never share it.

### Set up, and choose your model

```bash
make setup                     # creates .venv and installs the three dependencies
source .venv/bin/activate      # in every new terminal
make test                      # the harness's own tests; they spend no tokens
```

Then choose your model, once: every comparison you make holds it fixed. Two
backends cover almost every vendor:

| Your model | In `settings.yaml` |
|---|---|
| Claude, through Anthropic's API | `provider: anthropic`, `model`; the key in `ANTHROPIC_API_KEY` |
| Anything with an OpenAI-compatible API: OpenAI, Google Gemini, Mistral, DeepSeek, Groq, OpenRouter, a local Ollama or vLLM server, and many more | `provider: openai-compatible`, `model`, `base_url` (none for OpenAI itself), and `api_key_env`, the variable that holds your key (default `OPENAI_API_KEY`) |

If `pricing.yaml` has no line for your model, add one from your vendor's price
page, with that page and the date you read it (the file shows how). On a free
tier, still use the paid rate the page lists, or every cost comparison is $0.

**Not sure which?** Start with Google's Gemini API, which has a free tier:
`provider: openai-compatible`,
`base_url: https://generativelanguage.googleapis.com/v1beta/openai/`,
`api_key_env: GEMINI_API_KEY`, and `model: gemini-3.5-flash-lite`. Avoid the
very smallest models, such as `gemini-3.1-flash-lite`, which tend to search in
circles. Any vendor's model with tool calling works the same way. Then:

```bash
export OPENAI_API_KEY=...      # or ANTHROPIC_API_KEY, or the variable you named
make ping                      # two tiny calls: your key, your model, its tool calling, its price
```

Put the `export` line in your shell profile, not in a file inside this
repository. `make test` and `make ping` must both pass before you write any
code. Your code never depends on the vendor: the harness keeps every message in
one format and translates for the backend.

### Where to start: Assignment 1

| Order | What you write | How you test it | Costs |
|---|---|---|---|
| Part 0 | `eval/part0.py`, which reads the recorded run | Its numbers, against `make check-01` | Nothing |
| Part A | `agent/loop.py`, `agent/bounds.yaml`, and `ways/agent.py`, which runs the loop | `make bounds-smoke` | Nothing |
| Part B | `ways/direct.py`, `ways/workflow.py`, `prompts/*`, `eval/check_triage.py`, `eval/summarize.py` | `python run.py --way <way> --set dev`, then the measured runs | Tokens |
| Part C | `reports/LAB_01.md`, `reports/LAB_01.json`, `ARCHITECTURE.md` | `make check-01` | Nothing |
| Part D | `ways/hybrid.py` | The same 60 runs, without `make reset` first | Tokens |

`make check-01` works at any point and shows what is still missing.

## What is here, and what is yours

| Path | What it is | Yours to edit? |
|---|---|---|
| `harness/` | The model client, tracker, trace writer, runner, prices, scripted models | No |
| `tools/` | The three tools and their registry | Not yet (Week 3 rewrites them) |
| `fixtures/` | Ledgerline's codebase, the issues, the answers, a recorded run | **Never** |
| `checks/` | The checkers, one per assignment, and `FORMATS.md`, which defines every format they read | No |
| `tests/` | The harness's own tests | No |
| `settings.yaml`, `pricing.yaml` | Your model, the ceilings, the dated price sheet | Once, in setup: your model and its price line; never the ceilings |
| `run.py` | Runs a way over a set of issues, one trace per run | No |
| `agent/` | Your loop, and its bounds | **Yes** |
| `ways/` | Your four ways of doing Assignment 1's task | **Yes** |
| `eval/` | Your grounded success check, your results script, and your Part 0 script | **Yes** |
| `prompts/` | Every prompt you write, one file each | **Yes** |
| `reports/`, `ARCHITECTURE.md`, `CHANGES.md` | Your write-ups; `reports/` starts with templates | **Yes** |
| `runs/`, `tracker/` | Made by your first run: traces, the run ledger, posted comments | Written by the harness; **commit them** |

## Running

```bash
python run.py --way agent --set dev --runs 1            # try it on the two dev issues
python run.py --way workflow --set eval --runs 10       # a measurement: 60 runs
make ping                                                # check your model: two tiny calls
make bounds-smoke                                        # your agent against a model that never stops; free
make reset                                               # archive old comments before a measurement
make check-01                                            # the Assignment 1 checker
```

Each run writes `runs/<run_id>.jsonl` and appends a line to
`runs/_ledger.jsonl`. The runner stamps a fresh `run_id` on every run, and the
tracker stamps it on every comment that run posts, so each run is checked on its
own comments and nothing else. On a free tier, or if you hit rate limits, add `--jobs 1`:
the harness waits as long as your vendor asks before it retries.
`python run.py --help` lists every option.

## The rules the harness enforces

- **Success is read from the tracker, never from the agent.** Your
  `eval/check_triage.py` decides; the model's closing words decide nothing.
- **Every run has a hard ceiling** (`session_token_ceiling`), and **every assignment
  has one** (`lab_token_ceiling`). Your loop's own budget sits below the first; the
  runner stops starting runs at the second. Ask before you pass `--over-budget`.
- **Every number carries its run count and its spread.** Plan for ten runs, not one.
- **Prompts live in `prompts/`**, and a layer held only by a prompt is empty.
- **Disclose AI assistance** in each report: which tool, what it wrote, what you
  checked.

## Submitting an assignment

Your copy of this repository is private. When you create it, add the course
staff's GitHub account as a collaborator (**Settings**, then **Collaborators**)
and post its URL on the assignment in Canvas: that is how staff find and read
your work. Then, for each assignment:

Run `make check-01` first; it is the same checker staff run. Commit everything,
including `runs/` and `tracker/` (the checker reads both), then tag the commit
and push both the commit and the tag. A tag you have not pushed has not been
submitted.

```bash
make check-01
git add -A
git commit -m "Assignment 1"
git tag lab-01
git push
git push origin lab-01
```

Some assignments ask you to push a file before you measure: in Assignment 1, your
predictions. Commit and push it on its own, before the runs it predicts. The
time GitHub records for the push is the one that counts.
