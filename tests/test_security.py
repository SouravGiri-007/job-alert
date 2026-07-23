"""Tests for security features: input validation, CSRF, passwords."""
from models.admin import AdminUser
from routes.main import EMAIL_REGEX
from extensions import db
import re


class TestEmailValidation:
    """Email regex validation tests."""

    def test_valid_emails(self):
        valid = [
            'user@example.com',
            'user.name+tag@example.co.in',
            'user_name@sub.example.com',
            'user-name@example.org',
        ]
        for email in valid:
            assert EMAIL_REGEX.match(email), f'{email} should be valid'

    def test_invalid_emails(self):
        invalid = [
            '',
            'not-an-email',
            '@example.com',
            'user@',
            'user@.com',
            'a@b.c',  # Single-char TLD
            '<script>@example.com',
            'user@<script>.com',
        ]
        for email in invalid:
            assert not EMAIL_REGEX.match(email), f'{email} should be invalid'


class TestFieldValidation:
    """Input field validation tests."""

    def test_reject_html_in_fields(self):
        from routes.main import _validate_field
        from flask import Flask, flash
        import tempfile

        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test'
        app.secret_key = 'test'

        with app.test_request_context():
            result = _validate_field('<script>alert(1)</script>', 'Role')
            assert result is None  # Should be rejected

            result = _validate_field('Normal Role', 'Role')
            assert result == 'Normal Role'  # Should pass

    def test_reject_oversized_fields(self):
        from routes.main import _validate_field
        from flask import Flask

        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test'
        app.secret_key = 'test'

        with app.test_request_context():
            result = _validate_field('a' * 600, 'Role', max_length=500)
            assert result is None  # Too long

            result = _validate_field('a' * 100, 'Role', max_length=500)
            assert len(result) == 100  # Should pass


class TestPasswordSecurity:
    """Password hashing tests."""

    def test_bcrypt_hashing_works(self, db):
        admin = AdminUser(username='security_test')
        admin.set_password('MySecureP@ss1')

        # Verify the hash is not the plaintext
        assert admin.password_hash != 'MySecureP@ss1'
        assert admin.password_hash.startswith('$2b$')  # bcrypt prefix

        # Correct password matches
        assert admin.check_password('MySecureP@ss1') is True

        # Wrong password does not match
        assert admin.check_password('wrong') is False
        assert admin.check_password('MySecureP@ss1!') is False

    def test_empty_hash_returns_false(self, db):
        admin = AdminUser(username='no_hash')
        admin.password_hash = ''
        assert admin.check_password('anything') is False


class TestCSRFProtection:
    """CSRF protection tests — disabled in test config, but verify the extension loads."""

    def test_csrf_extension_loaded(self, app):
        assert 'csrf' in app.extensions

    def test_csrf_token_available_in_templates(self, client):
        # CSRF is disabled in test config (WTF_CSRF_ENABLED=False),
        # but verify the app doesn't crash when csrf_token is called
        resp = client.get('/admin/login')
        assert resp.status_code == 200
