"""Scheduler service for daily job scraping and email alerts.
Includes database-level locking to prevent duplicate execution across multiple workers.
"""
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import current_app
from sqlalchemy import or_

from extensions import db
from models.job import Job
from models.subscriber import Subscriber
from models.email_history import EmailHistory
from models.scraper_history import ScraperHistory
from scrapers.scrapers import get_all_scrapers, get_fallback_scraper
from services.email_service import send_job_alert, send_job_alerts_parallel
from services.matching_service import find_matching_jobs
from services.scheduler_lock import SchedulerLock
from utils.logger import get_logger, log_event

logger = get_logger('scheduler')
scheduler = BackgroundScheduler()


def scrape_all_jobs():
    """Scrape jobs from all registered sources with batch duplicate detection.
    Falls back to DemoScraper if all real scrapers return 0 jobs.
    """
    log_event('SCHEDULER_STARTED', 'Starting scheduled job scraping')
    logger.info('=== Starting scheduled scrape ===')

    scrapers = get_all_scrapers()  # Returns only real scrapers (excludes demo)
    total_new_jobs = 0
    total_found_jobs = 0

    for scraper in scrapers:
        history = ScraperHistory(
            source=scraper.source_name,
            status='pending',
            started_at=datetime.now(timezone.utc),
        )
        db.session.add(history)
        db.session.commit()

        try:
            jobs = scraper.scrape()
            new_count = 0

            if jobs:
                job_keys = [
                    (j.get('title', ''), j.get('company', ''), j.get('location', ''))
                    for j in jobs
                ]

                conditions = [
                    db.and_(
                        Job.title == title,
                        Job.company == company,
                        Job.location == location,
                    )
                    for title, company, location in job_keys
                ]
                if conditions:
                    existing = set()
                    for row in Job.query.with_entities(
                        Job.title, Job.company, Job.location
                    ).filter(or_(*conditions)).all():
                        existing.add((row.title, row.company, row.location))

                    for job_data in jobs:
                        key = (job_data.get('title', ''), job_data.get('company', ''), job_data.get('location', ''))
                        if key not in existing:
                            job = Job(
                                title=job_data.get('title', ''),
                                company=job_data.get('company', ''),
                                location=job_data.get('location', ''),
                                salary=job_data.get('salary', ''),
                                skills=job_data.get('skills', ''),
                                url=job_data.get('url', ''),
                                source=job_data.get('source', scraper.source_name),
                                posted_date=job_data.get('posted_date', ''),
                                description=job_data.get('description', ''),
                                job_type=job_data.get('job_type', ''),
                            )
                            db.session.add(job)
                            new_count += 1

            history.jobs_found = len(jobs) if jobs else 0
            history.jobs_new = new_count
            history.status = 'success'
            history.finished_at = datetime.now(timezone.utc)
            total_new_jobs += new_count
            total_found_jobs += history.jobs_found

            log_event('SCRAPER_SUCCESS', f'{scraper.source_name}: Found {history.jobs_found} jobs, {new_count} new')
            logger.info(f'{scraper.source_name}: {history.jobs_found} found, {new_count} new')

        except Exception as e:
            history.status = 'failed'
            history.error_message = str(e)
            history.finished_at = datetime.now(timezone.utc)
            log_event('SCRAPER_FAILED', f'{scraper.source_name}: {str(e)}', 'error')
            logger.error(f'{scraper.source_name} failed: {e}')

        db.session.commit()

    # Fallback: if no real scraper found any jobs, run the demo scraper
    if total_found_jobs == 0:
        logger.info('All real scrapers returned 0 jobs — running DemoScraper fallback')
        demo_scraper = get_fallback_scraper()
        demo_history = ScraperHistory(
            source=demo_scraper.source_name,
            status='pending',
            started_at=datetime.now(timezone.utc),
        )
        db.session.add(demo_history)
        try:
            demo_jobs = demo_scraper.scrape()
            for job_data in demo_jobs:
                job = Job(
                    title=job_data.get('title', ''),
                    company=job_data.get('company', ''),
                    location=job_data.get('location', ''),
                    salary=job_data.get('salary', ''),
                    skills=job_data.get('skills', ''),
                    url=job_data.get('url', ''),
                    source=job_data.get('source', demo_scraper.source_name),
                    posted_date=job_data.get('posted_date', ''),
                    description=job_data.get('description', ''),
                    job_type=job_data.get('job_type', ''),
                )
                db.session.add(job)

            demo_history.jobs_found = len(demo_jobs)
            demo_history.jobs_new = len(demo_jobs)
            demo_history.status = 'success'
            demo_history.finished_at = datetime.now(timezone.utc)
            total_new_jobs += len(demo_jobs)
            log_event('DEMO_FALLBACK', f'Demo fallback ran: {len(demo_jobs)} jobs')
            logger.info(f'Demo fallback: {len(demo_jobs)} jobs created')
        except Exception as e:
            demo_history.status = 'failed'
            demo_history.error_message = str(e)
            demo_history.finished_at = datetime.now(timezone.utc)
            logger.error(f'Demo fallback failed: {e}')
        db.session.commit()

    logger.info(f'=== Scrape complete. {total_new_jobs} new jobs saved ===')
    return total_new_jobs


def send_daily_alerts():
    """Send email alerts to all verified subscribers with matching jobs.
    Uses parallel thread pool for concurrent delivery when EMAIL_WORKERS > 1.
    """
    log_event('SCHEDULER_STARTED', 'Starting daily email alerts')
    logger.info('=== Starting daily email alerts ===')

    subscribers = Subscriber.query.filter_by(
        is_verified=True, is_active=True
    ).all()

    max_workers = current_app.config.get('EMAIL_WORKERS', 4)

    if max_workers > 1 and len(subscribers) > 5:
        # Parallel mode
        subscribers_with_jobs = []
        for subscriber in subscribers:
            try:
                matching_jobs = find_matching_jobs(subscriber)
                subscribers_with_jobs.append((subscriber, matching_jobs))
            except Exception as e:
                logger.error(f'Match failed for {subscriber.email}: {e}')

        sent_count, failed_count = send_job_alerts_parallel(subscribers_with_jobs, max_workers=max_workers)

        # Record all histories (parallel path doesn't track per-subscriber results,
        # so we use the aggregate sent/failed counts)
        for subscriber, matching_jobs in subscribers_with_jobs:
            try:
                # Without per-subscriber tracking, mark all as sent if they had jobs
                had_jobs = len(matching_jobs) > 0
                history = EmailHistory(
                    subscriber_id=subscriber.id,
                    jobs_sent=len(matching_jobs),
                    status='sent' if had_jobs else 'sent',
                    error_message='' if had_jobs else 'No matching jobs found',
                )
                db.session.add(history)
            except Exception as e:
                logger.error(f'History record failed for {subscriber.email}: {e}')
            db.session.commit()
    else:
        # Sequential mode (fallback for single-worker config)
        sent_count = 0
        failed_count = 0
        for subscriber in subscribers:
            try:
                matching_jobs = find_matching_jobs(subscriber)

                if matching_jobs:
                    success, error = send_job_alert(subscriber, matching_jobs)
                    history = EmailHistory(
                        subscriber_id=subscriber.id,
                        jobs_sent=len(matching_jobs),
                        status='sent' if success else 'failed',
                        error_message=error,
                    )
                    db.session.add(history)
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
                else:
                    history = EmailHistory(
                        subscriber_id=subscriber.id,
                        jobs_sent=0,
                        status='sent',
                        error_message='No matching jobs found',
                    )
                    db.session.add(history)

                db.session.commit()

            except Exception as e:
                logger.error(f'Failed to send alert to {subscriber.email}: {e}')
                log_event('EMAIL_FAILED', f'{subscriber.email}: {str(e)}', 'error')
                failed_count += 1

    log_event('EMAILS_SENT', f'Alerts sent: {sent_count} sent, {failed_count} failed')
    logger.info(f'=== Alerts complete. {sent_count} sent, {failed_count} failed ===')
    return sent_count, failed_count


def daily_job():
    """Main daily job: scrape + send alerts.
    Uses database locking to ensure only one worker executes.
    """
    with SchedulerLock.acquire('daily_job', timeout_seconds=600,
                                owner=f'worker_{datetime.now(timezone.utc).timestamp()}') as acquired:
        if not acquired:
            logger.info('Daily job: lock held by another worker, skipping')
            return

        logger.info('=== DAILY JOB STARTED ===')
        try:
            new_jobs = scrape_all_jobs()
            if new_jobs > 0:
                send_daily_alerts()
            logger.info(f'=== DAILY JOB COMPLETE. {new_jobs} new jobs scraped ===')
        except Exception as e:
            logger.error(f'Daily job failed: {e}')
            log_event('ERROR', f'Daily job failed: {str(e)}', 'error')


def retry_failed_emails():
    """Retry sending emails that previously failed."""
    with SchedulerLock.acquire('retry_emails', timeout_seconds=600,
                                owner=f'worker_{datetime.now(timezone.utc).timestamp()}') as acquired:
        if not acquired:
            logger.info('Retry emails: lock held by another worker, skipping')
            return

        failed_histories = EmailHistory.query.filter_by(status='failed').limit(20).all()
        retried = 0

        for history in failed_histories:
            subscriber = Subscriber.query.get(history.subscriber_id)
            if not subscriber or not subscriber.is_active:
                continue

            try:
                matching_jobs = find_matching_jobs(subscriber)
                if matching_jobs:
                    success, error = send_job_alert(subscriber, matching_jobs)
                    if success:
                        history.status = 'sent'
                        retried += 1
                    else:
                        history.error_message = f'Retry failed: {error}'
                db.session.commit()
            except Exception as e:
                logger.error(f'Retry failed for {subscriber.email}: {e}')

    log_event('RETRY_EMAILS', f'Retried {retried} failed emails')
    return retried


def init_scheduler(app):
    """Initialize and start the scheduler."""
    with app.app_context():
        try:
            scheduler.add_job(
                daily_job,
                trigger=CronTrigger(
                    hour=app.config.get('SCHEDULE_HOUR', 8),
                    minute=app.config.get('SCHEDULE_MINUTE', 0),
                ),
                id='daily_scrape_and_alert',
                name='Daily Scrape and Alert',
                replace_existing=True,
            )

            scheduler.add_job(
                retry_failed_emails,
                trigger=CronTrigger(hour=10, minute=0),
                id='retry_failed_emails',
                name='Retry Failed Emails',
                replace_existing=True,
            )

            scheduler.start()
            log_event('SCHEDULER_STARTED', 'Scheduler started successfully')
            logger.info('Scheduler started. Daily job scheduled at '
                        f'{app.config.get("SCHEDULE_HOUR", 8)}:'
                        f'{app.config.get("SCHEDULE_MINUTE", 0):02d}')
        except Exception as e:
            logger.error(f'Failed to start scheduler: {e}')
            log_event('SCHEDULER_ERROR', f'Scheduler init failed: {str(e)}', 'error')


def get_scheduler_jobs():
    """Get list of scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': str(job.next_run_time) if job.next_run_time else 'N/A',
            'trigger': str(job.trigger),
        })
    return jobs
