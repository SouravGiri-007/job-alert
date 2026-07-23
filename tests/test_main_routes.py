"""Tests for public routes (main blueprint)."""
from urllib.parse import urlencode
from models.subscriber import Subscriber
from extensions import db


class TestIndexRoute:
    """Landing page tests."""

    def test_index_returns_200(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'Smart Job Alert' in resp.data or b'Never Miss' in resp.data


class TestSubscribeRoute:
    """Subscription form tests."""

    def test_subscribe_success(self, client):
        resp = client.post('/subscribe', data={
            'email': 'newuser@test.com',
            'role': 'Python Developer',
            'skills': 'python, django',
            'location': 'Remote',
            'frequency': 'daily',
        }, follow_redirects=True)
        assert resp.status_code == 200

        sub = Subscriber.query.filter_by(email='newuser@test.com').first()
        assert sub is not None
        assert sub.role == 'Python Developer'
        assert sub.is_verified is False  # Must verify via email

    def test_subscribe_invalid_email(self, client):
        resp = client.post('/subscribe', data={
            'email': 'not-an-email',
        }, follow_redirects=True)
        assert resp.status_code == 200

        sub = Subscriber.query.filter_by(email='not-an-email').first()
        assert sub is None

    def test_subscribe_existing_unverified_resends(self, client, db):
        sub = Subscriber(email='existing@test.com', is_verified=False)
        db.session.add(sub)
        db.session.commit()

        client.post('/subscribe', data={
            'email': 'existing@test.com',
            'role': 'Updated Role',
        }, follow_redirects=True)

        updated = Subscriber.query.filter_by(email='existing@test.com').first()
        assert updated.role == 'Updated Role'

    def test_subscribe_existing_verified_shows_error(self, client, db):
        sub = Subscriber(email='verified@test.com', is_verified=True, is_active=True)
        db.session.add(sub)
        db.session.commit()

        resp = client.post('/subscribe', data={
            'email': 'verified@test.com',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_subscribe_rejects_html_in_fields(self, client):
        resp = client.post('/subscribe', data={
            'email': 'safe@test.com',
            'role': '<script>alert("xss")</script>',
        }, follow_redirects=True)
        assert resp.status_code == 200

        sub = Subscriber.query.filter_by(email='safe@test.com').first()
        assert sub is None


class TestVerifyRoute:
    """Email verification tests."""

    def test_verify_valid_token(self, client, db):
        sub = Subscriber(email='verify@test.com', verification_token='valid-token-123',
                         is_verified=False)
        db.session.add(sub)
        db.session.commit()

        resp = client.get('/verify/valid-token-123', follow_redirects=True)
        assert resp.status_code == 200

        updated = Subscriber.query.filter_by(email='verify@test.com').first()
        assert updated.is_verified is True

    def test_verify_invalid_token(self, client):
        resp = client.get('/verify/invalid-token', follow_redirects=True)
        assert resp.status_code == 200

    def test_verify_already_verified(self, client, db):
        sub = Subscriber(email='already@test.com', verification_token='token-321',
                         is_verified=True)
        db.session.add(sub)
        db.session.commit()

        client.get('/verify/token-321', follow_redirects=True)
        updated = Subscriber.query.filter_by(email='already@test.com').first()
        assert updated.is_verified is True  # Still verified


class TestUnsubscribeRoute:
    """Unsubscribe tests."""

    def test_unsubscribe_valid_token(self, client, db):
        sub = Subscriber(email='unsub@test.com', verification_token='unsub-token-456',
                         is_verified=True, is_active=True)
        db.session.add(sub)
        db.session.commit()

        resp = client.get('/unsubscribe/unsub-token-456', follow_redirects=True)
        assert resp.status_code == 200

        updated = Subscriber.query.filter_by(email='unsub@test.com').first()
        assert updated.is_active is False

    def test_unsubscribe_already_inactive(self, client, db):
        sub = Subscriber(email='already-inactive@test.com', verification_token='inactive-token',
                         is_verified=True, is_active=False)
        db.session.add(sub)
        db.session.commit()

        client.get('/unsubscribe/inactive-token', follow_redirects=True)
        updated = Subscriber.query.filter_by(email='already-inactive@test.com').first()
        assert updated.is_active is False  # Still inactive


class TestBrowseJobsRoute:
    """Public job browser tests."""

    def test_browse_jobs_empty(self, client):
        resp = client.get('/jobs')
        assert resp.status_code == 200

    def test_browse_jobs_with_data(self, client, sample_jobs):
        resp = client.get('/jobs')
        assert resp.status_code == 200
        assert b'Python' in resp.data or b'React' in resp.data

    def test_browse_jobs_search(self, client, sample_jobs):
        resp = client.get('/jobs?search=Python')
        assert resp.status_code == 200
