from ado_ai_pr_review.security import SecurityScanner


def test_security_scanner_reports_secret_without_value() -> None:
    scanner = SecurityScanner()

    findings, redacted = scanner.scan_diff("+ API_KEY = 'sk-test-secret-value-1234567890'\n")

    assert findings[0].type == "security"
    assert "secret" in findings[0].title.lower()
    assert "sk-test-secret-value" not in findings[0].body
    assert "[REDACTED_SECRET]" in redacted


def test_security_scanner_detects_aws_access_key() -> None:
    scanner = SecurityScanner()

    findings, redacted = scanner.scan_diff("+ AWS_ACCESS_KEY_ID = AKIAIOSFODNN7EXAMPLE\n")

    assert any("secret" in f.title.lower() for f in findings)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted


def test_security_scanner_detects_github_pat() -> None:
    scanner = SecurityScanner()

    findings, redacted = scanner.scan_diff("+ token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456abcd\n")

    assert any("secret" in f.title.lower() for f in findings)
    assert "ghp_" not in redacted


def test_security_scanner_detects_pem_private_key() -> None:
    scanner = SecurityScanner()

    findings, redacted = scanner.scan_diff("+ -----BEGIN RSA PRIVATE KEY-----\n")

    assert any("secret" in f.title.lower() for f in findings)
    assert "-----BEGIN RSA PRIVATE KEY-----" not in redacted
