"""Email service for sending job alerts with parallel delivery support."""
import smtplib
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
    """Send one email via SMTP — extracted for ThreadPoolExecutor use."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{current_app.config['MAIL_FROM_NAME']} <{current_app.config['MAIL_FROM']}>"
        msg['To'] = to_email
        msg['Reply-To'] = current_app.config['MAIL_FROM']
        msg['X-Priority'] = '1'
        msg['X-Mailer'] = 'Smart Job Alert'
        msg['List-Unsubscribe'] = f"<mailto:{current_app.config['MAIL_FROM']}?subject=unsubscribe>"

        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        smtp_host = current_app.config['SMTP_SERVER']
        smtp_port = current_app.config['SMTP_PORT']

        # Force IPv4 resolution — Render doesn't route outbound IPv6,
        # and smtp.gmail.com resolves to an IPv6 address by default.
        addr_info = socket.getaddrinfo(smtp_host, smtp_port, socket.AF_INET, socket.SOCK_STREAM)
        ipv4_addr = addr_info[0][4][0]

        with smtplib.SMTP(ipv4_addr, smtp_port, timeout=10) as server:
            server.ehlo(smtp_host)  # explicit EHLO since we're connecting by IP, not hostname
            server.starttls()
            server.ehlo(smtp_host)
            if current_app.config['SMTP_USERNAME']:
                server.login(
                    current_app.config['SMTP_USERNAME'],
                    current_app.config['SMTP_PASSWORD']
                )
            server.send_message(msg)

        log_event('EMAIL_SENT', f'Email sent to {to_email}')
        return (to_email, True, '')
    except Exception as e:
        error_msg = str(e)
        log_event('EMAIL_FAILED', f'Failed to send email to {to_email}: {error_msg}', 'error')
        logger.error(f'Email send error for {to_email}: {e}')
        return (to_email, False, error_msg)

    
def send_email(to_email, subject, html_body, text_body=''):
    """Send an email via SMTP (single send — backward compatible)."""
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
