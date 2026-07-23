"""Tests for email service — template rendering and email building."""
from datetime import datetime, timezone
from models.subscriber import Subscriber
from models.job import Job


class TestEmailBuilding:
    """Email template and content building tests."""

    def test_build_email_html_renders(self, app, sample_subscriber, sample_jobs):
        """Email HTML template should render without errors."""
        from services.email_service import build_email_html

        with app.app_context():
            html = build_email_html(sample_subscriber, sample_jobs)
            assert html is not None
            assert len(html) > 100
            # Should contain job titles
            assert 'Python' in html or 'React' in html or 'Data' in html
            # Should contain unsubscribe link
            assert 'unsubscribe' in html.lower()

    def test_build_email_text_renders(self, app, sample_subscriber, sample_jobs):
        """Email text template should render without errors."""
        from services.email_service import build_email_text

        with app.app_context():
            text = build_email_text(sample_subscriber, sample_jobs)
            assert text is not None
            assert len(text) > 50

    def test_send_job_alert_no_jobs(self, app, sample_subscriber):
        """Sending alert with no jobs should return success."""
        from services.email_service import send_job_alert

        with app.app_context():
            success, error = send_job_alert(sample_subscriber, [])
            assert success is True  # No-op success
            assert error == ''

    def test_verification_email_renders(self, app, sample_subscriber):
        """Verification email template should render.
        The SMTP connection will fail since no server is running,
        but the error should be a connection error, not a crash."""
        from services.email_service import send_verification_email

        with app.app_context():
            success, error = send_verification_email(sample_subscriber)
            # SMTP is not configured — send should fail cleanly
            assert success is False
            assert isinstance(error, str)
            assert len(error) > 0  # Should have an error message
