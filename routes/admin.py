"""Admin routes — login, dashboard, subscribers, jobs, email history, scraper history, logs.
Uses database-backed AdminUser with bcrypt password hashing and rate-limited login.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, limiter
from models.admin import AdminUser
from models.subscriber import Subscriber
from models.job import Job
from models.email_history import EmailHistory
from models.scraper_history import ScraperHistory
from utils.helpers import flash_success, flash_error, format_datetime, format_duration
from utils.logger import log_event, get_logger
from services.stats_service import (
    get_dashboard_stats,
    get_subscriber_growth_data,
    get_email_chart_data,
    get_source_distribution,
    get_recent_emails,
    get_recent_scrapes,
    get_scraper_health,
)
import csv as csv_module
from io import StringIO
from datetime import datetime, timezone, timedelta

admin_bp = Blueprint('admin', __name__)
logger = get_logger('admin')


def load_admin_user(user_id):
    """User loader for Flask-Login — now loads from database."""
    if user_id:
        return AdminUser.query.get(int(user_id))
    return None


# ── Login (rate-limited) ──

@admin_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour")
def login():
    """Admin login page with rate limiting."""
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        admin = AdminUser.query.filter_by(username=username, is_active=True).first()
        if admin and admin.check_password(password):
            login_user(admin, remember=True)
            admin.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            log_event('ADMIN_LOGIN', f'Admin logged in: {username}')
            flash_success('Logged in successfully!')
            return redirect(url_for('admin.dashboard'))
        else:
            flash_error('Invalid credentials.')

    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash_success('Logged out.')
    return redirect(url_for('admin.login'))


# ── Dashboard ──

@admin_bp.route('/')
@login_required
def dashboard():
    """Admin dashboard with stats and charts."""
    stats = get_dashboard_stats()

    subscriber_growth = get_subscriber_growth_data(days=7)
    email_stats = get_email_chart_data(days=7)
    source_data = get_source_distribution(limit=8)
    source_list = [(d['source'], d['count']) for d in source_data]

    recent_emails = get_recent_emails(limit=5)
    recent_scrapes = get_recent_scrapes(limit=5)

    try:
        from scheduler.scheduler import get_scheduler_jobs
        scheduled_jobs = get_scheduler_jobs()
    except Exception:
        scheduled_jobs = []

    return render_template(
        'admin/dashboard.html',
        **stats,
        subscriber_growth=subscriber_growth,
        email_stats=email_stats,
        source_data=source_list,
        recent_emails=recent_emails,
        recent_scrapes=recent_scrapes,
        scheduled_jobs=scheduled_jobs,
        format_datetime=format_datetime,
        format_duration=format_duration,
    )


# ── Subscribers ──

@admin_bp.route('/subscribers')
@login_required
def subscribers():
    """View and manage subscribers."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()

    query = Subscriber.query.order_by(Subscriber.created_at.desc())

    if search:
        query = query.filter(
            db.or_(
                Subscriber.email.ilike(f'%{search}%'),
                Subscriber.role.ilike(f'%{search}%'),
                Subscriber.skills.ilike(f'%{search}%'),
                Subscriber.location.ilike(f'%{search}%'),
            )
        )

    if status == 'verified':
        query = query.filter_by(is_verified=True, is_active=True)
    elif status == 'unverified':
        query = query.filter_by(is_verified=False, is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    subscribers_page = query.paginate(page=page, per_page=current_app.config.get('PER_PAGE', 10))

    return render_template(
        'admin/subscribers.html',
        subscribers=subscribers_page,
        search=search,
        status=status,
        format_datetime=format_datetime,
    )


@admin_bp.route('/subscribers/delete/<int:id>', methods=['POST'])
@login_required
def delete_subscriber(id):
    """Delete a subscriber."""
    subscriber = Subscriber.query.get_or_404(id)
    email = subscriber.email
    db.session.delete(subscriber)
    db.session.commit()
    log_event('SUBSCRIBER_DELETED', f'Deleted subscriber: {email}')
    flash_success(f'Subscriber {email} deleted.')
    return redirect(url_for('admin.subscribers'))


@admin_bp.route('/subscribers/export')
@login_required
def export_subscribers():
    """Export subscribers as CSV."""
    subscribers_list = Subscriber.query.all()
    output = StringIO()
    writer = csv_module.writer(output)
    writer.writerow(['ID', 'Email', 'Role', 'Skills', 'Location', 'Experience', 'Job Type', 'Frequency', 'Verified', 'Active', 'Created At'])

    for s in subscribers_list:
        writer.writerow([
            s.id, s.email, s.role, s.skills, s.location,
            s.experience, s.job_type, s.frequency,
            s.is_verified, s.is_active,
            s.created_at.isoformat() if s.created_at else '',
        ])

    output.seek(0)
    log_event('SUBSCRIBERS_EXPORTED', f'Exported {len(subscribers_list)} subscribers')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=subscribers.csv'},
    )


# ── Jobs ──

@admin_bp.route('/jobs')
@login_required
def jobs():
    """View and manage jobs."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    source = request.args.get('source', '').strip()

    query = Job.query.order_by(Job.scraped_at.desc())

    if search:
        query = query.filter(
            db.or_(
                Job.title.ilike(f'%{search}%'),
                Job.company.ilike(f'%{search}%'),
                Job.skills.ilike(f'%{search}%'),
            )
        )

    if source:
        query = query.filter_by(source=source)

    jobs_page = query.paginate(page=page, per_page=current_app.config.get('PER_PAGE', 10))

    sources = db.session.query(Job.source).distinct().order_by(Job.source).all()

    return render_template(
        'admin/jobs.html',
        jobs=jobs_page,
        search=search,
        source=source,
        sources=sources,
        format_datetime=format_datetime,
    )


@admin_bp.route('/jobs/<int:id>')
@login_required
def job_detail(id):
    """View job details."""
    job = Job.query.get_or_404(id)
    return render_template('admin/job_detail.html', job=job, format_datetime=format_datetime)


@admin_bp.route('/jobs/delete/<int:id>', methods=['POST'])
@login_required
def delete_job(id):
    """Delete a job."""
    job = Job.query.get_or_404(id)
    title = job.title
    db.session.delete(job)
    db.session.commit()
    flash_success(f'Job "{title}" deleted.')
    return redirect(url_for('admin.jobs'))


@admin_bp.route('/jobs/clear-old', methods=['POST'])
@login_required
def clear_old_jobs():
    """Clear jobs older than 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    deleted = Job.query.filter(Job.scraped_at < cutoff).delete()
    db.session.commit()
    log_event('OLD_JOBS_CLEARED', f'Cleared {deleted} old jobs')
    flash_success(f'Cleared {deleted} old jobs.')
    return redirect(url_for('admin.jobs'))


# ── Email History ──

@admin_bp.route('/email-history')
@login_required
def email_history():
    """View email sending history."""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '').strip()

    query = EmailHistory.query.order_by(EmailHistory.sent_at.desc())

    if status:
        query = query.filter_by(status=status)

    emails = query.paginate(page=page, per_page=current_app.config.get('PER_PAGE', 15))

    return render_template(
        'admin/email_history.html',
        emails=emails,
        status=status,
        format_datetime=format_datetime,
    )


# ── Scraper History ──

@admin_bp.route('/scraper-history')
@login_required
def scraper_history():
    """View scraper run history."""
    page = request.args.get('page', 1, type=int)
    source = request.args.get('source', '').strip()

    query = ScraperHistory.query.order_by(ScraperHistory.started_at.desc())

    if source:
        query = query.filter_by(source=source)

    history = query.paginate(page=page, per_page=current_app.config.get('PER_PAGE', 15))

    return render_template(
        'admin/scraper_history.html',
        history=history,
        source=source,
        format_datetime=format_datetime,
        format_duration=format_duration,
    )


# ── Scraper Health Dashboard ──

@admin_bp.route('/scraper-health')
@login_required
def scraper_health():
    """Scraper health dashboard — green/red status lights for each source."""
    health_data = get_scraper_health(hours=24)
    return render_template(
        'admin/scraper_health.html',
        health=health_data,
        format_datetime=format_datetime,
        format_duration=format_duration,
    )


# ── Logs ──

@admin_bp.route('/logs')
@login_required
def logs():
    """View application logs."""
    log_event('LOGS_VIEWED', 'Admin viewed logs')
    try:
        with open('logs/app.log', 'r') as f:
            log_lines = f.readlines()[-200:]
    except FileNotFoundError:
        log_lines = ['No logs found.']

    return render_template('admin/logs.html', log_lines=log_lines)


# ── Manual Actions ──

@admin_bp.route('/run-scraper', methods=['POST'])
@login_required
def run_scraper():
    """Manually trigger the scraper."""
    from scheduler.scheduler import scrape_all_jobs
    try:
        new_jobs = scrape_all_jobs()
        flash_success(f'Scraper completed! Found {new_jobs} new jobs.')
        log_event('MANUAL_SCRAPE', f'Admin triggered manual scrape: {new_jobs} new jobs')
    except Exception as e:
        flash_error(f'Scraper failed: {str(e)}')
        log_event('SCRAPER_FAILED', f'Manual scrape failed: {str(e)}', 'error')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/run-alerts', methods=['POST'])
@login_required
def run_alerts():
    """Manually trigger email alerts."""
    from scheduler.scheduler import send_daily_alerts
    try:
        sent, failed = send_daily_alerts()
        flash_success(f'Alerts sent! {sent} sent, {failed} failed.')
        log_event('MANUAL_ALERTS', f'Admin triggered alerts: {sent} sent, {failed} failed')
    except Exception as e:
        flash_error(f'Alerts failed: {str(e)}')
        log_event('EMAIL_FAILED', f'Manual alerts failed: {str(e)}', 'error')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/retry-failed', methods=['POST'])
@login_required
def retry_failed():
    """Retry failed emails."""
    from scheduler.scheduler import retry_failed_emails
    try:
        retried = retry_failed_emails()
        flash_success(f'Retried {retried} failed emails.')
        log_event('RETRY_EMAILS', f'Admin retried {retried} failed emails')
    except Exception as e:
        flash_error(f'Retry failed: {str(e)}')
    return redirect(url_for('admin.dashboard'))
