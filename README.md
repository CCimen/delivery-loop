# delivery-loop

A Claude Code plugin for leading software work that runs as several deliveries at once. A leader session writes briefs, hands them to builders, runs independent reviewers on a frozen commit, judges every finding by ID, and merges only behind a filled gate receipt. The queue lives on a durable board (`br`), not in the conversation, so any new session can pick up where the last one stopped.

This repository is a plugin marketplace named `delivery-loop` with one plugin, also named `delivery-loop`.

## What is in it

| Skill | Use it for |
|---|---|
| `/delivery-loop:orchestrate` | The leader's method: roles and model tiers, advisor, where truth lives, a delivery step by step, parallel work, integration-branch sync, token rules. Includes the project profile template and the engineering principles. |
| `/delivery-loop:review-gate` | Review depth by risk, finding verdicts, scope guard, stop rules, Codex pass rules, re-validation after every commit. Includes the brief, gate receipt, decision record and verdict table templates. |
| `/delivery-loop:delivery-board` | The board convention on `br`: one item per delivery, labels, the work card, status rules, session start. |
| `/delivery-loop:codex-peer-loop` | Run a read-only, resumable Codex review pass and interpret its receipt. |
| `/delivery-loop:setup` | Check the tools on this machine and add the project profile to a project. Runs only when you ask for it. |

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

## Not included
- **Hooks and guards** (working hours, push rules, gate receipt enforcement). Plugin hooks fire in every project where the plugin is enabled, and these are project-specific. Planned for a later version as opt-in per project.
- **The `br` tool and the Codex CLI.** Install them yourself.
- **Any project's content**: plans, decisions, briefs, reports or board items.
- **The `codex-implement-loop` skill** (Codex as the implementer).

## Requirements
Only Claude Code and `git` are required. Everything else adds a part of the method, and `/delivery-loop:setup` tells you which parts you have.

| Tool | Needed for | Without it |
|---|---|---|
| Claude Code with plugin support, `git` | Everything | – |
| `br` (beads_rust) on `PATH` | The board (`delivery-board`) | The other skills work; the queue lives in the status file until `br` is installed. |
| Codex CLI, signed in | The second-model review (`codex-peer-loop`, the gate's two reviewers) | Set "Codex reviewers: none" in the profile. The gate is then lenses and finding verification only, and the receipt says so. |
| Python 3.9 or later | The Codex runner | No Codex passes. |
| A forge CLI such as `gh` | Reading PR and CI state | The leader asks you for it. |
| The `/advisor` feature | A stronger model at decision points | The method works without it. |

## Install

You choose where to host the repository. Each person adds the marketplace once, then installs the plugin. Installing at user scope makes it available in the terminal, the desktop app's local sessions and VS Code on the same machine, since they read the same settings.

**From GitHub:**

```bash
claude plugin marketplace add CCimen/delivery-loop
claude plugin install delivery-loop@delivery-loop
```

In the desktop app: open the plugin browser, choose **Add marketplace**, enter `CCimen/delivery-loop` and select **Sync**, then install `delivery-loop`. Then run `/delivery-loop:setup` in the project you want to use it in.

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
Run `/delivery-loop:setup` in the project. It checks the tools on your machine, says what works without each, fills in the project profile from what the repository shows, asks you for the rest, and adds the profile to the project's CLAUDE.md when you agree. Then start a leader session with `/delivery-loop:orchestrate`.

By hand: copy the profile block from `plugins/delivery-loop/skills/orchestrate/project-profile.md` into the project's CLAUDE.md, fill it in, and create the work directories it names. A small project needs only the mainline, how merges happen, and where the work files live.

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

## License
No license has been chosen yet. Until one is added, the usual default applies: you may read and install the plugin from this repository, but there is no grant to copy or redistribute it.

