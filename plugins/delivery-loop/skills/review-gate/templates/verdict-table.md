# Verdicts <id>: head <sha>

Save as `<work>/verdicts/<id>.md`. One row per finding ID from every review (Codex, review bot, CI, lenses). Finding IDs stay stable across passes.

| Finding ID | Source (reviewer, pass) | SHA | Claim | Verdict | Evidence | Where the fix lives |
|---|---|---|---|---|---|---|
| <F1> | <reviewer, commit-gate 1> | <sha> | <one line> | true / rejected (reason) / follow-up / owner question | <file:line or check output> | <this delivery, commit sha / board item / owner question> |

Verdicts: **true** (verified, in scope, smallest fix applied), **rejected** (not proven, with the reason), **follow-up** (real but owned elsewhere: board item with the evidence), **owner question** (a product or contract choice).

## Not covered
<Reviewers or lenses that failed or timed out, on which SHA. They never count as green.>

## Disagreements
<Where the reviewers contradicted each other, and the evidence that decided it.>
