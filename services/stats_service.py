"""Shared service for dashboard statistics and chart data.
Eliminates duplicate queries between admin.py and api.py routes.
"""
from datetime import datetime, timezone, timedelta
from extensions import db
from models.subscriber import Subscriber
from models.job import Job
from models.email_history import EmailHistory
from models.scraper_history import ScraperHistory


def get_dashboard_stats():
    """Return summary stats for the admin dashboard."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        'total_subscribers': Subscriber.query.filter_by(is_active=True).count(),
        'total_verified': Subscriber.query.filter_by(is_verified=True, is_active=True).count(),
        'jobs_today': Job.query.filter(Job.scraped_at >= today_start).count(),
        'emails_sent_today': EmailHistory.query.filter(
            EmailHistory.sent_at >= today_start,
            EmailHistory.status == 'sent',
        ).count(),
        'failed_emails_today': EmailHistory.query.filter(
            EmailHistory.sent_at >= today_start,
            EmailHistory.status == 'failed',
        ).count(),
        'total_jobs': Job.query.count(),
        'active_sources': db.session.query(
            ScraperHistory.source
        ).distinct().count(),
    }


def get_subscriber_growth_data(days: int = 7):
    """Return subscriber sign-ups per day for the last N days."""
    data = []
    for i in range(days - 1, -1, -1):
        date = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=i)
        count = Subscriber.query.filter(
            Subscriber.created_at >= date,
            Subscriber.created_at < date + timedelta(days=1),
        ).count()
        data.append({
            'date': date.strftime('%b %d'),
            'count': count,
        })
    return data


def get_email_chart_data(days: int = 7):
    """Return sent/failed email counts per day for the last N days."""
    data = []
    for i in range(days - 1, -1, -1):
        date = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=i)
        sent = EmailHistory.query.filter(
            EmailHistory.sent_at >= date,
            EmailHistory.sent_at < date + timedelta(days=1),
            EmailHistory.status == 'sent',
        ).count()
        failed = EmailHistory.query.filter(
            EmailHistory.sent_at >= date,
            EmailHistory.sent_at < date + timedelta(days=1),
            EmailHistory.status == 'failed',
        ).count()
        data.append({
            'date': date.strftime('%b %d'),
            'sent': sent,
            'failed': failed,
        })
    return data


def get_source_distribution(limit: int = 10):
    """Return job count grouped by source."""
    data = db.session.query(
        Job.source, db.func.count(Job.id).label('count')
    ).group_by(Job.source).order_by(db.desc('count')).limit(limit).all()
    return [{'source': d[0], 'count': d[1]} for d in data]


def get_recent_emails(limit: int = 5):
    """Return most recent email history entries."""
    return EmailHistory.query.order_by(EmailHistory.sent_at.desc()).limit(limit).all()


def get_recent_scrapes(limit: int = 5):
    """Return most recent scraper history entries."""
    return ScraperHistory.query.order_by(ScraperHistory.started_at.desc()).limit(limit).all()
