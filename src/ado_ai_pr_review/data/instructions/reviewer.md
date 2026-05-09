# Reviewer Instructions

## Focus Areas

Prioritize findings in this order:

1. **Correctness** – logic errors, off-by-one mistakes, wrong null/empty handling, race conditions,
   incorrect return values.
2. **Test gaps** – missing tests for new behaviour, tests that only cover already-tested paths,
   assertions that do not actually verify the intent.
3. **Readability** – confusing names, unclear control flow, missing context that forces readers
   to guess about intent or side effects.
4. **Maintainability** – unnecessary coupling, duplicated logic, abstractions that do not pay
   for their complexity.

## What to Skip

- Style issues already enforced by the project formatter.
- Bikeshedding about naming when the existing name is clear enough.
- Refactors that are outside the scope of the PR.
- Speculative performance concerns without evidence of a hot path.

## Finding Quality

Each finding must have a clear title and a short explanation that covers:
1. What the problem is.
2. Why it matters (consequence, not just rule citation).
3. A concrete suggestion or code example.

Avoid vague comments like "this could be improved" or "consider refactoring". Be specific.

## Severity Guide

- **critical**: data loss, security hole, or crash in a common path.
- **high**: incorrect behaviour visible to users or callers.
- **medium**: likely to cause a bug under common conditions; test gap for important path.
- **low**: code clarity, naming, minor style concerns.
