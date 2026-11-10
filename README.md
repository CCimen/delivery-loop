# delivery-loop

A Claude Code plugin for leading software work that runs as several deliveries at once. A leader session writes briefs, hands them to builders, runs independent reviewers on a frozen commit, judges every finding by ID, and merges only behind a filled gate receipt. The queue lives on a durable board (`br`), not in the conversation, so any new session can pick up where the last one stopped.

This repository is a plugin marketplace named `delivery-loop` with one plugin, also named `delivery-loop`.

## What is in 0.1.0

| Skill | Use it for |
|---|---|
| `/delivery-loop:orchestrate` | The leader's method: roles and model tiers, advisor, where truth lives, a delivery step by step, parallel work, integration-branch sync, token rules. Includes the project profile template and the engineering principles. |
| `/delivery-loop:review-gate` | Review depth by risk, finding verdicts, scope guard, stop rules, Codex pass rules, re-validation after every commit. Includes the brief, gate receipt, decision record and verdict table templates. |
| `/delivery-loop:delivery-board` | The board convention on `br`: one item per delivery, labels, the work card, status rules, session start. |
| `/delivery-loop:codex-peer-loop` | Run a read-only, resumable Codex review pass and interpret its receipt. |

| Agent | Use it for |
|---|---|
| `delivery-loop:builder` | Build one written brief in its own worktree: test first, never pushes, fixed report. |
| `delivery-loop:cartographer` | Map one area of the code with file:line evidence. |
| `delivery-loop:contract-auditor` | Audit one contract between two owners. |
| `delivery-loop:data-lifecycle-auditor` | Trace one kind of data to confirmed deletion. |
| `delivery-loop:finding-verifier` | Try to refute one finding before it is applied. |
| `delivery-loop:lens-reviewer` | Review a diff through one lens: goal, correctness and consumers, or tests. |
| `delivery-loop:beads-reconciler` | Compare the board with code and PRs and propose `br` commands. |

Claude loads a skill when the task matches its description, or you run it by name. A builder session runs as the builder agent: `claude --agent delivery-loop:builder` in the delivery's worktree.

## Not in 0.1.0
- **Hooks and guards** (working hours, push rules, gate receipt enforcement). Plugin hooks fire in every project where the plugin is enabled, and these are project-specific. Planned for a later version as opt-in per project.
- **The `br` tool and the Codex CLI.** Install them yourself.
- **Any project's content**: plans, decisions, briefs, reports or board items.
- **The `codex-implement-loop` skill** (Codex as the implementer).

## Requirements
- Claude Code with plugin support.
- `br` (beads_rust) on `PATH`, for the board.
- The Codex CLI, signed in, for `codex-peer-loop` and the review gate's Codex passes.
- Python 3.9 or later, for the Codex runner.
- `git`, and your forge's CLI (for example `gh`) for reading PR and CI state.
- Optional: the `/advisor` feature (the method works without it; say so in the session and let the Codex reviewers carry the second opinion).

## Install

You choose where to host the repository. Each person adds the marketplace once, then installs the plugin. Installing at user scope makes it available in the terminal, the desktop app's local sessions and VS Code on the same machine, since they read the same settings.

**From a local directory** (your own machine, or a clone):

```bash
claude plugin marketplace add /path/to/delivery-loop-plugin
claude plugin install delivery-loop@delivery-loop
```

A marketplace added from a local path loads the plugin in place: edits take effect at the next session or after `/reload-plugins`, whatever `version` says.

**From a private git repository** (any host):

```bash
claude plugin marketplace add git@your-host:your-org/delivery-loop-plugin.git
#   or: claude plugin marketplace add https://your-host/your-org/delivery-loop-plugin.git
#   or, on GitHub: claude plugin marketplace add your-org/delivery-loop-plugin
claude plugin install delivery-loop@delivery-loop
```

Claude Code clones with the git credentials already on the machine and never prompts. Over SSH the key must work without a passphrase prompt (for example loaded in `ssh-agent`) and the host must be in `known_hosts`; over HTTPS a credential helper must already hold a credential (on GitHub: `gh auth login`, then `gh auth setup-git`). Append `#<tag>` to the add command to pin a release.

**Inside a session**: `/plugin marketplace add <same source>`, then `/plugin install delivery-loop@delivery-loop` and choose a scope.

**Desktop app**: add the marketplace once with one of the commands above (or `/plugin marketplace add` in a session). Then, in a local or SSH session in the **Code** tab, click **+** next to the prompt box, select **Add plugins** (or **Plugins**, then **Browse plugins**), select `delivery-loop`, and choose a scope.

**Try it without installing**: `claude --plugin-dir ./plugins/delivery-loop`.

## Adopt it in a project
1. Copy the profile block from `plugins/delivery-loop/skills/orchestrate/project-profile.md` into the project's CLAUDE.md and fill it in: mainline and integration branch, how merges happen, working hours, the board command and labels, where briefs, reports, verdicts and receipts live, the heavy-step throttle, and reviewer models.
2. Create the work directories the profile names, and the board's program and landing labels.
3. Start a leader session and run `/delivery-loop:orchestrate`.

## Where the Codex runner is
The runner ships at `plugins/delivery-loop/skills/codex-peer-loop/scripts/codex_peer_loop.py`. The `codex-peer-loop` skill refers to it as `${CLAUDE_SKILL_DIR}/scripts/codex_peer_loop.py`, and the `review-gate` skill as `${CLAUDE_PLUGIN_ROOT}/skills/codex-peer-loop/scripts/codex_peer_loop.py`. Claude Code replaces both with the absolute path of the installed copy when the skill loads, so nothing depends on `~/.claude/skills`. To run it by hand, use the path in your clone. Session state lives in `~/.cache/codex-peer-loop/`, outside the plugin, so it survives plugin updates.

## Release a new version
1. Change the plugin.
2. Bump `version` in `plugins/delivery-loop/.claude-plugin/plugin.json`. Keep it out of `marketplace.json`, where a second value would conflict.
3. Add an entry to `CHANGELOG.md`.
4. Check: `claude plugin validate .` and, in `plugins/delivery-loop/skills/codex-peer-loop`, `python3 -m unittest discover -s tests`.
5. Commit, then tag: `claude plugin tag plugins/delivery-loop` creates `delivery-loop--v<version>` after checking that the manifests agree (`--push` pushes the tag). Push the commit.

Installed copies from a git-hosted marketplace stay on their version until the `version` string changes. They update when the user runs `claude plugin update delivery-loop@delivery-loop` (shell) or `/plugin marketplace update delivery-loop` (session), or automatically if they turn on **Enable auto-update** for the marketplace under **Marketplaces** in `/plugin` (off by default for marketplaces like this one). A running session keeps the version it loaded until `/reload-plugins` or the next session.

## What it costs per turn
While the plugin is enabled, every skill and agent description is in context on every turn: about 1,500 tokens for this version (`claude plugin details delivery-loop` shows the current figure). A skill's full text loads only when it is invoked, and then stays for the rest of the session: roughly 0.8k to 8k tokens per skill, the largest being `codex-peer-loop`. To pay nothing in projects that do not use the method, install at project or local scope, or disable the plugin there.

## Cloud sessions
Cloud sessions, including claude.ai/code, do not load plugins installed on your machine, nor ones that a repository's `.claude/settings.json` turns on. There, the plugin is available only if your organisation distributes it through managed settings.
