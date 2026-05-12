# Context Isolation and Structured Logging

This document describes the context isolation and structured logging features that ensure secure, traceable execution of pull request reviews.

## Request IDs

Every pull request review is assigned a unique request ID that is propagated through all log messages and available to callers for end-to-end tracing.

### Local Mode

In local mode (CLI), request IDs are generated at the start of each `ado-ai-pr-review local` invocation with the format:
```
local-{16 hex chars}
```

Example: `local-abc123def456789f`

### Webhook Mode

In webhook mode, request IDs are read from the incoming HTTP request headers:
- **`X-Request-ID`** — preferred header for custom request IDs
- **`X-Correlation-ID`** — fallback if `X-Request-ID` is not present

If neither header is provided, a request ID is auto-generated with the format:
```
ado-pr-{pr_id}-{16 hex chars}
```

Example: `ado-pr-42-0123456789abcdef`

### Request ID Storage and Propagation

The request ID is stored in `PRContext.request_id` and is automatically included in every log message emitted during the request lifecycle. This allows complete tracing of a single review from start to finish.

## X-Request-ID / X-Correlation-ID Headers

External callers (Azure DevOps service hooks, monitoring systems, load balancers) can pass either header to set a custom request ID:

```bash
curl -X POST https://your-container-app/webhook/ado \
  -H "X-Request-ID: my-custom-id-12345" \
  -H "Content-Type: application/json" \
  -d '{"...": "..."}'
```

Or using `X-Correlation-ID`:

```bash
curl -X POST https://your-container-app/webhook/ado \
  -H "X-Correlation-ID: my-correlation-id" \
  -H "Content-Type: application/json" \
  -d '{"...": "..."}'
```

### Response Includes Request ID

The webhook returns the request ID in the response body, allowing callers to correlate the entire end-to-end flow:

```json
{"status": "accepted", "request_id": "ado-pr-42-0123456789abcdef"}
```

Callers can use this ID to query logs, trace request flow, and correlate multiple operations across their infrastructure.

## Workspace Boundary Rules

All file operations are constrained to a single workspace (the cloned repository). This prevents accidental or malicious access to files outside the intended scope.

### Safe Read Operations

All repository file reads (guidance files, context files, indexed files) go through `WorkspaceBoundary.safe_read_text()`. This ensures:
- No parent traversal using `../`
- No absolute paths outside the workspace root
- No symlinks that point outside the workspace

If any file violates these rules, a `WorkspaceBoundaryError` is raised. The offending file or candidate is skipped and logged. Review proceeds with the remaining valid files.

### Safe Write Operations

All fix writes go through `WorkspaceBoundary.safe_write_text()`, applying the same constraints:
- Rejects parent traversal (`../`)
- Rejects absolute paths outside the workspace
- Rejects symlinks that could escape to another cloned repository

## JSON Log Fields

Log output is structured as JSON, with each line containing a complete log record. This enables:
- Machine-readable parsing in log aggregation systems
- Filtering and querying by request ID, level, logger, etc.
- Correlation of logs across distributed infrastructure

### Standard Log Fields

Each log line contains these fields:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 | Date and time in UTC, e.g. `2026-05-12T10:00:00.000Z` |
| `level` | string | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logger` | string | Logger name, e.g. `ado_ai_pr_review.engine` |
| `message` | string | Log message |
| `request_id` | string | Request ID for tracing |

### Extra Fields

Any additional context is included as extra fields in the same JSON object. Examples:
- `command`: The command being executed (`review`, `security`, `fix`)
- `pr_id`: The pull request ID
- `findings_count`: Number of review findings
- `duration_ms`: Execution time in milliseconds

### Exception Fields

When an exception occurs, the following fields are added:

| Field | Type | Description |
|-------|------|-------------|
| `exc_type` | string | Exception class name |
| `traceback` | string | Full traceback (secrets redacted) |

### Example Log Line

```json
{"timestamp": "2026-05-12T10:00:00.000Z", "level": "INFO", "logger": "ado_ai_pr_review.engine", "message": "review metrics", "request_id": "local-abc123def456", "command": "review", "pr_id": 0, "findings_count": 3}
```

Another example with exception:

```json
{"timestamp": "2026-05-12T10:00:15.123Z", "level": "ERROR", "logger": "ado_ai_pr_review.engine", "message": "review failed", "request_id": "local-abc123def456", "command": "review", "pr_id": 0, "exc_type": "ValueError", "traceback": "Traceback (most recent call last):\n  File \"engine.py\", line 42, in review\n    ..."}
```

## Secret Redaction

Sensitive data is automatically redacted from all log output to prevent accidental exposure of credentials.

### Configured Secrets

Any secrets passed to `CliRunner(secrets=[...])` are replaced with `[REDACTED]` in all log output:
- Log messages
- Extra field values (string values only)
- Exception tracebacks

### Default Patterns

The following patterns are **always redacted** even if not explicitly configured:

| Pattern | Example | Replaced With |
|---------|---------|---|
| OpenAI API keys | `sk-proj-abc123...` | `[REDACTED]` |
| GitHub tokens | `ghp_abc123...` | `[REDACTED]` |
| AWS access keys | `AKIA...` | `[REDACTED]` |
| Azure connection strings | `DefaultEndpointsProtocol=https;...` | `[REDACTED]` |
| PEM private keys | `-----BEGIN PRIVATE KEY-----...` | `[REDACTED]` |

Example log with redaction:

```json
{"timestamp": "2026-05-12T10:00:00.000Z", "level": "INFO", "logger": "ado_ai_pr_review.engine", "message": "authenticating with token [REDACTED]", "request_id": "local-abc123def456"}
```

## Filtering Container Apps Logs by Request ID

When running in Azure Container Apps, logs are captured in Azure Monitor / Log Analytics. Use the following Kusto Query Language (KQL) query to trace a single review:

```kusto
ContainerAppConsoleLogs
| where ContainerName == "ado-ai-pr-review"
| extend parsed = parse_json(Log)
| where parsed.request_id == "ado-pr-42-0123456789abcdef"
| project TimeGenerated, parsed.level, parsed.message, parsed
| order by TimeGenerated asc
```

This query:
1. Filters to the `ado-ai-pr-review` container
2. Parses each log line as JSON
3. Filters to a specific request ID
4. Projects relevant columns for viewing
5. Orders by timestamp for chronological review

You can modify the request ID to trace any specific review. Each log entry includes all context (command, PR ID, findings, etc.) for complete end-to-end visibility.
