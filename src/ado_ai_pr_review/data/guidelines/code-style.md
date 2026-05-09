# Code Style Guidelines

> This is the default placeholder. Replace or extend it with your project's actual style guide.
> Reference this file from `.ado-ai-review.yml` under `guidelines.code_style`.

## General Principles

- Prefer clarity over cleverness. Write code for the next reader.
- Follow the project formatter; do not argue with its output.
- Use consistent naming conventions throughout the codebase.
- Comments explain *why*, not *what*. The code explains what.

## Naming

- Use the conventions already established in the file you are editing.
- Avoid abbreviations unless they are universally understood in the domain (e.g. `id`, `url`).

## Error Handling

- Fail fast at system boundaries; handle errors at the layer where you have enough context
  to recover or report meaningfully.
- Do not swallow exceptions silently.
- Prefer specific exception types over bare `except Exception`.

## Tests

- Each test covers one behaviour. One assertion per test is a good heuristic.
- Test names describe the scenario: `test_returns_empty_list_when_no_files_exist`.
- Prefer real objects over mocks when the cost is low.
