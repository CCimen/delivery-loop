---
name: orchestrate
description: The leader's method for multi-delivery software work, where builders build, reviewers give evidence and the leader judges and integrates. Use when starting or resuming a leader session, writing or sending a brief, deciding a delivery's next step (brief, build, gate, verdicts, fix round, push and CI, leader's own check, merge, after landing), planning parallel builds and WIP limits, syncing an integration branch, choosing models or subagents, or handing over to a new leader session.
---

# Orchestrate: leading deliveries

Builders build, reviewers give evidence, the leader judges. The leader owns the synthesis, the decisions and the integration.

The method expects a **project profile** in the project's CLAUDE.md: mainline and integration branch, how merges happen, working hours, board command and labels, where briefs, reports, verdicts and receipts live, the heavy-step throttle, and reviewer models. Template: [project-profile.md](project-profile.md). Engineering principles for every delivery: [engineering-principles.md](engineering-principles.md). The gate is owned by the `review-gate` skill, the board by `delivery-board`, Codex passes by `codex-peer-loop`.

## 1. Models and roles
Defaults; the project profile may change any of them.

| Role | Default model | Why |
|---|---|---|
| Leader while building | Opus, with Fable as advisor | Most turns are routine: read a report, start a review, tick a gate. The advisor is consulted at the forks. |
| Leader at open design (a plan pass before a delivery that still has a design choice, a new architecture question) | Fable | Open, consequential judgment. A Fable main model takes only Fable as advisor. |
| Builder: a builder session or the `builder` subagent | Opus | Implementation from a written brief. |
| Lenses, finding verification, contracts, data lifecycle | Opus in subagents | Judgment with file:line evidence. |
| Mapping, board reconciliation, reading CI logs, running a scripted stack check | Sonnet | Reading and running with a fixed format. |
| Simple lookups | Haiku | Find a file, list, count. |
| Second opinion | Codex, for example `gpt-6.1-sol` and `gpt-6-astra` | Independent model, own session. |

## 2. Advisor
- The owner turns it on with `/advisor fable` (saved as `advisorModel`); Fable needs a recent Claude Code and consent to usage credits through `/model fable`. The leader cannot turn it on. With no advisor tool in the session, say so and let the two Codex reviewers carry the second opinion.
- The advisor reads the whole conversation on every call, without cache. So: short leader sessions, evidence in before the question, few calls.
- The saved advisor applies to every session and is inherited by subagents whose model supports the pair, so builder sessions on Opus consult it too.
- Consult it: (1) before a brief with a design choice is frozen; (2) before a PR in the security class is merged; (3) when the same finding or failure comes back a second time; (4) when the two reviewers contradict each other and the source does not settle it.
- When advice contradicts the evidence (code, a test, a decision): state the conflict and decide on the evidence.

## 3. Where truth lives
The conversation is not the project's memory. Each kind of fact has one owner, and a new session reads them in this order. Paths come from the project profile.

| What | Owner |
|---|---|
| Order, dependencies, status and next action per delivery | The board: one item per delivery (`delivery-board`) |
| What a delivery contains and when it is done | The plan; it changes only by a decision |
| The owner's decisions | The decision log; a later decision overrides an earlier one and the design |
| The builder's assignment | `briefs/<id>.md` (template in `review-gate`) |
| The builder's result | `reports/<id>.md` |
| Review verdicts, per finding ID | `verdicts/<id>.md` |
| Gate receipt | `<receipts>/<full-sha>.md` |
| What is happening right now (sessions, worktrees, waiting on) | A short status file. The queue is on the board, not here |

The **work card** is the board item's notes, overwritten at every boundary (format in `delivery-board`). Start a session with the status file and the board's session-start routine, then the real state on the forge, before doing anything. Switch leader sessions when a wave has landed or the context has grown; write the cards first.

## 4. A delivery, step by step
1. **Brief.** The leader writes the brief from the plan. A delivery that still has a design choice gets a plan pass with both Codex reviewers before the brief is frozen. A delivery whose design the plan review already covered gets no plan pass.
2. **Build.** A small fix in an open PR: the `builder` subagent in that PR's worktree. A delivery: a builder session in its own worktree under the builder rules (for example `claude --agent delivery-loop:builder`). Test first. The builder runs no Codex passes; it does its own stack check and writes the report. Large deliveries with many touch points start with a short implementation plan that the leader approves.
3. **Gate, before push.** Cheap checks first: changed files against the brief's list, a single migration head, the report's tests. Then, in one message and on the same frozen SHA: the lenses at the depth the review protocol sets, and both Codex reviewers in `commit-gate`. Nobody changes the worktree during the passes.
4. **Verdicts.** Every finding goes to `finding-verifier`, except nits outside the changed lines, which do not block. The leader writes a verdict per finding ID: true, rejected with reason, follow-up on the board, or owner question. A reviewer that failed or timed out stands as "not covered" in the receipt and never counts as green.
5. **Fix round.** All true findings in one message to the same builder, which has the context. Every new SHA, also after findings from the bot or CI, is re-validated on the delta (`review-gate`). Two rounds that produce new findings about the previous fix: cut the delivery smaller.
6. **Push, CI, bot.** The leader pushes, opens the PR and requests the review bot the way the profile says. CI therefore runs only on reviewed code. Findings from the bot or CI go back to step 5.
7. **Leader's stack check.** The scenario from the delivery's "Done when", including its failure paths. A Sonnet subagent may run the script through the shared throttle and return evidence; the leader judges.
8. **Merge.** Gate receipt filled, then merge the way the profile says, pinned to the reviewed head (for example a merge queue with an expected head SHA).
9. **After landing.** After a landing on the mainline, sync the mainline into the integration branch (section 6). The board item closes only once the sync has gone through; if it cannot, the item stays in progress with the next action on the card. Then update the status page, if any, and tell the sessions whose files are affected.

## 5. Parallel work
- Independent chains of deliveries run in parallel, with documentation alongside. One writer per worktree and one build at a time per chain. At most one PR with a database migration in flight on the mainline; check the single migration head before every merge.
- At most three builds and two gates at once. The leader's judgment is the bottleneck; more builders only queue at the gate.
- Use waiting time: while builds run, write the next briefs and run the next plan passes.
- Start independent subagents in the same message, in the background. One level: subagents start no subagents of their own. Save each report as a file.
- Heavy steps (end-to-end tests, full test suites, type checks, builds, container builds) go through the project's shared throttle, with the concurrency cap it sets. A throttle failure such as running out of memory is not a test result.

## 6. Integration branch
- Others push to the integration branch too, so it moves. Run the delta check at session start, before every action on the branch, and before every brief that touches it: new commits, which deliveries they touch, and whether a sync would conflict. New commits in a watched area get a delta review (a subagent on `<seen>..<new>`); carry the consequences into the plan and the cards, then mark the new head as seen.
- Small, frequent syncs keep conflicts small: merge the mainline in after every landing on the mainline, not in bulk. Keep a PR branch against the integration branch current by merging the integration branch into it, never by rebasing pushed work.
- Where the profile allows it, the leader commits and pushes directly: the mainline merge after each landing, and small mechanical fixes that follow from it. Anything with new behaviour, and a first large sync, goes as a PR against the integration branch, because CI, the bot and the gate need a diff.
- The sync: its own worktree, `git merge origin/<mainline>` (never rebase, never force), a single migration head, unit tests and the type check through the throttle, then push. Conflicts in code someone else owns: tell that owner which files first.
- If the project's guard asks the owner before every direct push, that is the owner's setting.
- The integration branch goes into the mainline only at the point the plan names.

## 7. Token rules
1. Context lives in files and on the board. The leader reads reports and verdict tables, not whole diffs, and reads source only for a blocker or a disputed finding.
2. Every subagent gets a bounded brief, a fixed output format and the cheapest model that suffices.
3. Collect all findings, then one fix round. A follow-up goes to the same agent or session, not to a new one that has to re-read.
4. No plan pass where the plan already reviewed the design. Effort by difficulty, not by habit.
5. Gate before push, and small fixes ride along in an open PR: every PR costs CI runs.
6. Fan out only where the parts are independent. Do small things yourself.

## 8. Subagents (this plugin, named `delivery-loop:<name>`)
| Agent | Model | Used for |
|---|---|---|
| `cartographer` | Sonnet | Map one area with file:line evidence. |
| `contract-auditor` | Opus | One contract between two owners. |
| `data-lifecycle-auditor` | Opus | One kind of data from creation to confirmed deletion. |
| `finding-verifier` | Opus | Try to refute a finding before anything is applied. |
| `lens-reviewer` | Opus | One lens per agent on a diff: goal, correctness and consumers, tests. |
| `beads-reconciler` | Sonnet | Compare the board with code and PRs and propose `br` commands. |
| `builder` | Opus | Build one bounded, written brief in its own worktree. |

## 9. Mapping to Anthropic's agent patterns
- Subagents (delegate, read the report, follow up in the same thread, one level deep) = the Agent tool and SendMessage.
- Dynamic workflows (many agents in phases, cross-checking) = the Workflow tool. The gate fits: lenses, then verification per finding. Use it only when the owner explicitly asks for a workflow; otherwise run the same phases as parallel subagents.
- Advisor (a stronger model at decisive points while the main agent does the work) = `/advisor`.
- The patterns are parallelisation, specialisation and escalation. An agent that fails does not fail the run: list what was not covered.
