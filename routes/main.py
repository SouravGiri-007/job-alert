"""Main routes - landing page, subscription, verification, unsubscribe, job browser with filters."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from extensions import db
from models.subscriber import Subscriber
from models.job import Job
from utils.helpers import generate_token, flash_success, flash_error, flash_info
from utils.logger import log_event
from services.email_service import send_verification_email, send_unsubscribe_confirmation
import re

main_bp = Blueprint('main', __name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
MAX_FIELD_LENGTH = 500

VALID_JOB_TYPES = ['', 'Full-time', 'Part-time', 'Contract', 'Internship', 'Freelance']
VALID_SORT_OPTIONS = ['newest', 'oldest', 'company_az', 'company_za']


@main_bp.route('/')
def index():
    """Landing page."""
    latest_jobs = Job.query.order_by(Job.scraped_at.desc()).limit(6).all()
    subscriber_count = Subscriber.query.filter_by(is_active=True).count()
    return render_template('index.html', latest_jobs=latest_jobs, subscriber_count=subscriber_count)


def _validate_field(value, field_name, max_length=MAX_FIELD_LENGTH):
    """Validate a text field — reject if too long or contains dangerous content."""
    if not value:
        return value
    if len(value) > max_length:
        flash_error(f'{field_name} is too long (max {max_length} characters).')
        return None
    if re.search(r'<[^>]*>', value):
        flash_error(f'Invalid characters in {field_name}.')
        return None
    return value.strip()


@main_bp.route('/subscribe', methods=['POST'])
def subscribe():
    """Handle subscription form submission."""
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', '').strip()
    skills = request.form.get('skills', '').strip()
    location = request.form.get('location', '').strip()
    experience = request.form.get('experience', '').strip()
    job_type = request.form.get('job_type', '').strip()
    frequency = request.form.get('frequency', 'daily')

    if not email or not EMAIL_REGEX.match(email):
        flash_error('Please enter a valid email address.')
        return redirect(url_for('main.index') + '#subscribe')

    if len(email) > 254:
        flash_error('Email address is too long.')
        return redirect(url_for('main.index') + '#subscribe')

    role = _validate_field(role, 'Role')
    if role is None:
        return redirect(url_for('main.index') + '#subscribe')

    skills = _validate_field(skills, 'Skills')
    if skills is None:
        return redirect(url_for('main.index') + '#subscribe')

    location = _validate_field(location, 'Location')
    if location is None:
        return redirect(url_for('main.index') + '#subscribe')

    if frequency not in ('daily', 'weekly'):
        frequency = 'daily'

    existing = Subscriber.query.filter_by(email=email).first()
    if existing:
        if existing.is_verified:
            flash_error('This email is already subscribed and verified.')
        else:
            existing.verification_token = generate_token()
            existing.role = role
            existing.skills = skills
            existing.location = location
            existing.experience = experience
            existing.job_type = job_type
            existing.frequency = frequency
            db.session.commit()
            try:
                send_verification_email(existing)
                flash('check_spam', 'check_spam')
            except Exception:
                flash_success('Preferences updated. Email verification will be sent during next run.')
        return redirect(url_for('main.index') + '#subscribe')

    token = generate_token()
    subscriber = Subscriber(
        email=email,
        role=role,
        skills=skills,
        location=location,
        experience=experience,
        job_type=job_type,
        frequency=frequency,
        verification_token=token,
    )
    db.session.add(subscriber)
    db.session.commit()

    try:
        send_verification_email(subscriber)
        flash('check_spam', 'check_spam')
    except Exception as e:
        log_event('EMAIL_FAILED', f'Verification email failed: {str(e)}', 'error')
        flash_info('Subscribed! Verification will be sent once the email service is ready.')

    log_event('NEW_SUBSCRIBER', f'New subscriber: {email}')
    return redirect(url_for('main.index') + '#subscribe')


@main_bp.route('/verify/<token>')
def verify_email(token):
    """Verify email address."""
    if not token or len(token) > 128:
        flash_error('Invalid verification link.')
        return redirect(url_for('main.index'))

    subscriber = Subscriber.query.filter_by(verification_token=token).first()
    if not subscriber:
        flash_error('Invalid or expired verification link.')
        return redirect(url_for('main.index'))

    if subscriber.is_verified:
        flash_success('Your email is already verified!')
        return redirect(url_for('main.index'))

    subscriber.is_verified = True
    db.session.commit()

    log_event('EMAIL_VERIFIED', f'Email verified: {subscriber.email}')
    flash_success('Your email has been verified! You will receive job alerts soon.')
    return redirect(url_for('main.index'))


@main_bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    """Unsubscribe a user via token."""
    if not token or len(token) > 128:
        flash_error('Invalid unsubscribe link.')
        return redirect(url_for('main.index'))

    subscriber = Subscriber.query.filter_by(verification_token=token).first()
    if not subscriber:
        flash_error('Invalid unsubscribe link.')
        return redirect(url_for('main.index'))

    if not subscriber.is_active:
        flash_info('You are already unsubscribed.')
        return redirect(url_for('main.index'))

    subscriber.is_active = False
    db.session.commit()

    try:
        send_unsubscribe_confirmation(subscriber)
    except Exception:
        pass

    log_event('UNSUBSCRIBED', f'User unsubscribed: {subscriber.email}')
    flash_success('You have been unsubscribed successfully. You can re-subscribe anytime.')
    return redirect(url_for('main.index'))


@main_bp.route('/jobs')
def browse_jobs():
    """Browse all scraped jobs with advanced filters."""
    from datetime import datetime, timedelta

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    location_filter = request.args.get('location', '').strip()
    source_filter = request.args.get('source', '').strip()
    job_type_filter = request.args.get('job_type', '').strip()
    salary_only = request.args.get('salary_only', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    sort = request.args.get('sort', 'newest').strip()

    # Length limits
    if len(search) > 200:
        search = search[:200]
    if len(location_filter) > 200:
        location_filter = location_filter[:200]

    # Validate sort
    if sort not in VALID_SORT_OPTIONS:
        sort = 'newest'

    # Build query
    query = Job.query

    # Free-text search
    if search:
        query = query.filter(
            db.or_(
                Job.title.ilike(f'%{search}%'),
                Job.company.ilike(f'%{search}%'),
                Job.skills.ilike(f'%{search}%'),
                Job.description.ilike(f'%{search}%'),
            )
        )

    # Location
    if location_filter:
        query = query.filter(Job.location.ilike(f'%{location_filter}%'))

    # Source
    if source_filter:
        query = query.filter(Job.source == source_filter)

    # Job type
    if job_type_filter and job_type_filter in VALID_JOB_TYPES:
        query = query.filter(Job.job_type == job_type_filter)

    # Salary only
    if salary_only == 'yes':
        query = query.filter(Job.salary != '')

    # Date range
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Job.scraped_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Job.scraped_at < dt_to)
        except ValueError:
            pass

    # Sorting
    if sort == 'oldest':
        query = query.order_by(Job.scraped_at.asc())
    elif sort == 'company_az':
        query = query.order_by(Job.company.asc())
    elif sort == 'company_za':
        query = query.order_by(Job.company.desc())
    else:
        query = query.order_by(Job.scraped_at.desc())

    jobs = query.paginate(page=page, per_page=current_app.config.get('PER_PAGE', 10))

    # Get distinct sources for filter dropdown
    sources = db.session.query(Job.source).distinct().order_by(Job.source).all()
    source_list = [s[0] for s in sources]

    # Pre-compute active filter badges for the template (avoids Jinja2 list-append hack)
    active_filters = []
    if search:
        active_filters.append(f'Search: "{search}"')
    if location_filter:
        active_filters.append(f'Location: {location_filter}')
    if source_filter:
        active_filters.append(f'Source: {source_filter}')
    if job_type_filter:
        active_filters.append(f'Type: {job_type_filter}')
    if salary_only == 'yes':
        active_filters.append('With Salary')
    if date_from:
        active_filters.append(f'From: {date_from}')
    if date_to:
        active_filters.append(f'To: {date_to}')

    return render_template(
        'jobs.html',
        jobs=jobs,
        search=search,
        location_filter=location_filter,
        source_filter=source_filter,
        source_list=source_list,
        job_type_filter=job_type_filter,
        salary_only=salary_only,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        active_filters=active_filters,
    )
