# Indexer Instructions

## Goal

Produce a short, accurate description of each file so the reviewer can decide whether
to load it as context for the current PR.

## Description Format

Two sentences maximum:
1. What the file does or contains.
2. What domain, layer, or role it belongs to (e.g. "API handler", "domain model",
   "database migration", "CI pipeline configuration", "test fixture").

## Tags

Apply every relevant tag from this set:

- `business` – core domain logic, entities, aggregates, use cases, business rules.
- `tests` – test files, fixtures, test utilities, test configuration.
- `security` – authentication, authorization, encryption, secret handling, input validation.
- `api` – HTTP handlers, serializers, route definitions, protocol adapters.
- `domain` – value objects, aggregates, domain events, domain services.
- `config` – environment loading, application configuration, feature flags, infrastructure config.
- `docs` – documentation, ADRs, specs, changelogs.

## Relevance Hints

Flag a file as relevant to the current PR if:
- It defines a type, class, or function that the diff directly modifies or calls.
- It contains tests for code touched by the diff.
- It enforces a security policy that the diff may bypass or weaken.
- It provides domain context that a reviewer would need to judge correctness.

## Exclusions

Do not index build outputs, vendored dependencies, lock files, generated protobuf/OpenAPI files,
or binary assets. Respect the `exclude` patterns from the config.
