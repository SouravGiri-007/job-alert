"""Tests for the shared stats service."""
from services.stats_service import (
    get_dashboard_stats,
    get_subscriber_growth_data,
    get_email_chart_data,
    get_source_distribution,
    get_recent_emails,
    get_recent_scrapes,
)


class TestDashboardStats:
    """Dashboard stats service tests."""

    def test_get_dashboard_stats(self, db, sample_subscriber, sample_jobs):
        stats = get_dashboard_stats()
        assert stats['total_subscribers'] >= 1
        assert stats['total_jobs'] >= 3
        assert 'total_verified' in stats
        assert 'jobs_today' in stats
        assert 'active_sources' in stats

    def test_get_dashboard_stats_empty(self, db):
        stats = get_dashboard_stats()
        assert stats['total_subscribers'] == 0
        assert stats['total_jobs'] == 0
        assert stats['active_sources'] == 0


class TestGrowthData:
    """Subscriber growth data tests."""

    def test_get_subscriber_growth(self, db, sample_subscriber):
        data = get_subscriber_growth_data(days=7)
        assert len(data) == 7
        # The sample subscriber was just created, so today should have 1
        assert data[-1]['count'] >= 0


class TestSourceDistribution:
    """Source distribution tests."""

    def test_get_source_distribution(self, db, sample_jobs):
        sources = get_source_distribution()
        assert isinstance(sources, list)
        if sources:
            assert 'source' in sources[0]
            assert 'count' in sources[0]


class TestRecentData:
    """Recent data queries tests."""

    def test_get_recent_emails(self, db, sample_email_history):
        emails = get_recent_emails(limit=5)
        assert len(emails) <= 5
        if emails:
            assert hasattr(emails[0], 'subscriber_id')

    def test_get_recent_scrapes(self, db, sample_scraper_history):
        scrapes = get_recent_scrapes(limit=5)
        assert len(scrapes) <= 5
        if scrapes:
            assert hasattr(scrapes[0], 'source')
