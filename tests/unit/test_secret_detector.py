"""Tests for secret_detector.py."""

from fcode.scanner.secret_detector import detect_secrets, REDACTION_MARKER


def test_api_key_redacted():
    content = 'API_KEY=sk_test_abc123xyz456\nprint("ok")'
    safe, found = detect_secrets(content)
    assert found
    assert REDACTION_MARKER in safe
    assert "sk_test_abc123xyz456" not in safe


def test_secret_keyword_redacted():
    content = 'SECRET=my_super_secret_value_1234\n'
    safe, found = detect_secrets(content)
    assert found
    assert REDACTION_MARKER in safe


def test_token_redacted():
    content = 'TOKEN=ghp_abcdefghijklmnopqrstuvwx\n'
    safe, found = detect_secrets(content)
    assert found


def test_password_redacted():
    content = 'PASSWORD=hunter2\n'
    safe, found = detect_secrets(content)
    assert found


def test_private_key_redacted():
    content = 'PRIVATE_KEY=some_private_key_data_here_xyz\n'
    safe, found = detect_secrets(content)
    assert found


def test_pem_key_redacted():
    content = '-----BEGIN RSA PRIVATE KEY-----\nABCDEF1234\n-----END RSA PRIVATE KEY-----'
    safe, found = detect_secrets(content)
    assert found
    assert REDACTION_MARKER in safe


def test_harmless_string_not_redacted():
    content = 'name = "alice"\ncount = 42\nprint("hello")\n'
    safe, found = detect_secrets(content)
    assert not found
    assert safe == content


def test_line_count_preserved():
    content = 'x = 1\nAPI_KEY=sk_test_long_key_value_here\nz = 3\n'
    safe, found = detect_secrets(content)
    assert found
    assert safe.count("\n") == content.count("\n")


def test_deterministic_marker():
    content = 'API_KEY=sk_test_abcdefghijklmnop\n'
    safe1, _ = detect_secrets(content)
    safe2, _ = detect_secrets(content)
    assert safe1 == safe2


def test_mixed_content():
    content = 'DEBUG = True\nAPI_KEY=sk_test_1234567890abcdef\nSECRET=my_secret_value_12345\nprint("done")\n'
    safe, found = detect_secrets(content)
    assert found
    assert "sk_test_1234567890abcdef" not in safe
    assert "my_secret_value_12345" not in safe
    assert "DEBUG" in safe
    assert "print" in safe
    assert safe.count("\n") == content.count("\n")


def test_no_secrets():
    content = 'def foo():\n    return 42\n'
    safe, found = detect_secrets(content)
    assert not found
    assert safe == content
