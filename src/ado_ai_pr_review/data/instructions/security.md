# Security Instructions

## Security Checklist

For every PR diff, check each category:

1. **Secrets** – API keys, tokens, passwords, certificates, or any credential in code or config.
2. **Injection** – SQL, shell command, LDAP, XPath, template injection in user-controlled input.
3. **Authentication** – Endpoints or operations that require authentication actually enforce it.
4. **Authorization** – Users cannot access or modify resources they do not own; checks happen
   server-side, not only client-side.
5. **Input validation** – External inputs are validated at the boundary before processing or storage.
6. **Unsafe deserialization** – No untrusted data deserialized into live objects without type checks.
7. **Sensitive data handling** – PII, tokens, and secrets are not logged, returned in errors,
   cached in plain text, or stored without encryption.

## Severity Guide

- **critical**: Direct exploit path — injection with user control, exposed credential, auth bypass.
- **high**: Privilege escalation, sensitive data leak, missing authz on a write endpoint.
- **medium**: Defence-in-depth gap, missing validation on a non-critical path, risky pattern.
- **low**: Hardening suggestion, informational observation.

## Hard Constraint

Never include secret values in findings, explanations, or suggested code.
Report only location (file path, line range) and risk type.
