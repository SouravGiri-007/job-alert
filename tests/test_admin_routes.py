"""Tests for admin routes."""


class TestAdminLogin:
    """Admin login tests."""

    def test_login_page_loads(self, client):
        resp = client.get('/admin/login')
        assert resp.status_code == 200
        assert b'Admin Login' in resp.data or b'login' in resp.data.lower()

    def test_login_success(self, client):
        resp = client.post('/admin/login', data={
            'username': 'testadmin',
            'password': 'testpass123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Should redirect to dashboard
        assert b'Dashboard' in resp.data or b'dashboard' in resp.data

    def test_login_failure(self, client):
        resp = client.post('/admin/login', data={
            'username': 'wrong',
            'password': 'wrong',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Invalid' in resp.data

    def test_logout(self, client):
        client.post('/admin/login', data={
            'username': 'testadmin',
            'password': 'testpass123',
        })
        resp = client.get('/admin/logout', follow_redirects=True)
        assert resp.status_code == 200

    def test_dashboard_requires_login(self, client):
        resp = client.get('/admin/', follow_redirects=True)
        assert resp.status_code == 200
        # Should redirect to login
        assert b'Admin Login' in resp.data or b'login' in resp.data.lower()


class TestAdminDashboard:
    """Admin dashboard tests."""

    def test_dashboard_shows_stats(self, admin_session, sample_jobs, sample_email_history,
                                   sample_scraper_history):
        resp = admin_session.get('/admin/', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Dashboard' in resp.data or b'dashboard' in resp.data.lower()

    def test_dashboard_has_manual_actions(self, admin_session):
        resp = admin_session.get('/admin/', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Run Scraper' in resp.data or b'run-scraper' in resp.data


class TestAdminSubscribers:
    """Admin subscriber management tests."""

    def test_subscribers_page(self, admin_session, sample_subscriber):
        resp = admin_session.get('/admin/subscribers', follow_redirects=True)
        assert resp.status_code == 200
        assert b'test@example.com' in resp.data

    def test_subscribers_search(self, admin_session, sample_subscriber):
        resp = admin_session.get('/admin/subscribers?search=test', follow_redirects=True)
        assert resp.status_code == 200
        assert b'test@example.com' in resp.data

    def test_subscribers_filter_verified(self, admin_session, sample_subscriber):
        resp = admin_session.get('/admin/subscribers?status=verified', follow_redirects=True)
        assert resp.status_code == 200

    def test_subscribers_export(self, admin_session, sample_subscriber):
        resp = admin_session.get('/admin/subscribers/export', follow_redirects=True)
        assert resp.status_code == 200
        assert b'test@example.com' in resp.data or 'test@example.com' in resp.data.decode()

    def test_delete_subscriber(self, admin_session, sample_subscriber):
        resp = admin_session.post(f'/admin/subscribers/delete/{sample_subscriber.id}',
                                  follow_redirects=True)
        assert resp.status_code == 200


class TestAdminJobs:
    """Admin job management tests."""

    def test_jobs_page(self, admin_session, sample_jobs):
        resp = admin_session.get('/admin/jobs', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Python' in resp.data or b'Senior' in resp.data

    def test_job_detail(self, admin_session, sample_jobs):
        job = sample_jobs[0]
        resp = admin_session.get(f'/admin/jobs/{job.id}', follow_redirects=True)
        assert resp.status_code == 200

    def test_clear_old_jobs(self, admin_session, sample_jobs):
        resp = admin_session.post('/admin/jobs/clear-old', follow_redirects=True)
        assert resp.status_code == 200
