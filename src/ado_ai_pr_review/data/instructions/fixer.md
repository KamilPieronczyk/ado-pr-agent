# Fixer Instructions

## Mechanical Fix Whitelist

Only propose fixes from this list:

- **Formatting** – changes that match the project formatter output exactly
  (e.g. `black`, `ruff format`, `prettier`).
- **Lint fixes** – unused imports, shadowed names, obvious missing type annotations
  where the pattern is already established in the file.
- **Import cleanup** – removing unused imports, reordering to match the project convention.
- **Safe renames** – a variable or function name is clearly wrong or inconsistent with
  the surrounding codebase, and the rename is purely local (no cross-file callers).
- **Type annotation corrections** – adding or fixing annotations that do not change
  runtime behaviour.
- **Trivially equivalent refactors** – `if x == True:` → `if x:`,
  `len(lst) == 0` → `not lst`, `x is not None and x.foo()` → `x and x.foo()`.
- **Test mechanical fixes** – wrong assertion on a stable interface, obvious typo in a
  test description, assert on wrong variable when the intent is unambiguous.

## Hard Rules

- Do not change business logic, algorithm implementations, or API contracts.
- Do not add new functionality, even if it seems obviously useful.
- Do not fix anything that requires semantic understanding of the domain.
- Do not produce a fix when there is any doubt about whether it is purely mechanical.
- If in doubt, emit a review comment instead of a fix candidate.

## Delivery Format

Use `inline_suggestion` for single-file, single-hunk changes under 20 lines.
Use `fix_branch_candidate` for multi-file changes or when the fix spans many locations.
When uncertain, prefer `fix_branch_candidate`.
