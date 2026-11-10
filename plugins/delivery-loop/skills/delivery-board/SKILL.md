---
name: delivery-board
description: The board convention for deliveries on top of the `br` (beads_rust) CLI. Use at the start of every leader session to find what can start and what is in flight, when a brief is sent (claim the item), whenever a delivery crosses a boundary (brief, build, gate, fix, CI, queue, landed, synced) and its work card must be rewritten, when recording a PR link or a follow-up, when closing a delivery after landing and sync, and before handing over to a new session. `br` must be installed separately.
---

# Delivery board

The board owns the queue: order, dependencies, status and next action per delivery. Not the conversation, and not a status file; the status file says only what is happening right now (sessions, worktrees, waiting on). The board command and labels come from the project profile.

`br` (beads_rust) is not bundled with this plugin; install it separately and run it from the directory the profile names. The code and the forge decide what is implemented; check them before acting on what an item says.

## Convention
- **One item per delivery**, with the delivery id in the title: `<id>: <what it does>`.
- **Two labels**: the program label, and one label for where the code lands (for example mainline, integration branch, another repository, docs, or no code).
- **Items that are part of a delivery without being its item** are closed when the delivery has landed; keep that list in a comment on the program's parent item.
- **The PR link** goes in external-ref: `br update <id> --external-ref <pr-url>`.
- **The work card** is the item's notes, overwritten at every boundary: `br update <id> --notes "<card>"`.

```
State: brief | build | gate | fix | CI | queue | landed | synced
Branch, worktree: …        PR, head: <number> <sha>   (PR link also in external-ref)
Brief, report, verdicts: paths
Codex: <id>-sol n/3, <id>-astra n/3
Next: one sentence.        Waiting on: …
```

## Status rules
- Claim the item when the brief is sent: `br update <id> --claim` (sets `in_progress`).
- Close it only after the delivery has landed and been synced to the integration branch, if the project has one: `br close <id> --reason "<landed as …, synced at …>"`. If the sync cannot go through, the item stays in progress with the next action on the card.
- Follow-ups from the review gate become new items with the evidence, not changes to the PR.
- Only the leader changes the board. Builders name the item id in their report; `beads-reconciler` proposes `br` commands and runs none.

## Session start
1. Read the status file.
2. `br ready -l <program-label>`: what can start.
3. `br list -s in_progress -l <program-label>`: what is in flight (it does not show in `ready`).
4. `br show <id>` for each card you will act on.
5. The real state on the forge (PR head, CI) before anything is done.

Before switching to a new leader session, write the cards first.
