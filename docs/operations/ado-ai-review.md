# ADO AI PR Review Operations

## Required Azure DevOps Settings

- The pipeline must run as a PR branch policy so `System.PullRequest.*` variables are populated.
- The checkout step must use `persistCredentials: true`.
- Scripts must be allowed to access `System.AccessToken`.
- The project build service identity needs code read permission to review PRs.
- To publish comments, the build service identity needs pull request contribute/comment permissions.
- To create bootstrap commits or fix branches, the build service identity needs branch contribute permission.

## Required Variables

- `AZURE_OPENAI_BASE_URL`: Azure OpenAI or Foundry v1 base URL ending in `/openai/v1/`.
- `AZURE_OPENAI_DEPLOYMENT`: model deployment name.
- `AZURE_OPENAI_API_KEY`: optional when Microsoft Entra authentication is configured.

## Commands

- `/ai review`: general code review.
- `/ai security`: security baseline review.
- `/ai fix`: mechanical fixes only.

## Security Boundary

The model never receives a raw shell tool. It can only request typed review outputs. All local CLI operations are controlled by Python code, command allowlists, timeouts, output caps, and secret redaction.
