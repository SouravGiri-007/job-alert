"""Tests for the job matching engine."""
from datetime import datetime, timezone
from models.subscriber import Subscriber
from models.job import Job
from services.matching_service import calculate_match_score, find_matching_jobs


class TestCalculateMatchScore:
    """Tests for the core scoring algorithm."""

    def setup_subscriber(self, **kwargs):
        defaults = dict(email='test@test.com', is_verified=True, is_active=True)
        defaults.update(kwargs)
        sub = Subscriber(**defaults)
        sub.id = 1
        return sub

    def setup_job(self, **kwargs):
        defaults = dict(title='Python Developer', company='Acme', location='Bangalore, India',
                        salary='10 LPA', skills='python, django, sql', job_type='Full-time',
                        source='Test', scraped_at=datetime.now(timezone.utc))
        defaults.update(kwargs)
        job = Job(**defaults)
        job.id = 1
        return job

    def test_perfect_match(self):
        """A job matching all subscriber preferences should score 1.0."""
        sub = self.setup_subscriber(skills='python, django', role='Python Developer',
                                    location='Bangalore', job_type='Full-time')
        job = self.setup_job(title='Senior Python Developer', skills='python, django, flask',
                             location='Bangalore, India', job_type='Full-time')
        score = calculate_match_score(sub, job)
        assert score == 1.0, f'Expected 1.0, got {score}'

    def test_skills_no_overlap_returns_zero(self):
        """Zero skill overlap should hard-reject with score 0.0."""
        sub = self.setup_subscriber(skills='java, spring, kotlin')
        job = self.setup_job(skills='python, django, react')
        score = calculate_match_score(sub, job)
        assert score == 0.0, f'Expected 0.0, got {score}'

    def test_partial_role_match_with_aliases(self):
        """Role aliases like 'developer' matching 'engineer' should get partial score."""
        sub = self.setup_subscriber(role='frontend developer', location='Bangalore')
        job = self.setup_job(title='Front End Engineer', location='Bangalore, India')
        score = calculate_match_score(sub, job)
        assert score > 0, f'Expected > 0 for alias match, got {score}'
        assert score < 1.0, 'Alias match should not be perfect'

    def test_remote_location_matches_anything(self):
        """If subscriber wants remote, any location should match."""
        sub = self.setup_subscriber(location='Remote', skills='python')
        job = self.setup_job(location='Bangalore, India', skills='python, django')
        score = calculate_match_score(sub, job)
        assert score > 0, f'Remote preference should match any location, got {score}'

    def test_wrong_job_type_returns_zero(self):
        """If subscriber wants Internship but job is Full-time, reject."""
        sub = self.setup_subscriber(job_type='Internship', skills='python')
        job = self.setup_job(job_type='Full-time', skills='python, django')
        score = calculate_match_score(sub, job)
        assert score == 0.0, f'Wrong job type should yield 0.0, got {score}'

    def test_no_preferences_scores_zero(self):
        """Subscriber with no preferences should score 0 (handled upstream)."""
        sub = self.setup_subscriber(skills='', role='', location='', job_type='')
        job = self.setup_job()
        score = calculate_match_score(sub, job)
        assert score == 0.0

    def test_city_alias_matches(self):
        """City aliases like Bengaluru should match Bangalore."""
        sub = self.setup_subscriber(location='Bangalore', skills='python')
        job = self.setup_job(location='Bengaluru, India', skills='python, django')
        score = calculate_match_score(sub, job)
        assert score > 0, f'City alias should match, got {score}'


class TestFindMatchingJobs:
    """Tests for the find_matching_jobs function."""

    def test_returns_matched_jobs(self, db, sample_subscriber, sample_jobs):
        """Should return only jobs meeting the minimum score."""
        matched = find_matching_jobs(sample_subscriber, jobs=sample_jobs)
        assert len(matched) == 1, f'Expected 1 match for Python/location, got {len(matched)}'
        assert 'Python' in matched[0].title

    def test_no_preferences_returns_latest(self, db, sample_jobs):
        """Subscriber with no prefs should get up to 20 latest jobs."""
        sub = Subscriber(email='noprefs@test.com', is_verified=True, is_active=True)
        matched = find_matching_jobs(sub, jobs=sample_jobs)
        assert len(matched) == 3, f'With no prefs, should return all jobs, got {len(matched)}'

    def test_no_jobs_returns_empty(self, db, sample_subscriber):
        """No jobs available should return empty list."""
        matched = find_matching_jobs(sample_subscriber, jobs=[])
        assert matched == []
