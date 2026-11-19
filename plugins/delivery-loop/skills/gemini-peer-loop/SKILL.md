---
name: gemini-peer-loop
description: Run a skeptical, read-only, resumable Gemini peer-review loop from Claude Code through the Antigravity CLI (agy), with Gemini 4 Neon by default. Use whenever the user or repository policy asks for Gemini, Antigravity or agy as a reviewer, a Gemini second opinion, or a Gemini design pass or gate before landing; it owns the agy launch, the read-only sandbox, model and reasoning effort (low/medium/high/xhigh) driven by the difficulty of the review work, exact conversation continuity, receipts, pass budgets, and gate interpretation.
---

# Gemini Peer Loop

Use Gemini as Claude Code's skeptical peer reviewer, through the Antigravity
CLI (`agy`) in headless stream-json mode. Gemini reviews; it does not
implement. Claude verifies every important claim in source and decides.

This runner keeps the review contract of
[codex-peer-loop](../codex-peer-loop/SKILL.md): the workflow, phases, pass
budgets and convergence, declared complexity and auto effort, the three-line
gate header, the review manifest and drift check, receipts, and the required
Claude behavior all read the same there. This page covers what differs. Read
"Codex" there as "Gemini", `.codex/artifacts` as `.gemini-peer-loop/artifacts`,
and `CODEX_PEER_LOOP_*` as `GEMINI_PEER_LOOP_*`.

Gemini is an extra reviewer. It fills a required reviewer slot in the review
gate only when the project profile says so.

## Run a pass

```bash
${CLAUDE_SKILL_DIR}/scripts/gemini_peer_loop.py \
  --session billing-review-gemini \
  --new-session \
  --title "billing review" \
  --phase commit-gate \
  --complexity complex \
  --require-green \
  --path src/billing \
  --context-file /abs/path/brief.md \
  --question "Ready to land, or small long-term improvements? What blocks green?"
```

Resume with the same `--session` and without `--new-session`; the runner
prints a resume skeleton after each pass. Launch every pass with the `Bash`
tool's `run_in_background: true`, never under `setsid`, `nohup`, `timeout` or
a shell `&`, and wait for the task notification (see "Running to completion"
in codex-peer-loop). `--dry-run` prints the exact `agy` command and prompt.

## Model and effort

- Model: `gemini-4-neon` (Gemini 4 Neon) by default; `--model` or
  `GEMINI_PEER_LOOP_MODEL` picks `gemini-4-argon` or `gemini-4-hydrogen`
  (`agy models` lists all). A resumed session keeps its model.
- Effort: declare `--complexity` per pass and leave `--effort auto`, as in
  codex-peer-loop. Auto never exceeds `xhigh` and stops at the model's top
  level: `gemini-4-argon` tops out at `high`. `--effort max` only with a
  named difficulty; a level the model lacks is refused loudly by `agy`.

## Read-only boundary

Verified on macOS with `agy` 1.5.12:

- `agy` runs from a fresh workspace per pass under the state directory
  (`~/.cache/gemini-peer-loop/workspaces/`), removed after the pass, with
  `TMPDIR` inside it. Nothing one pass writes reaches the next: `agy` loads
  hooks, rules and agents from its workspace.
- Read rules mount everything else the sandbox could write as read-only: the
  repository, its git directory, external `--path` and `--context-file`
  directories, the artifact directory, the state directory, the workspace's
  `.agents` folder, and the sandbox's default writable roots (`~/.cache`,
  `~/Library/Caches`, `/tmp`, the user temp and cache directories). The most
  specific rule wins, so only the per-pass workspace stays writable.
- File writes, unsandboxed commands, URL actions and MCP are denied. A
  runner-written agent (`delivery-loop-reviewer`) allows only file view,
  shell, command status and finish, so scheduling, messaging, browser and
  subagent tools are absent. Commands run in the sandbox without network.
- The reviewed repository's own `.agents` hooks do not run: the repository is
  never `agy`'s workspace.
- Other platforms are refused: on a host without the sandbox, `agy` asks for
  approvals headless mode cannot give, and elsewhere its mounts are unproven.

Not isolated:

- Your own `agy` hooks (`~/.gemini/config/hooks.json`) still run, and no
  per-session switch stops them; the timeout covers a stall.
- Reads outside the repository are not blocked (the read-only Codex sandbox
  reads the whole disk too). Never put secrets in a brief.
- A hard-killed runner (SIGKILL) cannot stop `agy`, which runs in its own
  process group, and leaves its workspace behind. Before retrying, check that
  the earlier `agy` has exited. A pass killed mid-run may not be resumable;
  start a new session then. A workspace the runner cannot remove is named in
  a warning on stderr; delete it by hand.
- The drift check covers the repository and `--context-file` files. A
  `--path` outside the repository is reviewed but not hashed: pass external
  files the gate relies on as `--context-file`.

## The review and its evidence

The review is the structured result `agy` returns at the end of the turn
(`--json-schema`), never the streamed text, which also carries interim
chatter. Every stream line is checked live against one grammar: first one
`init` with a canonical conversation id, the runner's agent and
`proceed-in-sandbox` (on a resume, the stored conversation); then
`step_update` events of known step types, tool steps only from the
allowlist; then one `result`, and nothing after it. Every later event names
the init's conversation. Any break, including a line the runner cannot
check, stops `agy` at once.

| Exit | Meaning |
|---|---|
| 0 | Review completed (and green, with `--require-green`). |
| 2 | Review completed, gate not green: a review outcome; the pass is counted. |
| 3 | No usable review: no structured review or no valid header, a status other than SUCCESS, or a stream that broke the contract, including a resume that names another conversation (stopped at once). Not evidence, not counted. |
| 4 | Conversation identity could not be verified after the run; do not trust the output. |
| 5 | Output collection incomplete (`drain_complete=false`); not evidence. |
| 6 | agy's process group could not be confirmed stopped (`process_group=unconfirmed`); not evidence. |
| 124 | Timeout; the process group was stopped. |

The `.status` receipt has the same keys as codex-peer-loop's, plus
`reviewer=gemini`, `agy_bin=` and `agy_version=` (recorded, never refused);
`thread_id` holds the Gemini conversation id. The live `.progress` receipt
adds `permission_mode=` and `violation=`. Evidence is usable when the receipt
shows `timed_out=false`, `drain_complete=true`, `process_group` `clean` or `terminated` (never `unconfirmed`), `thread_identity_status=passed`, `content_drift=false`, an empty `manifest_error` and `context_truncated=0`. A pass counts toward the budget once Gemini completed a valid
review in the right conversation (exit 0 or 2), drift or manifest error
included; counted is not usable.

## Requirements

`agy` on `PATH` (or `--agy-bin`, `GEMINI_PEER_LOOP_AGY_BIN`), signed in once
interactively, Python 3.9 or later, and macOS.
