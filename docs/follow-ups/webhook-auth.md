# Follow-up: Webhook Endpoint Authentication

**Date:** 2026-05-09
**Status:** Implemented — Option A (Basic Auth) shipped in feat/adapter-layer

## Problem

The `/webhook/ado` endpoint currently has **no incoming request authentication**.

The server checks that `ADO_AUTH_TOKEN` is configured (server-side credential used to call
ADO REST API), but it does NOT verify that the incoming HTTP request actually came from
Azure DevOps. Any caller who can reach the Container Apps URL can POST a crafted payload and
trigger a review — consuming OpenAI tokens and potentially reading repository contents.

Relevant code: `src/ado_ai_pr_review/webhook_server.py`, `handle_ado_webhook()`.

## Options

### Option A — ADO Service Hook Basic Auth (recommended)

When creating a service hook in ADO, you can configure **Basic authentication** credentials
(username + password) that ADO sends in the `Authorization` header of every webhook POST.

Implementation:
1. Read `WEBHOOK_USERNAME` and `WEBHOOK_PASSWORD` from env vars at startup.
2. In `handle_ado_webhook()`, extract the `Authorization` header, decode the Base64
   credentials, and compare to the configured values using `secrets.compare_digest`.
3. Return `HTTP 401` if missing or incorrect.

ADO configuration: *Project Settings → Service hooks → edit subscription → Authentication*.

Pros: Native ADO feature, zero changes to payload format, works out of the box.
Cons: Password sent on every request (mitigated by HTTPS); credentials must be rotated
manually; no replay protection.

### Option B — HMAC Signature

Azure DevOps does **not** natively sign webhook payloads with HMAC (unlike GitHub).
This option would require a proxy or Azure API Management policy in front of the Container
App to add a signature header before forwarding.

Pros: Cryptographically strong, replay-safe with timestamp validation.
Cons: Requires additional infrastructure; ADO has no built-in HMAC support.

### Option C — IP Allowlist via Container Apps Ingress Rules

Restrict inbound traffic to Azure DevOps IP ranges using Container Apps ingress IP security
restrictions. Azure DevOps publishes its service tag (`AzureDevOps`) which can be used in
Azure networking rules.

Pros: Network-layer defense; no code change needed.
Cons: IP ranges can change; does not prevent abuse from compromised ADO tenant; Container
Apps ingress rules require infrastructure-level configuration.

### Option D — Shared Secret Header

Add a custom `X-ADO-AI-Secret` header requirement. Configure the same secret in ADO service
hook custom headers (supported via the "HTTP Header" field in the service hook subscription)
and in the `WEBHOOK_SECRET` env var.

Implementation: similar to Option A but uses a custom header instead of `Authorization`.

Pros: Simple, stateless, easy to rotate via env var.
Cons: Same replay-protection gap as Basic Auth; custom headers must be added manually per
service hook subscription.

## Recommended Path

Implement **Option A** (Basic Auth) as the first fix — it requires only ~20 lines of code
and uses a built-in ADO feature. Add **Option C** (IP allowlist) as a defense-in-depth
layer at the infrastructure level.

## Implementation Sketch (Option A)

```python
# webhook_server.py additions

import base64
import secrets

_WEBHOOK_USERNAME = os.getenv("WEBHOOK_USERNAME", "")
_WEBHOOK_PASSWORD = os.getenv("WEBHOOK_PASSWORD", "")

def _verify_basic_auth(request: Request) -> None:
    if not _WEBHOOK_USERNAME or not _WEBHOOK_PASSWORD:
        return  # not configured — skip (allows gradual rollout)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        raise HTTPException(status_code=401, detail="Missing credentials")
    try:
        decoded = base64.b64decode(auth_header[6:]).decode()
        username, _, password = decoded.partition(":")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    ok = secrets.compare_digest(username, _WEBHOOK_USERNAME) and \
         secrets.compare_digest(password, _WEBHOOK_PASSWORD)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/webhook/ado")
async def handle_ado_webhook(payload: AdoWebhookPayload, request: Request) -> dict[str, str]:
    _verify_basic_auth(request)
    ...
```

Environment variables to add to Container Apps:
- `WEBHOOK_USERNAME` — any non-empty string, e.g. `ado-ai`
- `WEBHOOK_PASSWORD` — random secret, e.g. `openssl rand -hex 32`

ADO service hook setup: *Authentication type: Basic*, fill in the same username/password.

## Related Files

- `src/ado_ai_pr_review/webhook_server.py` — endpoint to modify
- `src/ado_ai_pr_review/adapters/webhook.py` — `AdoWebhookAdapter`, `AdoWebhookPayload`
- `docs/research-azure-marketplace-managed-app.md` — deployment target context
