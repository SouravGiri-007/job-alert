"""Pytest configuration, fixtures, and sample data for Smart Job Alert tests."""
import os
import sys
import pytest
import tempfile
from datetime import datetime, timezone, timedelta

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from extensions import db as _db
from models.subscriber import Subscriber
from models.job import Job
from models.email_history import EmailHistory
from models.scraper_history import ScraperHistory
from models.admin import AdminUser


# ── Test configuration ──

class TestConfig:
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ADMIN_USERNAME = 'testadmin'
    ADMIN_PASSWORD = 'testpass123'
    WTF_CSRF_ENABLED = False  # Disable CSRF for test requests
    TESTING = True
    APP_NAME = 'Smart Job Alert'
    APP_URL = 'http://localhost'
    PER_PAGE = 10
    SMTP_SERVER = 'localhost'
    SMTP_PORT = 1025
    SMTP_USERNAME = ''
    SMTP_PASSWORD = ''
    MAIL_FROM = 'test@test.com'
    MAIL_FROM_NAME = 'Test'
    EMAIL_WORKERS = 1
    RATELIMIT_ENABLED = False


# ── Fixtures ──

@pytest.fixture(scope='session')
def app():
    """Create a Flask app for testing with in-memory database."""
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        # Seed test admin
        AdminUser.seed_default_admin('testadmin', 'testpass123')
        yield app


@pytest.fixture(scope='function')
def db(app):
    """Provide a clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        # Clear all tables after each test
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture(scope='function')
def client(app, db):
    """Test client with clean database."""
    with app.test_client() as client:
        with app.app_context():
            # Re-seed admin for tests that need it
            AdminUser.seed_default_admin('testadmin', 'testpass123')
        yield client


@pytest.fixture(scope='function')
def sample_subscriber(db):
    """Create a sample verified subscriber."""
    sub = Subscriber(
        email='test@example.com',
        role='Python Developer',
        skills='python, django, sql',
        location='Bangalore',
        job_type='Full-time',
        frequency='daily',
        is_verified=True,
        is_active=True,
        verification_token='sample-verify-token-abc123',
    )
    db.session.add(sub)
    db.session.commit()
    return sub


@pytest.fixture(scope='function')
def sample_jobs(db):
    """Create sample job listings."""
    jobs_data = [
        Job(title='Senior Python Developer', company='Google', location='Bangalore, India',
            salary='25-40 LPA', skills='python, django, flask, sql', source='LinkedIn',
            job_type='Full-time', scraped_at=datetime.now(timezone.utc)),
        Job(title='React Frontend Engineer', company='Amazon', location='Hyderabad, India',
            salary='20-35 LPA', skills='react, javascript, css', source='Indeed',
            job_type='Full-time', scraped_at=datetime.now(timezone.utc)),
        Job(title='Data Science Intern', company='StartupXYZ', location='Remote',
            salary='15k/month', skills='python, ml, statistics', source='Internshala',
            job_type='Internship', scraped_at=datetime.now(timezone.utc)),
    ]
    for j in jobs_data:
        db.session.add(j)
    db.session.commit()
    return jobs_data


@pytest.fixture(scope='function')
def sample_email_history(db, sample_subscriber):
    """Create sample email history entries."""
    histories = [
        EmailHistory(subscriber_id=sample_subscriber.id, jobs_sent=3, status='sent'),
        EmailHistory(subscriber_id=sample_subscriber.id, jobs_sent=0, status='sent',
                     error_message='No matching jobs found'),
    ]
    for h in histories:
        db.session.add(h)
    db.session.commit()
    return histories


@pytest.fixture(scope='function')
def sample_scraper_history(db):
    """Create sample scraper history entries."""
    histories = [
        ScraperHistory(source='LinkedIn', jobs_found=25, jobs_new=10, status='success',
                       started_at=datetime.now(timezone.utc) - timedelta(hours=2),
                       finished_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=55)),
        ScraperHistory(source='Internshala', jobs_found=15, jobs_new=5, status='success',
                       started_at=datetime.now(timezone.utc) - timedelta(hours=1),
                       finished_at=datetime.now(timezone.utc) - timedelta(minutes=58)),
    ]
    for h in histories:
        db.session.add(h)
    db.session.commit()
    return histories


@pytest.fixture(scope='function')
def admin_session(client):
    """Create an authenticated admin session."""
    client.post('/admin/login', data={
        'username': 'testadmin',
        'password': 'testpass123',
    }, follow_redirects=True)
    return client
