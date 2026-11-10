---
name: setup
description: Check that this machine and project are ready for delivery-loop and adopt it in a project. Verifies br, the Codex CLI, Python and git, says what works without each, and adds the project profile to the project's CLAUDE.md. Use right after installing the plugin, when starting to use it in a new project, or when a delivery-loop skill fails because a tool or the profile is missing.
disable-model-invocation: true
---

# Setup: get a machine and a project ready

Run the check, tell the user what is missing and what still works, then add the project profile. Change nothing without the user's yes.

## 1. Check
```bash
bash "${CLAUDE_SKILL_DIR}/scripts/doctor.sh"
```
The script only reads: tool versions and the current project. Report its lines as they are.

## 2. What works without each tool
| Missing | What still works | What does not |
|---|---|---|
| `br` (beads_rust) | `orchestrate`, `review-gate`, `codex-peer-loop`, all agents | `delivery-board`. Until `br` is installed there is no board, so say plainly that the queue lives in the status file for now. |
| Codex CLI, or not signed in | Lenses, finding verification, the receipt | The two-model review. Set "Codex reviewers: none" in the profile; the gate is then weaker, and the receipt says so. |
| Python 3.9+ | Everything except the Codex runner | `codex-peer-loop` passes. |
| `gh` or another forge CLI | Everything local | Reading PR and CI state; the leader then asks the user for it. |

Do not install tools yourself. Name the tool and let the user install it.

## 3. The project profile
If the check reports no profile:
1. Read the template: `${CLAUDE_PLUGIN_ROOT}/skills/orchestrate/project-profile.md`.
2. Fill in what the repository shows: the mainline (default branch), how PRs land (merge queue, required checks, PR template), the migration tool, test and type-check commands, where a `.beads/` directory is.
3. Ask the user only for what the repository cannot show: an integration branch if any, working hours, the program label, where briefs, reports, verdicts and receipts should live, what needs their word and what needs no approval, and the reviewer models.
4. Show the finished block. On the user's yes, add it to the project's CLAUDE.md and create the work directories it names. Create board labels only if `br` is installed.

Write "none" where something does not apply. A small project needs only the mainline, how merges happen, and where the work files live.

## 4. Next
Say which skill starts the work: `/delivery-loop:orchestrate` for a leader session. A builder session runs as `claude --agent delivery-loop:builder` in the delivery's worktree.
