# Engineering principles

When you build features, fix defects or refactor, improve the system's ability to meet its requirements and to stay understandable, reliable and changeable over time. Judge quality by clear responsibilities, understandable contracts, low cost of change and verifiable behaviour. Scale analysis, documentation and tests to the task's complexity and consequences.

## 1. Start from the purpose and the actual implementation
- Understand which problem the task solves, which observable behaviour is needed and which existing properties must be preserved.
- Follow the affected use cases and data flows until you know their owners and dependencies. Keep implemented, decided and assumed apart.
- Check the plan's technical assumptions. When code and plan disagree, describe the difference and its consequence. Respect decided goals, contracts and migration steps; propose a change when new evidence justifies it.

## 2. Give every coherent responsibility a clear owner
- Put rules and knowledge where they belong. Avoid long-lived parallel implementations of the same decision.
- Interfaces should require as little knowledge of the inside as possible. A responsibility handles the coordination and rules that belong to its own task.
- Keep together what shares knowledge and changes together. Keep apart responsibilities that mean different things or evolve independently.
- Use the same domain words everywhere (the project's glossary). Make contracts, states, side effects and failure outcomes explicit.

## 3. Refactor when the feature needs a better structure
- Make necessary, bounded refactors within the task, especially when a local solution would otherwise duplicate a rule, bypass the right owner, create a parallel path or force several callers to coordinate the same internal details.
- Justify it by the concrete flaw that disappears and what becomes easier to understand, change or verify. A larger diff can be right when it improves the responsibility involved.
- Keep unrelated cleanup out. Separate behaviour-preserving changes from intentional behaviour changes (separate commits).

## 4. Reuse and generalise with a clear purpose
For a new or extended abstraction you should be able to answer: which responsibility it encapsulates, what callers no longer need to know, which existing or decided needs it supports, and what complexity it adds. Similar code is not necessarily the same responsibility. Make real variation (organisation, resource, provider, environment) explicit in existing configuration or policy data; keep stable rules in code.

## 5. Use patterns with judgment
DDD, SOLID, clean architecture and other patterns are tools, not goals. Use them when they explain the domain, gather a responsibility, reduce harmful dependencies or handle a concrete need for variation. Central rules should be understandable and testable without the whole app or real external services. New layers, interfaces, queues and services are justified by actual benefit and cost. For a significant design decision, compare two reasonable alternatives against a concrete scenario, and write briefly why the choice was made and what would justify revisiting it (template: decision record in `review-gate`).

## 6. Own data and its lifecycle
When something is created, copied, derived or stored: settle ownership, access, copies, caches, retention, deletion and external recipients. Keep requested, in-progress and confirmed results apart where it affects correctness. For side effects, consider timeout, interruption, retry, duplication and concurrency, and how incomplete work is detected. When a contract changes, plan the transition for existing data, clients and work in progress, and retire old paths once the transition is done.

## 7. Verify both the behaviour and the assumptions
- Choose checks that test the requirements and the important failure paths. Start with a test that shows the defect or the requirement.
- For a decisive uncertainty, write down the assumption and the cheapest check that could prove it wrong.
- Tests follow requirements and contracts, not the implementation's inner structure.
- An important architectural property that must survive gets a proportionate automatic check. Write down what the check covers and what it does not.
- Verification (built right) is not enough on its own. Validation (built the right thing) needs a real scenario: a real identity provider, an administrator who understands the setting, the real end-to-end path running.

## 8. Leave understandable code and the decisions the next developer needs
Clear names. Contracts, side effects and the reasons behind unexpected decisions are documented close to the code. Update affected documentation. Remove replaced code and outdated instructions. Make the purpose and retirement of transitional solutions clear.

## Lenses from the books (use the one that fits)
| Book | Question to ask |
|---|---|
| A Philosophy of Software Design (Ousterhout) | Is the module deep: small interface, much hidden? Where does knowledge spread (change amplification, cognitive load, unknown unknowns)? Can the error be defined away? Did we design it twice? |
| Modern Software Engineering (Farley) | Which hypothesis are we testing, and which small experiment gives fast feedback? Can it be tested without the whole system? |
| Building Evolutionary Architectures (Ford et al.) | Which architectural property must survive, and which automatic check (fitness function) protects it? |
| Software Architecture: The Hard Parts (Ford et al.) | Which forces argue for splitting or joining? Strict or loose contract? Who owns the data? Which trade-off are we making, and what does it cost? |
| Designing Data-Intensive Applications (Kleppmann) | Who owns the data and its derivations? What happens on timeout, duplicate, partial failure, concurrency and schema change? What does "done" mean? |

## Overbuilding guard
- No new mechanism, setting or abstraction unless it removes a demonstrated problem. "Might be good later" becomes a note on the board, not code.
- No interface with one implementation, no speculative configuration, no scaffolding for later steps.
- If fix rounds keep producing findings about the previous fix, cut smaller instead of adding passes.

**Final check:** does the next relevant change become easier to understand, carry out and verify, while today's requirements are met?
