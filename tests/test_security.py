from ado_ai_pr_review.security import SecurityScanner


def test_security_scanner_reports_secret_without_value() -> None:
    scanner = SecurityScanner()

    findings, redacted = scanner.scan_diff("+ API_KEY = 'sk-test-secret-value-1234567890'\n")

    assert findings[0].type == "security"
    assert "secret" in findings[0].title.lower()
    assert "sk-test-secret-value" not in findings[0].body
    assert "[REDACTED_SECRET]" in redacted
