"""Tests for API endpoints."""
import json


class TestStatsAPI:
    """Dashboard statistics API tests."""

    def test_stats_endpoint(self, client, sample_subscriber, sample_jobs):
        resp = client.get('/api/stats')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'total_subscribers' in data
        assert 'total_jobs' in data
        assert data['total_jobs'] >= 3
        assert data['total_subscribers'] >= 1

    def test_stats_empty(self, client):
        resp = client.get('/api/stats')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['total_subscribers'] == 0
        assert data['total_jobs'] == 0


class TestChartAPI:
    """Chart data API tests."""

    def test_subscriber_chart(self, client):
        resp = client.get('/api/chart/subscribers')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
        assert len(data) > 0
        assert 'date' in data[0]
        assert 'count' in data[0]

    def test_email_chart(self, client):
        resp = client.get('/api/chart/emails')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
        assert 'sent' in data[0]
        assert 'failed' in data[0]

    def test_sources_chart(self, client, sample_jobs):
        resp = client.get('/api/chart/sources')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
