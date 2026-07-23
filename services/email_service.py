"""Email service for sending job alerts via Resend API with parallel delivery support."""
import resend
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import render_template, current_app
from utils.logger import get_logger, log_event

logger = get_logger('email_service')


def build_email_html(subscriber, jobs):
    """Build HTML email body for job alerts."""
    return render_template(
        'emails/job_alert.html',
        subscriber=subscriber,
        jobs=jobs,
        app_name=current_app.config['APP_NAME'],
        app_url=current_app.config['APP_URL'],
    )


def build_email_text(subscriber, jobs):
    """Build plain text email body for job alerts."""
    return render_template(
        'emails/job_alert.txt',
        subscriber=subscriber,
        jobs=jobs,
        app_name=current_app.config['APP_NAME'],
        app_url=current_app.config['APP_URL'],
    )


def _send_single(to_email, subject, html_body, text_body=''):
    """Send one email via Resend API."""
    api_key = current_app.config.get('RESEND_API_KEY', '')
    if not api_key:
        log_event('EMAIL_FAILED', f'Resend API key not configured. Cannot send to {to_email}.', 'error')
        return (to_email, False, 'RESEND_API_KEY not set')

    try:
        resend.api_key = api_key

        sender = f"{current_app.config['MAIL_FROM_NAME']} <{current_app.config['MAIL_FROM']}>"

        params = {
            "from": sender,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }

        if text_body:
            params["text"] = text_body

        response = resend.Emails.send(params)
        log_event('EMAIL_SENT', f'Email sent to {to_email} (id: {response.get("id", "unknown")})')
        return (to_email, True, '')
    except Exception as e:
        error_msg = str(e)
        log_event('EMAIL_FAILED', f'Failed to send email to {to_email}: {error_msg}', 'error')
        logger.error(f'Email send error for {to_email}: {e}')
        return (to_email, False, error_msg)


def send_email(to_email, subject, html_body, text_body=''):
    """Send an email via Resend API (single send)."""
    _, success, error = _send_single(to_email, subject, html_body, text_body)
    return success, error


def send_verification_email(subscriber):
    """Send verification email to a new subscriber."""
    verify_url = f"{current_app.config['APP_URL']}/verify/{subscriber.verification_token}"
    html = render_template(
        'emails/verify_email.html',
        subscriber=subscriber,
        verify_url=verify_url,
        app_name=current_app.config['APP_NAME'],
    )
    text = render_template(
        'emails/verify_email.txt',
        subscriber=subscriber,
        verify_url=verify_url,
        app_name=current_app.config['APP_NAME'],
    )
    return send_email(
        subscriber.email,
        f'Verify your {current_app.config["APP_NAME"]} subscription',
        html,
        text
    )


def send_job_alert(subscriber, jobs):
    """Send job alert email to subscriber."""
    if not jobs:
        return True, ''
    html = build_email_html(subscriber, jobs)
    text = build_email_text(subscriber, jobs)
    return send_email(
        subscriber.email,
        f'{len(jobs)} new jobs matching your preferences',
        html,
        text
    )


def send_job_alerts_parallel(subscribers_with_jobs, max_workers=4):
    """Send multiple job alerts in parallel using a thread pool.

    Args:
        subscribers_with_jobs: list of (subscriber, jobs_list) tuples
        max_workers: number of parallel threads (default: 4)

    Returns:
        (sent_count, failed_count)
    """
    sent = 0
    failed = 0

    def _send(subscriber, jobs):
        success, _ = send_job_alert(subscriber, jobs)
        return success

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_send, sub, jobs): sub.email
            for sub, jobs in subscribers_with_jobs
        }
        for future in as_completed(futures):
            if future.result():
                sent += 1
            else:
                failed += 1

    return sent, failed


def send_unsubscribe_confirmation(subscriber):
    """Send confirmation after unsubscribe."""
    html = render_template(
        'emails/unsubscribed.html',
        subscriber=subscriber,
        app_name=current_app.config['APP_NAME'],
    )
    return send_email(
        subscriber.email,
        f'You have been unsubscribed from {current_app.config["APP_NAME"]}',
        html
    )
