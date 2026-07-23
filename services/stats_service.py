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


def get_scraper_health(hours: int = 24):
    """Return per-source health summary for the last N hours.

    Returns a dict:
      'sources': [
          {
              'source': str,
              'last_status': 'success' | 'failed' | 'no_data',
              'total_runs': int,
              'successful_runs': int,
              'failed_runs': int,
              'success_rate': float (0-100),
              'total_jobs_found': int,
              'total_jobs_new': int,
              'last_run_at': datetime | None,
              'last_duration': float | None,
              'avg_duration': float | None,
          },
          ...
      ]
      'overall_health': 'healthy' | 'degraded' | 'down',
      'overall_success_rate': float,
      'total_runs_last_24h': int,
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get all scraper history in the window
    rows = ScraperHistory.query.filter(
        ScraperHistory.started_at >= cutoff
    ).order_by(ScraperHistory.started_at.desc()).all()

    # Group by source
    from collections import OrderedDict
    grouped = OrderedDict()

    for row in rows:
        if row.source not in grouped:
            grouped[row.source] = {
                'source': row.source,
                'total_runs': 0,
                'successful_runs': 0,
                'failed_runs': 0,
                'total_jobs_found': 0,
                'total_jobs_new': 0,
                'durations': [],
                'last_run_at': None,
                'last_status': 'no_data',
                'last_duration': None,
            }

        g = grouped[row.source]
        g['total_runs'] += 1

        if row.status == 'success':
            g['successful_runs'] += 1
        else:
            g['failed_runs'] += 1

        g['total_jobs_found'] += row.jobs_found or 0
        g['total_jobs_new'] += row.jobs_new or 0

        if row.duration is not None:
            g['durations'].append(row.duration)

        # First row (most recent) = last run
        if g['last_run_at'] is None:
            g['last_run_at'] = row.started_at
            g['last_status'] = row.status
            g['last_duration'] = row.duration

    # Compute derived fields
    sources = []
    total_all_runs = 0
    total_successful_runs = 0

    for g in grouped.values():
        g['success_rate'] = round(
            (g['successful_runs'] / g['total_runs'] * 100) if g['total_runs'] > 0 else 0,
            1,
        )
        g['avg_duration'] = (
            round(sum(g['durations']) / len(g['durations']), 1) if g['durations'] else None
        )
        del g['durations']
        sources.append(g)

        total_all_runs += g['total_runs']
        total_successful_runs += g['successful_runs']

    overall_success_rate = round(
        (total_successful_runs / total_all_runs * 100) if total_all_runs > 0 else 0,
        1,
    )

    if total_all_runs == 0:
        overall_health = 'down'
    elif overall_success_rate == 100:
        overall_health = 'healthy'
    elif overall_success_rate >= 50:
        overall_health = 'degraded'
    else:
        overall_health = 'down'

    return {
        'sources': sources,
        'overall_health': overall_health,
        'overall_success_rate': overall_success_rate,
        'total_runs_last_24h': total_all_runs,
    }
