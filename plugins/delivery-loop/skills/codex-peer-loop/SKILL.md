---
name: codex-peer-loop
description: Run a skeptical, read-only, resumable Codex (GPT-6 Astra) peer-review loop from Claude Code for non-trivial plans, architecture and agent-rule changes, reliability-sensitive implementation, public contracts, design second opinions, and commit gates. Use whenever repository policy or the user asks for Codex, a "peer loop", a second opinion, a design pass, or a gate before landing; it owns model choice, reasoning effort (low/medium/high/xhigh) driven by the difficulty of the review work, exact session continuity, bounded evidence, receipts, pass budgets, and gate interpretation.
---

# Codex Peer Loop

Use Codex as Claude Code's skeptical peer reviewer. Codex reviews; it does not
implement. Claude verifies every important claim in source and decides.

Repository policy decides **when** a peer review is required and which
skepticism mode applies. This skill owns Codex CLI execution, model and effort
choice, exact session continuity, bounded evidence, receipts, pass budgets,
and gate interpretation.

## Workflow

1. Freeze the target before Pass 1:
   - request and observable behavior;
   - relevant product and roadmap context, current completion ledger, exact
     task, dependencies, adjacent remaining work, and why this slice is next;
   - the requirements of this slice, kept apart from decided future needs (a
     future need may shape a boundary without being built now);
   - branch/base/commit or dirty patch;
   - canonical owner and allowed files;
   - assumptions or unknowns that could change architecture or the verdict;
   - known problems, so the reviewer does not rediscover them;
   - validation already run and explicit non-goals.
2. Declare `--complexity` (see Model and effort) and start Pass 1 with
   `--new-session`. Ask Codex to challenge problem framing, ownership,
   overengineering, overcomplication, duplicate paths, delete/reuse
   opportunities, contracts, failure modes, tests, cost, and AI slop. Treat the
   brief as a hypothesis: verify it against the repository and runtime, and
   surface only unknowns capable of changing the decision.
3. Verify each finding and classify it by its ID (F1, F2, ...; Codex keeps the
   IDs stable across passes):
   - **true**: reproduced from file:line evidence and owned by this slice, fix;
   - **self-check**: plausible but unproven, run the cheapest decisive check;
   - **unproven / rejected**: Codex asserted without evidence or misread the
     code, record why and do not act;
   - **follow-up**: real but owned elsewhere, file it;
   - **escalate**: needs a product, public-contract, persistence, release, or
     operator decision.
4. Apply only verified in-scope changes. Codex is a second opinion, never the
   decider: a finding is accepted because Claude agrees with the evidence,
   not because Codex ranked it P1.
5. Resume the same `--session` with the phase that names the pass's mission
   (see Phases), the prior artifact, a finding-by-finding response by ID,
   changed files, and validation output.
6. Continue only for verified blockers, within the pass budget below. Stop and
   reframe if scope roughly doubles or a missing canonical contract is the real
   problem.

## Phases

The phase, not the iteration number, sets what a pass reviews and how broadly.
The iteration number is bookkeeping.

| Phase | Mission |
|---|---|
| `plan` | Problem framing, real alternatives, ownership, and the assumptions the decision rests on. |
| `agent-config` | Whether agent rules give each concern one owner, are testable, and fit repository policy. |
| `commit-gate` | A full review of the whole current change against the decided requirements. Use it for the first code review even when an earlier pass in the session reviewed the plan. |
| `verification` | Settle each prior finding by ID against the fixes, then check the fixes for regressions. |
| `post-commit` | Confirm the landed change matches what was reviewed. |
| `review`, `implementation`, `self-review` | General review of the supplied packet. |

## Pass budget and convergence

Long gate loops are the most expensive failure this loop has produced: one
program ran fourteen iterations on a single session with MIN_SCORE stuck at
6-7 because each pass surfaced findings about the previous pass's fixes.
Budget passes up front and record the rule in the brief:

- **Design**: a `plan` or `agent-config` pass plus at most one follow-up. Give
  Codex the preferred option plus the strongest alternative and ask it to
  argue against the preference.
- **Gate**: at most three passes, counting the `commit-gate` pass and the
  `verification` passes after it.
- The runner counts completed passes per session. When a budget is spent it
  prints no resume skeleton and says so.

A spent budget ends model review. It never changes how serious a finding is
and never approves the change. Settle each remaining verified blocker in one
of these ways:

- run a decisive local check;
- make a fix and verify it yourself;
- cut a smaller slice;
- record a blocked decision as the project requires.

A fourth gate pass is a sign the slice is too big, not that the review is too
weak.

A finding about code from the latest fix round can still be a real blocker,
for example a regression. Judge it on its evidence; its origin does not settle
whether it blocks. Dispute a finding in the same session with file:line
evidence, not opinion: one adjudication pass, then decide.

## Independent value and simplicity gate

When a user or repository requires this loop in addition to another exact-diff
commit gate, give Codex the same frozen diff plus the relevant roadmap, task
ledger, product context, prior delivery receipts, acceptance criteria, and
known gaps. Prefer direct paths and bounded relevant excerpts over an
unstructured dump that hides the decision.

Keep the second gate independent and decision-focused. Ask whether the change:

- delivers the roadmap or product outcome it claims;
- has one clear canonical owner and reduces rather than relocates debt;
- adds complexity only where a measured cost, durable invariant, public
  contract, scalability need, or failure mode justifies it;
- avoids both overengineering and underengineering: the smallest diff is not a
  virtue when it leaves brittle behavior, weak integrity, poor API DX, or a
  foreseeable scaling trap;
- can delete, reuse, or deepen existing ownership without choosing a shortcut;
- keeps production and test code proportional to observable risk.

Do not duplicate routine line-by-line correctness review already owned by the
first gate. Newly noticed unrelated issues remain follow-ups, not permission to
expand the commit.

## Architecture lenses (opt-in)

The default prompt stays short. When a change touches one of the triggers
below, add the matching lens with `--extra-instruction "<lens>"`. Repeat the
flag for more than one lens. Do not use `--focus`: it replaces the default
review lenses instead of adding to them.

| Trigger | Lens text to pass |
|---|---|
| A new or moved abstraction, or changed ownership | What must callers know after this change, where does a common change now spread, and is complexity encapsulated or only moved? |
| A new behavior resting on a key claim | Name the most important claim this change makes and the cheapest observation that could prove it wrong. |
| A property that must survive future refactors | Which important property deserves a cheap, durable check, and what is the smallest such check? |
| Responsibility, data ownership, or a system boundary changes | Compare against the strongest real alternative split of responsibility or data ownership, and state the trade-off that decides it. |
| Concurrency, retries, storage, or partial failure | Which guarantees hold under concurrent access, retries, crashes, and partial failure, and which are only assumed? |

The lenses draw on, in order: A Philosophy of Software Design, Modern
Software Engineering, Building Evolutionary Architectures, Software
Architecture: The Hard Parts, and Designing Data-Intensive Applications.
Each lens adds reasoning work, so raise `--complexity` with it when the lens
is the hard part of the pass.

Keep these out of the default review:

- generic rules about file counts, function length, or single-use abstractions;
- a full ADR or a broad alternatives analysis for every commit;
- a general framework of architecture checks for every quality;
- distribution and scale checklists for purely local changes.

## Model and effort

- Model: `gpt-6-astra` (override with `--model` or `CODEX_PEER_LOOP_MODEL`).
- Effort: `auto` (override with `--effort` or `CODEX_PEER_LOOP_EFFORT`).
- Complexity: `routine` (set with `--complexity` or `CODEX_PEER_LOOP_COMPLEXITY`).
- Timeout: 3600 seconds.
- Execution: read-only sandbox, user config ignored, MCP disabled by default.

Reviews run on GPT-6 Astra; codex-implement-loop codes on GPT-6.1 Sol by
default. Treat that split as a setup to evaluate, not a guarantee of
independence. Both models can be misled by the same wrong brief, and a
critical slice may use Astra on both sides. What keeps the review honest is a
separate reviewer session, clear goals and contracts in the brief, known
problems stated up front, and the implementer's explanation treated as a
hypothesis. Each model takes efforts `low` through `ultra`; "Astra medium"
means this model at that effort.

### Declare complexity

Claude declares how hard the **review work** is, meaning what the reviewer
must work out in this pass, not how much code changed. A one-line change to
tenant filtering can need several callers and a security boundary understood;
many mechanical edits can be easy to verify. File count does not set
complexity.

| Complexity | Auto effort | Use when |
|---|---|---|
| `trivial` | low | A mechanical change with unchanged behavior and contracts, whose correctness a narrow check can establish. |
| `routine` (default) | medium | Bounded behavior within known owners, where requirements, affected callers, and relevant tests are clear. |
| `complex` | high | Several interacting owners, changed contracts, concurrency, caching, or failure paths that must be understood together. |
| `critical` | xhigh | A hard, consequential decision with real remaining uncertainty, such as a migration, an isolation model, or a recovery mechanism, where a missed defect is costly. |

This is a starting policy, not a measured optimum. Calibrate it on your own
past reviews (see Measuring).

The session saves the complexity, the model, and the effort request. A
resumed pass reuses them without repeating flags; an explicit flag replaces
the saved value for this and later passes. Environment defaults only apply to
new sessions.

### Auto effort

`--effort auto` starts at the complexity's rung. Full-scope phases (`plan`,
`agent-config`, `commit-gate`) climb one rung because they review their whole
subject. Nothing lowers effort automatically, and the result stays within
low..xhigh.

| Complexity | plan / agent-config / commit-gate | Other phases |
|---|---|---|
| `trivial` | medium | low |
| `routine` | high | medium |
| `complex` | xhigh | high |
| `critical` | xhigh | xhigh |

Lower the declared complexity for a follow-up only when the evidence shows
the remaining verification is limited:

- the relevant contract was already reviewed;
- the fix is bounded and its impact is traceable;
- no new consequential assumptions or owners appeared;
- a clear check can show whether the finding is resolved.

A fix that changes retry behavior or moves ownership can need as much
reasoning as the pass before it.

Raise effort only for a named difficulty, not because a counter reached two.
Before escalating, diagnose why the pass stalled: a wrong spec, a missing
environment, an oversized task, or a check that cannot decide the question
each needs a different fix. Then state what extra reasoning should resolve,
for example: "two failure orderings give different recovery behavior; the
next pass decides which contract holds in both." Choose `max` or `ultra`
explicitly and only with that reason.

Pin `--effort` when the user names a tier ("run it at Astra high"); a pinned
value stays pinned across resumes. Skepticism sets the review stance, not
the effort. Lower effort is not lower standards: the review contract,
evidence rules, and gate header are the same at every level.

## Pass 1

```bash
${CLAUDE_SKILL_DIR}/scripts/codex_peer_loop.py \
  --session billing-review \
  --new-session \
  --title "billing review" \
  --phase plan \
  --iteration 1 \
  --complexity complex \
  --context-file /tmp/billing-review-brief.md \
  --path backend/src/billing \
  --skepticism skeptical \
  --question "Challenge the real problem, ownership, simpler delete/reuse-first design, tests, maintainability, and failure modes."
```

## Pass 2: first code review

The session keeps its complexity and effort request, so this `commit-gate`
pass runs at `xhigh` without repeating `--complexity complex`.

```bash
${CLAUDE_SKILL_DIR}/scripts/codex_peer_loop.py \
  --session billing-review \
  --title "billing review" \
  --phase commit-gate \
  --iteration 2 \
  --require-green \
  --context-file /tmp/billing-implementation-brief.md \
  --path backend/src/billing \
  --question "Review the implementation against the decided plan. What blocks green?"
```

## Pass 3: verification

```bash
${CLAUDE_SKILL_DIR}/scripts/codex_peer_loop.py \
  --session billing-review \
  --title "billing review" \
  --phase verification \
  --iteration 3 \
  --require-green \
  --context-file /tmp/billing-review-fix-summary.md \
  --path backend/src/billing \
  --question "Settle each prior finding by ID against the fixes and validation. What still blocks green?"
```

## Running to completion (long runs)

A review at `high` or `xhigh` effort routinely runs past any host's
foreground shell cap. Claude Code and Claude Desktop cap a foreground `Bash`
call at 600 seconds, while this runner's default timeout is 3600. Launch
every pass with the `Bash` tool's native `run_in_background: true` and the
plain command as shown above.

Never wrap the runner in `setsid`, `nohup`, `timeout`, or a shell `&`, and do
not redirect its stdout. `setsid` and `timeout` do not exist on macOS, so the
pass exits 127 before it starts. The wrapper is also unnecessary: the runner
starts Codex in its own process group and, after a timeout or when anything
outlives Codex, stops that whole group, including members that ignore
SIGTERM. A hand-rolled redirect is what hides the startup error.

Track the background task the tool returned, and nothing else. On startup the
runner announces this run's identity: session, model and resolved effort,
timeout, and the exact artifact, status-receipt, live `.progress` receipt, and
sidecar paths it owns. No pid is published, because the task, not a process,
is what you follow.

Expect silence. Codex output streams into `*.stdout.txt` / `*.stderr.txt`, so
the runner's own stdout stays quiet between the startup banner and the final
result. For a cheap mid-run status check read the `.progress` receipt
(event counts, last event and detail, elapsed as of the most recent event)
instead of tailing the JSONL sidecar. A log or receipt that stops growing
still proves nothing either way: it is equally consistent with a normal run
and a hung one. Only the tracked task's own state answers whether the run is
alive. Do not poll with foreground `sleep` loops; wait for the task
notification.

A pass succeeded only when that exact task exits 0 and its announced `.status`
receipt reports the run: `exit_code=0`, `timed_out=false`,
`drain_complete=true`, `thread_identity_status=passed`, `content_drift=false`,
plus `green_light` / `green_verdict` for gate decisions. Those parsed fields
are the machine-readable result; the artifact itself opens with
`# Codex Peer Loop Artifact` and carries the three-line gate header inside its
`## Codex Output` section, so do not expect the header at the top of the file.

Never infer health from `pgrep`, `ps` counts, unrelated Codex processes, log
file size, or the mere existence of a log. Those match other sessions and stale
processes, and they once proved a dead run alive. If the tracked task exits
non-zero, report the failure; do not relaunch under a different wrapper.

| Exit | Meaning |
|---|---|
| 0 | Review completed (and green, with `--require-green`). |
| 2 | Review completed, gate not green: a review outcome, not a launch failure. |
| 4 | Thread identity mismatch on resume; do not trust the output. |
| 5 | Output collection incomplete or failed (`drain_complete=false`); not evidence. |
| 6 | Codex's process group could not be confirmed stopped (`process_group=unconfirmed`); not evidence. |
| 124 | Timeout; the process group was stopped. |

## Session and gate integrity

The runner maps the stable `--session` name to Codex's canonical thread UUID
under `~/.cache/codex-peer-loop/`, scoped by the repository's main worktree
(`git rev-parse --git-common-dir`; a separate or bare git dir is its own
scope). Resumes use that exact UUID, never global `--last`.

Because the scope is the main worktree, a session started at the main checkout
resumes from any linked worktree of the same repository, and the reverse. A
separate clone is a different scope: launching there reports which repository
holds the session's state, so launch from that repository instead of starting
a replacement. Relative `--path` and `--context-file` values resolve against
the launch directory; use absolute paths when launching from a lane worktree.

One session runs one pass at a time. The runner holds an OS lock on the
session for the whole pass, from reading session state to the final receipt,
and refuses a second launch at startup. The kernel releases the lock if the
runner dies, so there is no stale lock to clear. Each run reads Codex's last
message from its own file, so a refused launch cannot disturb the running
pass. If Codex still reports "thread already has an active writer", wait for
the running task and rerun the same command; never answer it with
`--new-session`.

The mapping is stored the moment Codex announces the thread, not at exit:
once the `.progress` receipt shows `thread_persist=ok`, a timed-out or
killed pass stays resumable under the same `--session`. A failed store is
retried once at exit, recorded in the `.status` receipt, and announced with
a stderr warning; resumed passes report `n/a` because their state already
exists.

Old unscoped state is never guessed or silently reused. The runner fails with
the exact scoped destination so a human can verify and migrate the UUID, or
start a deliberate replacement with `--new-session`.

Receipts record identity as `passed`, `failed`, or `unverified`; a provider
failure is never reported as a successful identity check.

Use `--allow-new-on-resume-failure` only when losing prior context is acceptable.
It is not valid for a required verification pass.

A gate is valid only when the first three nonblank output lines are one
unambiguous header:

```text
VERDICT: green | changes_required | blocked
GREEN_LIGHT: yes | no
MIN_SCORE: 1-10
```

Later restatements do not override the opening header. MIN_SCORE is
diagnostic. The gate decision rests on the verdict and verified blockers. A
blocker must name the violated requirement, contract, or property, the
consequence, the evidence, and what would resolve it. A score, a style
preference, or wording that merely sounds machine-written does not block on
its own. `--required-min-score N` additionally enforces a score, for teams
that have calibrated what the numbers mean. Green is advisory until Claude
verifies the evidence and agrees.

## Evidence and receipts

Every receipt carries a review manifest: the base commit, a hash of the
staged and unstaged diff plus untracked files (scoped to `--path`, excluding
the runner's own artifacts), and a hash of the context files. The runner takes
the manifest before the prompt is assembled and again after the pass. If the
content changed during the run, `content_drift=true`, the verdict covers
neither version exactly, and `--require-green` fails. A git failure while
taking the manifest (including the repository and HEAD probes) is recorded as
`manifest_error` and also fails `--require-green`: stability that could not be
measured is not assumed. Outside a git repository the manifest covers only
the context files.
`pass_history` reports whether the pass was counted toward the budget; only
a review Codex completed with complete output counts. Keep the tree stable while a pass runs, and scope it
with `--path` when other agents work elsewhere in the repository.

Context files are read with per-file and total byte caps; the runner never
loads an entire oversized file merely to truncate it. Each file Codex will not
see whole gets a `context_truncated:`, `context_omitted:` or
`context_unreadable:` line on stderr at launch (also with `--dry-run`), and the
status receipt counts those files as `context_truncated=<n>`; this is a
warning, not a gate failure, so raise the caps when the reviewer needs the
whole file. Artifacts, JSONL
stdout/stderr sidecars, live `.progress` receipts, and status receipts are
written under `.codex/artifacts/codex-peer-loop-*` by default. When repository
or user policy forbids worktree-local artifacts, pass `--artifact-dir` pointing
at an approved external or temporary directory from the first run; the resume
command preserves it.

Prefer bounded source, test, runtime, or rich prototype references over repeated
prose. Keep generic standards in their canonical repository instructions or
specialist skills instead of copying them into the review brief. Never put
secrets, API keys, or credentials in a brief or context file; the artifact
stores the full prompt.

A run needs a brief. With `--question`, stdin is not read; put extra
material in `--context-file` (data waiting on stdin fails the launch rather
than being dropped). Without `--question`, stdin is the brief and must reach
end of input within 10 seconds, so close the pipe after writing. Either
failure stops the runner before Codex starts. Keep the title stable; iteration is separate metadata. Run the script with
`--help` for the current CLI contract and `--dry-run` to inspect the exact
command, resolved effort, and prompt. Do not duplicate its flag catalogue or
reviewer prompt in repository policy.

## Measuring

Before tuning the prompt or the effort policy, collect about ten changes you
have already judged:

- some with known, consequential defects;
- some that are correct;
- a fix that already resolved an earlier objection;
- a deliberate design choice that is easy to misread;
- a real problem outside the task's scope.

Change one thing at a time and track:

- which known defects were found and evidenced;
- false blockers;
- time to a usable decision;
- the number of passes.

Ten cases are a start, not a statistically safe measure.

## Required Claude behavior

- Verify file:line claims and blockers locally before acting on them.
- Reject vague green output or invented evidence.
- Document accepted, self-checked, deferred, escalated, and rejected findings
  by ID with the reason for each.
- Respect the pass budget; when it is spent, settle remaining blockers
  locally instead of running another model pass.
- Preserve local receipts, but do not commit them unless repository policy
  explicitly requires it.
- Final summaries name the session, iterations, model, complexity and effort,
  verdicts, finding IDs, fixes, disagreements, the reviewed head and drift
  status, and validation run.
