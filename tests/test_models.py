"""Tests for database models."""
import pytest
from datetime import datetime, timezone
from models.subscriber import Subscriber
from models.job import Job
from models.email_history import EmailHistory
from models.scraper_history import ScraperHistory
from models.admin import AdminUser
from extensions import db


class TestSubscriberModel:
    """Subscriber model tests."""

    def test_create_subscriber(self, db):
        sub = Subscriber(
            email='alice@test.com',
            role='Data Scientist',
            skills='python, ml, statistics',
            location='Remote',
            job_type='Full-time',
            frequency='daily',
            is_verified=True,
            is_active=True,
        )
        db.session.add(sub)
        db.session.commit()

        saved = Subscriber.query.filter_by(email='alice@test.com').first()
        assert saved is not None
        assert saved.role == 'Data Scientist'
        assert saved.is_verified is True
        assert saved.frequency == 'daily'

    def test_get_skills_list(self, db):
        sub = Subscriber(email='bob@test.com', skills='python, django,   sql,  ')
        db.session.add(sub)
        db.session.commit()

        skills = sub.get_skills_list()
        assert skills == ['python', 'django', 'sql']

    def test_unique_email_constraint(self, db):
        sub1 = Subscriber(email='dup@test.com')
        db.session.add(sub1)
        db.session.commit()

        sub2 = Subscriber(email='dup@test.com')
        db.session.add(sub2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

    def test_to_dict(self, db):
        sub = Subscriber(email='dict@test.com', role='Engineer', skills='go')
        db.session.add(sub)
        db.session.commit()

        data = sub.to_dict()
        assert data['email'] == 'dict@test.com'
        assert data['role'] == 'Engineer'
        assert 'created_at' in data


class TestJobModel:
    """Job model tests."""

    def test_create_job(self, db):
        job = Job(
            title='Senior Python Dev',
            company='Google',
            location='Bangalore',
            salary='30 LPA',
            skills='python, flask, k8s',
            url='https://example.com/job/1',
            source='LinkedIn',
            job_type='Full-time',
        )
        db.session.add(job)
        db.session.commit()

        saved = Job.query.filter_by(title='Senior Python Dev').first()
        assert saved is not None
        assert saved.company == 'Google'

    def test_get_skills_list(self, db):
        job = Job(title='Dev', skills='python,  react, node')
        db.session.add(job)
        db.session.commit()

        assert job.get_skills_list() == ['python', 'react', 'node']

    def test_is_duplicate(self, db):
        Job.query.delete()
        job = Job(title='Same Job', company='Same Co', location='Same City')
        db.session.add(job)
        db.session.commit()

        assert Job.is_duplicate('Same Job', 'Same Co', 'Same City') is True
        assert Job.is_duplicate('Different', 'Same Co', 'Same City') is False

    def test_to_dict(self, db):
        job = Job(title='Test Job', company='Test Co')
        db.session.add(job)
        db.session.commit()

        data = job.to_dict()
        assert data['title'] == 'Test Job'
        assert 'scraped_at' in data


class TestEmailHistoryModel:
    """EmailHistory model tests."""

    def test_create_history(self, db, sample_subscriber):
        history = EmailHistory(
            subscriber_id=sample_subscriber.id,
            jobs_sent=5,
            status='sent',
        )
        db.session.add(history)
        db.session.commit()

        saved = EmailHistory.query.filter_by(subscriber_id=sample_subscriber.id).first()
        assert saved is not None
        assert saved.jobs_sent == 5
        assert saved.status == 'sent'


class TestScraperHistoryModel:
    """ScraperHistory model tests."""

    def test_duration_property(self, db):
        start = datetime.now(timezone.utc)
        end = datetime.now(timezone.utc)
        history = ScraperHistory(
            source='LinkedIn',
            jobs_found=20,
            jobs_new=8,
            status='success',
            started_at=start,
            finished_at=end,
        )
        db.session.add(history)
        db.session.commit()

        dur = history.duration
        assert dur is not None
        assert dur >= 0


class TestAdminUserModel:
    """AdminUser model tests."""

    def test_password_hashing(self, db):
        admin = AdminUser(username='admin1')
        admin.set_password('securePass123!')

        assert admin.check_password('securePass123!') is True
        assert admin.check_password('wrongPassword') is False
        assert admin.password_hash != 'securePass123!'  # Not plaintext

    def test_seed_default_admin_creates_once(self, db):
        admin1 = AdminUser.seed_default_admin('seed_admin', 'seedPass1!')
        assert admin1 is not None
        assert admin1.username == 'seed_admin'

        admin2 = AdminUser.seed_default_admin('seed_admin', 'seedPass1!')
        assert admin2.id == admin1.id  # Same user returned

    def test_flask_login_protocol(self, db):
        admin = AdminUser(username='logintest')
        admin.set_password('pass')
        db.session.add(admin)
        db.session.commit()

        assert admin.is_authenticated is True
        assert admin.is_anonymous is False
        assert admin.get_id() == str(admin.id)
