# Gate receipt: PR <number>, head <full-sha>

Save as `<receipts>/<full-sha>.md` (path from the project profile). Merge only when every line is ticked and the head matches the SHA the merge is pinned to. New commit, new receipt.

- [ ] CI green on the head, including required checks: <link or run id>
- [ ] Review bot, if the project has one, has reviewed exactly this head, no findings: <review reference>
- [ ] First Codex reviewer green on the final diff: <session, artifact, reviewed head = this head, `content_drift=false`>
- [ ] Second Codex reviewer green on the final diff: <session, artifact, reviewed head = this head, `content_drift=false`>
- [ ] The lenses the review protocol's depth requires have reported; no reviewer stands as "not covered": <which lenses, on which SHA; for an older SHA: why the report still holds>
- [ ] The builder's stack check, or what the review protocol prescribes instead (docs: not applicable; tests only: repeated runs): <result, SHA, where the evidence is>
- [ ] The leader's stack check in its own stack, or what the review protocol prescribes instead: <result, SHA, where the evidence is>
- [ ] PR text and labels meet the project's PR rules
- [ ] Not a branch or PR the project profile excludes from our merges
- [ ] Every finding from every review has a verdict (true and fixed, rejected with reason, or follow-up on the board)

Notes:
