# Changelog

All notable changes to the `delivery-loop` plugin. Versions follow `version` in `plugins/delivery-loop/.claude-plugin/plugin.json`.

## 0.3.0 - 2026-11-10

Easier to start with on a new machine and in a new project.

- New skill `setup` (runs only when asked): checks `br`, the Codex CLI, Python, git and the project profile, says what works without each, and adds the profile to the project's CLAUDE.md.
- The method now says what happens without the Codex CLI: "Codex reviewers: none" in the profile, a gate of lenses and verification, and a receipt that says so.
- README: install from GitHub, requirements as a table with what each tool adds, adoption through `setup`.

## 0.2.0 - 2026-11-10

Builds in the guidance from Anthropic's "Prompting Claude Fable 5.2".

- `orchestrate`: a new section "Instructions and reports" (say who owns the code, finish the whole task, exact approvals with the exception inside the rule, pruning cautions that build up, keeping the owner informed, reports for a low-context reader, evidence instead of written-out reasoning); effort guidance under the model table; the gate reads the diff because a builder's summary leaves out small changes; what a subagent costs.
- `builder`: ownership and finishing rules, and a report that lists every change.
- Brief template: ownership and approval lines. Project profile: what needs the owner's word and what needs no approval.
- The delta check marks the reviewed commit as seen; a pass with content drift gives invalid evidence.

## 0.1.0 - 2026-11-10

First release.

### Skills
- `orchestrate`: the leader's method. Roles and model tiers, advisor rules, where truth lives, a delivery step by step (brief, build, gate before push, verdicts, one fix round, push and CI, leader's own check, merge, after landing), parallel work and WIP limits, keeping an integration branch in sync, token rules, and the mapping to subagents, dynamic workflows and the advisor. Includes a project profile template and the engineering principles.
- `review-gate`: depth by risk, when a finding is applied, scope guard, stop rules, Codex pass rules, usable evidence versus a green gate versus a spent pass, re-validation after every new commit, and records. Includes templates for the brief, gate receipt, decision record and verdict table, and how a Codex pass is run.
- `delivery-board`: the board convention on top of `br` (beads_rust): one item per delivery, program and landing labels, the work card in the item's notes, the PR link in external-ref, status rules and the session-start routine.
- `codex-peer-loop`: the Codex peer review skill with its runner and tests. The runner is located through `${CLAUDE_SKILL_DIR}`; the examples use neutral names.

### Agents
- `builder`, `cartographer`, `contract-auditor`, `data-lifecycle-auditor`, `finding-verifier`, `lens-reviewer`, `beads-reconciler`.

### Not included
- Hooks and guards (working hours, push rules, gate receipt enforcement), the `br` tool, the Codex CLI, any project's plan, decisions, briefs or board contents, and the `codex-implement-loop` skill.
