from ado_ai_pr_review.redaction import SecretRedactor


def test_secret_redactor_replaces_configured_secret() -> None:
    redactor = SecretRedactor(secrets=["abc123"])

    assert redactor.redact("token=abc123") == "token=[REDACTED]"


def test_secret_redactor_replaces_known_token_patterns() -> None:
    redactor = SecretRedactor()

    text = "openai=sk-abcdefghijklmnopqrstuvwxyz github=ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"
    redacted = redactor.redact(text)

    assert "sk-" not in redacted
    assert "ghp_" not in redacted
    assert redacted.count("[REDACTED]") == 2


def test_secret_redactor_handles_empty_values() -> None:
    redactor = SecretRedactor(secrets=["", "   ", "real-secret"])

    assert redactor.redact("real-secret visible") == "[REDACTED] visible"
