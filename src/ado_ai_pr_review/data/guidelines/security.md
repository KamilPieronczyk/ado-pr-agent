# Security Guidelines

> This is the default placeholder. Replace or extend it with your team's actual security requirements.
> Reference this file from `.ado-ai-review.yml` under `guidelines.security`.

## Baseline Requirements

- All external inputs must be validated and sanitized before processing or storage.
- Secrets must never appear in logs, error messages, API responses, or test fixtures.
- Use parameterized queries or ORM-level escaping for all database access.
- Enforce authentication and authorization at every API endpoint — never rely solely on
  client-side checks.

## Dependencies

- Review newly added dependencies for known CVEs before merging.
- Pin dependency versions in production manifests.
- Avoid transitive dependencies on abandoned or unreviewed packages for security-sensitive paths.

## Secrets Management

- Store credentials in environment variables or a secrets manager. Never commit them.
- Rotate credentials immediately if accidentally exposed.
- Treat anything in `.env` files as a local-only convenience; never commit `.env`.

## Sensitive Data

- Do not log PII (names, emails, IDs) in production log levels.
- Store passwords hashed with a modern algorithm (bcrypt, argon2). Never plain text or MD5/SHA1.
- Encrypt sensitive fields at rest if the database does not provide full-disk encryption.
