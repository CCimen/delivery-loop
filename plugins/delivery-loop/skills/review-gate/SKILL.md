---
name: review-gate
description: The review protocol and merge gate for a delivery. Use when a builder reports a frozen commit, before anything is pushed or merged, when choosing review depth (lens reviewers, two Codex reviewers, stack check) by risk, when deciding whether a finding is applied, rejected, a follow-up or an owner question, after any new commit (fix round, bot or CI finding) that needs re-validation, when a pass budget is spent, and when filling a gate receipt. Holds the brief, gate receipt, decision record and verdict table templates.
---

# Review gate

Goal: keep quality, rigour and nuance high, without going outside scope and without engineering more than the value justifies. Reviewers give evidence; the leader judges.

Templates: [brief](templates/brief.md), [gate receipt](templates/gate-receipt.md), [decision record](templates/decision-record.md), [verdict table](templates/verdict-table.md). How a Codex pass is run: [codex-passes.md](codex-passes.md). The runner is `${CLAUDE_PLUGIN_ROOT}/skills/codex-peer-loop/scripts/codex_peer_loop.py` (the `codex-peer-loop` skill owns its flags).

## 1. Depth follows risk
| Change | Lens review (fresh `lens-reviewer` subagents) | Codex | Running stack |
|---|---|---|---|
| Docs, copy, test-only, mechanical | one lens | both reviewers, low or medium effort | test-only: repeated runs; docs: none |
| Ordinary behaviour or contract | three lenses, high effort | both reviewers, effort by complexity | yes |
| Security, identity, sessions, deletion of retained data, migrations, concurrency | three lenses, high effort | both reviewers, xhigh | yes, including the failure paths |
| Plans, amendments, decisions before briefing | none | both reviewers, xhigh for consequential designs | none |

The three lenses are the PR's own goal (for example finality or security), correctness and consumers (every client and the API), and tests (does each test fail without its fix).

Every Codex finding is checked in source by `finding-verifier`, which tries to refute it and returns the smallest resolution before anything is applied. Nits outside the changed lines do not block and skip verification.

## 2. When a finding is applied
Only when all three hold:
1. It is verified in source or by a check. The reviewer's word is not enough.
2. It belongs to this delivery: its stated goal, or a regression it causes.
3. The fix is the smallest one that removes the real problem, and its value can be stated.

Otherwise:
- **Real but owned elsewhere:** a follow-up on the board, with the evidence.
- **Not proven:** recorded as rejected, with the reason.
- **A product or contract choice:** an owner question.

When the two reviewers contradict each other, decide on evidence, not majority, and write the reason.

## 3. Scope guard in every brief
- **In scope:** the delivery's requirements. Decided future needs may shape a boundary, but they are not built now.
- **Known and out of scope:** listed, so reviewers do not rediscover them.
- **Reviewers and verifiers** say where a suggested fix is larger than needed.
- **Nits** do not block. They ride along only when they touch lines the delivery already changes.

## 4. Stop rules
- **Pass budgets:** per Codex session, a design gets a plan pass and one follow-up; a gate gets at most three passes. The runner counts, nobody else.
- **Repeated findings:** if fix rounds keep producing findings about the previous fix, cut the delivery smaller instead of adding passes.
- **No speculative design:** no new mechanism, setting or abstraction unless it removes a demonstrated problem. "Might be useful later" becomes a follow-up note, not code.

## 5. Codex passes
- The leader runs every pass; builders run none. One session per delivery and reviewer: `<id>-sol`, `<id>-astra`. Plan and gate passes share the session, so the reviewer knows the decided design.
- Same evidence, different missions. First reviewer (default `gpt-6.1-sol`): responsibility, contracts, simplicity, overbuilding, and whether the delivery gives what the plan promises. Second reviewer (default `gpt-6-astra`): failure paths, data, security, concurrency, and the strongest alternative.
- Complexity follows how hard the review is: `critical` for identity, sessions, multi-factor authentication, deletion of retained data, migrations and concurrency; `complex` for contracts between components or repositories; `routine` for ordinary behaviour; `trivial` for docs and mechanical changes. `--effort max` only with a difficulty named in the brief.
- The Codex brief points to files instead of pasting: the goal and the plan's section, decisions that apply, known and out of scope, validation already run, earlier findings by ID, and the question "Ready to merge, or small long-term improvements?".
- Codex is a colleague, not an authority. When you disagree, say so with evidence in the same session.

## 6. Usable evidence, a green gate, a spent pass
Keep these three apart:
- **Evidence is usable** when the `.status` receipt shows `timed_out=false`, `drain_complete=true`, `thread_identity_status=passed`, `content_drift=false` and `context_truncated=0`. A truncated or omitted context file: raise the caps and rerun.
- **The gate is green** only with exit 0 under `--require-green`.
- **A pass is spent** as the runner counts it (`pass_history`): a completed pass that is not green (exit 2) still spends one, and its findings stand.

A spent budget ends model review; it never approves. Settle what remains locally (a decisive check, or a fix the leader verifies), but that never replaces both reviewers green on the final SHA: a head neither has reviewed is not merged. Cut it into a smaller delivery with its own sessions, or take it to the owner.

## 7. Re-validation after every new commit
Every new SHA, also after findings from the review bot or CI, is tested on the delta: a `verification` pass in the same Codex sessions, the lenses and tests the delta touches rerun, and the stack check redone for changed behaviour. Older evidence is reused only with its SHA and the reason it still holds, written in the receipt. A reviewer that failed or timed out stands as "not covered" and never counts as green.

## 8. Records
- Every PR and design records how each finding was settled: ID, verdict, and where the fix lives ([verdict table](templates/verdict-table.md)).
- Owner decisions go into the decision log; significant design choices use the [decision record](templates/decision-record.md).
- Follow-ups go to the board, not into the PR.
- Before merging, fill a [gate receipt](templates/gate-receipt.md) for the exact head. New commit, new receipt.
