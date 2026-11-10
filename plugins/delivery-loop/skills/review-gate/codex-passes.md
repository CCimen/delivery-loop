# Running a Codex pass

The two Codex reviewers are sounding boards and a second opinion. They do not judge. The leader runs every pass, checks each finding in source (through `finding-verifier`) and decides. The rules are in this skill's SKILL.md; this file says how a pass is run. `<runner>` is the path SKILL.md gives. Run it with `--help` when a flag is uncertain, and with `--dry-run` the first time for a new delivery.

## Before a pass
1. Freeze the target: worktree, branch and SHA. Nobody changes the worktree while the pass runs; otherwise `content_drift=true` and the pass does not count.
2. Write the brief to `<work>/codex/<id>-brief.md` and, for a follow-up, the finding table to `<work>/codex/<id>-findings.md`. Never in the repository, never secrets.
3. Launch from the repository the diff lives in (each repository has its own session scope). Use absolute paths.

## The command
Two calls in the same message, each with the Bash tool's `run_in_background: true`. No wrappers (`nohup`, `timeout`, `&`), no redirection, no polling.

```bash
<runner> \
  --session <id>-sol --new-session --model gpt-6.1-sol \
  --title "<id>" --phase <plan|commit-gate> --complexity <critical|complex|routine|trivial> \
  --path <absolute worktree or directory> \
  --context-file <work>/codex/<id>-brief.md \
  --context-bytes 45000 --context-total-bytes 140000 \
  --extra-instruction "Responsibility, contracts, simplicity and overbuilding. Does the delivery give what the plan promises?" \
  --question "Ready to merge, or small long-term improvements? What blocks green?"
```
- Second reviewer: `--session <id>-astra --model gpt-6-astra` and the mission `"Failure paths, data, security and concurrency. Argue for the strongest alternative."`.
- Gate pass: add `--require-green`.
- Later passes in the same session: drop `--new-session`, change the phase (`commit-gate` after `plan`, then `verification`), and pass the finding table as a context file. The session remembers model, complexity and effort.
- Repositories that must not receive artifacts: add `--artifact-dir <work>/codex/artifacts/<id>` from the first pass.
- Add an architecture lens from the `codex-peer-loop` skill's table with another `--extra-instruction` when the pass touches ownership, a system boundary, or concurrency and partial failure.

## After a pass
- Usable evidence: the `.status` receipt shows `timed_out=false`, `drain_complete=true`, `thread_identity_status=passed`, `content_drift=false` and `context_truncated=0`. If the startup lines show a truncated or omitted context file: raise the caps and rerun.
- The gate is green only with exit 0 under `--require-green`. Exit 2 is a completed pass that is not green: its findings stand and the pass is spent.
- Every finding goes to `finding-verifier` with the finding ID, the SHA and the delivery's goal. Write the verdicts to `<work>/verdicts/<id>.md` ([verdict table](templates/verdict-table.md)).
- When the reviewers contradict each other: decide on evidence, not majority, and write the reason.
- Budget per session: two design passes, three gate passes. The runner counts them (`pass_history` in the receipt), nobody else. When the budget is spent, settle remaining findings locally: a decisive check, or a fix the leader verifies. That never replaces both reviewers green on the final SHA: a head neither has reviewed is not merged; the delivery is cut into a smaller one with its own sessions, or goes to the owner.
- Working hours from the project profile apply to passes too.
