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

Effort: `high` is the starting point for builders and reviewers; most of the gain is already there. Use `xhigh` only where a measured gain justifies the tokens, and `max` almost never. Routine leader turns and scripted subagents run lower. Effort changes thinking, time and tool calls, not the length of a reply.

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
1. **Brief.** The leader writes the brief from the plan. A delivery that still has a design choice gets a plan pass with both Codex reviewers before the brief is frozen. A delivery whose design the plan review already covered gets no plan pass. The brief says who owns the code, which steps need no approval and what needs the leader's word (section 7; template in `review-gate`).
2. **Build.** A small fix in an open PR: the `builder` subagent in that PR's worktree. A delivery: a builder session in its own worktree under the builder rules (for example `claude --agent delivery-loop:builder`). Test first. The builder runs no Codex passes; it does its own stack check and writes the report. Large deliveries with many touch points start with a short implementation plan that the leader approves.
3. **Gate, before push.** Cheap checks first: changed files against the brief's list, a single migration head, the report's tests. Then, in one message and on the same frozen SHA: the lenses at the depth the review protocol sets, and both Codex reviewers in `commit-gate`. Nobody changes the worktree during the passes. A builder's report is not the diff: summaries leave out small changes, so a lens always reads the diff, and a changed file outside the brief's list or a behaviour change the brief did not ask for is a finding.
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
- Others push to the integration branch too, so it moves. Run the delta check at session start, before every action on the branch, and before every brief that touches it: new commits, which deliveries they touch, and whether a sync would conflict. New commits in a watched area get a delta review (a subagent on `<seen>..<new>`); carry the consequences into the plan and the cards, then mark exactly the reviewed commit as seen, so a commit that arrived after the review still shows as new.
- Small, frequent syncs keep conflicts small: merge the mainline in after every landing on the mainline, not in bulk. Keep a PR branch against the integration branch current by merging the integration branch into it, never by rebasing pushed work.
- Where the profile allows it, the leader commits and pushes directly: the mainline merge after each landing, and small mechanical fixes that follow from it. Anything with new behaviour, and a first large sync, goes as a PR against the integration branch, because CI, the bot and the gate need a diff.
- The sync: its own worktree, `git merge origin/<mainline>` (never rebase, never force), a single migration head, unit tests and the type check through the throttle, then push. Conflicts in code someone else owns: tell that owner which files first.
- If the project's guard asks the owner before every direct push, that is the owner's setting.
- The integration branch goes into the mainline only at the point the plan names.

## 7. Instructions and reports
- **Ownership.** Every brief says who owns the code. Where the delivery should leave its area cleaner, the brief carries this sentence, bounded to the area it names: "This codebase is yours: what it's for and how it's built are your call, and you'll keep building on it." Where the code is someone else's and should change as little as possible, leave the sentence out and say that instead. The sentence makes a builder merge repeated code and fix what it finds nearby; it also costs more output and brings changes nobody asked for, which is why the gate reads the diff.
- **Finish the whole task.** A builder works through ordinary obstacles (errors, timeouts, locked files, empty results, failing tools): diagnose, wait and retry, fix the request, use another route. It stops only for a deliberate blocker (a file marked not to be touched, access withheld on purpose, a guard) or a decision that belongs to the leader or the owner, and then says plainly what it found.
- **Approvals.** A rule names the exact actions that need the owner's word, with its scope and reason, and carries its own exception ("never X without the owner's go-ahead for that X"). The project profile also lists what needs no approval, for example retries of calls that are safe to repeat. A go-ahead says what to do ("Yes, fix F1 to F3 and write the report"), not "continue".
- **Caution builds up.** When a wave has landed, prune what every session carries: delete notes, memories and rules whose reason no longer holds, and rewrite absolutes so they state scope and reason. Read what reviewer agents attach to their reports: a reviewer's "stop at the first error" is evidence for the leader, not a standing rule for the builder.
- **Keeping the owner informed.** With a person watching, say in a line what you are about to do, give a one-line update every few tool calls, and close with a recap that stands on its own: what you found, what you did, what is next.
- **Reports and handoffs.** Write for a reader who has not seen the tool calls or the files: key points first, plain words, full sentences, the same word for the same thing, and no label invented during the work without saying what it is.
- **Evidence, not reasoning.** Never ask an agent to write out its reasoning in its answer; ask for evidence (file:line, command and result). A safety classifier can decline a benign security review; say so and run that review on another model.

## 8. Token rules
1. Context lives in files and on the board. The leader reads reports and verdict tables, not whole diffs, and reads source only for a blocker or a disputed finding.
2. Every subagent gets a bounded brief, a fixed output format and the cheapest model that suffices.
3. Collect all findings, then one fix round. A follow-up goes to the same agent or session, not to a new one that has to re-read.
4. No plan pass where the plan already reviewed the design. Effort by difficulty, not by habit.
5. Gate before push, and small fixes ride along in an open PR: every PR costs CI runs.
6. Fan out only where the parts are independent. Do small things yourself. A subagent is not free: it reads its context from scratch and can cost as much as a long leader turn, so know which model and effort each one runs on.

## 9. Subagents (this plugin, named `delivery-loop:<name>`)
| Agent | Model | Used for |
|---|---|---|
| `cartographer` | Sonnet | Map one area with file:line evidence. |
| `contract-auditor` | Opus | One contract between two owners. |
| `data-lifecycle-auditor` | Opus | One kind of data from creation to confirmed deletion. |
| `finding-verifier` | Opus | Try to refute a finding before anything is applied. |
| `lens-reviewer` | Opus | One lens per agent on a diff: goal, correctness and consumers, tests. |
| `beads-reconciler` | Sonnet | Compare the board with code and PRs and propose `br` commands. |
| `builder` | Opus | Build one bounded, written brief in its own worktree. |

## 10. Mapping to Anthropic's agent patterns
- Subagents (delegate, read the report, follow up in the same thread, one level deep) = the Agent tool and SendMessage.
- Dynamic workflows (many agents in phases, cross-checking) = the Workflow tool. The gate fits: lenses, then verification per finding. Use it only when the owner explicitly asks for a workflow; otherwise run the same phases as parallel subagents.
- Advisor (a stronger model at decisive points while the main agent does the work) = `/advisor`.
- The patterns are parallelisation, specialisation and escalation. An agent that fails does not fail the run: list what was not covered.
