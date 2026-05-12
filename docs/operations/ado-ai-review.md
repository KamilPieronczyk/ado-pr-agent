# ADO AI PR Review Operations

## Pre-flight Checklist

- Container App has `AZURE_CLIENT_ID` set to the managed identity's client ID.
- The managed identity principal ID has been added to the Azure DevOps organization as a user with Basic access (see README § Azure DevOps Identity Onboarding).
- The identity has Code (Read) and Pull Request Threads (Read & Write) permissions on the target project.
- For `/ai fix`: the identity has Contribute permission on the target branch.
- ADO service hooks are configured to POST to `https://<container-app>/webhook/ado` with Basic Auth credentials matching `WEBHOOK_USERNAME` / `WEBHOOK_PASSWORD`.
- `ADO_AUTH_MODE` is absent or set to `entra` (default).

## Temporary PAT Fallback (local/test only)

Set `ADO_AUTH_MODE=pat` and `ADO_PAT=<token>` to bypass managed identity. Explicitly for local testing — do not use in production deployments.

## Required Environment Variables

- `AZURE_CLIENT_ID`: managed identity client ID injected by the ARM template.
- `AZURE_OPENAI_BASE_URL`: Azure OpenAI endpoint.
- `AZURE_OPENAI_DEPLOYMENT`: model deployment name.
- `AZURE_OPENAI_API_KEY`: optional; omit to use managed identity for OpenAI auth.
- `WEBHOOK_USERNAME` / `WEBHOOK_PASSWORD`: Basic Auth credentials for the webhook endpoint.

## Commands

- `/ai review`: general code review.
- `/ai security`: security baseline review.
- `/ai fix`: mechanical fixes only.

## Security Boundary

The model never receives a raw shell tool. All write actions (git push, PR comments) are performed by Python code that validates model output first. Secret values detected locally are redacted before any model call.
