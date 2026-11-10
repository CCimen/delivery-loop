# Project profile template

Copy the block below into the project's CLAUDE.md and fill it in. The delivery-loop skills and agents read these values instead of assuming them. Write "none" where something does not apply.

```markdown
## Delivery loop: project profile
- Mainline: `<main>`. Integration branch: `<branch | none>`; it goes into the mainline only at <the delivery or decision that allows it>.
- Merging: <how a PR lands, for example a merge queue with an expected head SHA>. PR rules: <required PR sections and labels>. Review bot: <how to request it, for example a standalone `/review` comment | none>.
- Branches and PRs we never push to or merge: <list | none>.
- Direct pushes allowed: <for example the mainline merge into the integration branch and mechanical fixes that follow from it | none>.
- Needs the owner's word, exactly these actions: <for example force-push of a PR branch, cancelling CI runs, creating forge issues>. Needs no approval: <for example fetching, reading, tests through the throttle, board updates, retries of calls that are safe to repeat, pushes to PR branches>.
- Working hours: <none | HH:MM–HH:MM timezone>. Outside them: no implementation, commits, pushes, merges or review passes.
- Board: `br`, run from `<directory with .beads/>`. Program label: `<label>`. Landing labels: `<label>` = mainline, `<label>` = integration branch, `<label>` = <other repository>, `<label>` = docs, `<label>` = no code.
- Files: plan `<path>`; decisions `<path>`; briefs `<work>/briefs/<id>.md`; reports `<work>/reports/<id>.md`; verdicts `<work>/verdicts/<id>.md`; Codex briefs and finding tables `<work>/codex/`; Codex artifacts `<path | default>`; gate receipts `<path>/<full-sha>.md`; status file `<work>/<STATUS>.md`; status page `<path | none>`.
- Integration delta check: `<command | git log <seen>..origin/<integration branch>>`.
- Heavy-step throttle: `<command prefix> -- <command>`; at most <n> at once; exit codes that are not test results: <list | none>.
- Migrations: <tool and the single-head check | none>.
- Models: leader <opus>, advisor <fable>, builders and reviewers <opus>, mapping <sonnet>, lookups <haiku>. Codex reviewers: `<gpt-6.1-sol>` (responsibility, contracts, simplicity) and `<gpt-6-astra>` (failure paths, data, security, strongest alternative).
- Public text (code, commits, PRs, comments, docs): never <internal decision numbers, board ids, customer names, internal plan words, reviewer model names>; no AI attribution.
- Secrets: never read or print <files and variables>.
```
