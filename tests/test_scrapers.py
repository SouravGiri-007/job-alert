"""Tests for scrapers — sanitization, deduplication, base class, and mock-HTML parsing."""
from bs4 import BeautifulSoup
from scrapers.scrapers import (
    sanitize_text, BaseScraper, DemoScraper,
    RapidAPIJobsScraper, JSearchScraper,
    get_all_scrapers, get_fallback_scraper,
)


class TestSanitization:
    """Text sanitization tests."""

    def test_sanitize_removes_scripts(self):
        dirty = '<script>alert("xss")</script>Safe Title'
        clean = sanitize_text(dirty)
        assert '<script>' not in clean
        assert 'alert' not in clean
        assert 'Safe Title' in clean

    def test_sanitize_removes_style(self):
        dirty = '<style>body{background:red}</style>Clean Text'
        clean = sanitize_text(dirty)
        assert '<style>' not in clean
        assert 'Clean Text' in clean

    def test_sanitize_strips_unknown_tags(self):
        dirty = '<div>Hello <marquee>world</marquee></div>'
        clean = sanitize_text(dirty)
        assert '<marquee>' not in clean
        assert 'Hello' in clean
        assert 'world' in clean

    def test_sanitize_limits_length(self):
        long_text = 'a' * 3000
        clean = sanitize_text(long_text)
        assert len(clean) <= 2000

    def test_sanitize_empty_string(self):
        assert sanitize_text('') == ''
        assert sanitize_text(None) == ''


class TestBaseScraper:
    """Base scraper tests."""

    def test_deduplicate(self):
        scraper = BaseScraper()
        jobs = [
            {'title': 'Python Dev', 'company': 'Google'},
            {'title': 'Python Dev', 'company': 'Google'},  # Duplicate
            {'title': 'Java Dev', 'company': 'Amazon'},
        ]
        unique = scraper.deduplicate(jobs)
        assert len(unique) == 2

    def test_deduplicate_with_limit(self):
        scraper = BaseScraper()
        jobs = [{'title': f'Job {i}', 'company': 'Co'} for i in range(10)]
        unique = scraper.deduplicate(jobs, limit=5)
        assert len(unique) == 5

    def test_sanitize_job_data(self):
        scraper = BaseScraper()
        job_data = {
            'title': '<script>alert(1)</script>Python Dev',
            'company': 'Safe Co',
            'skills': 'python, flask',
            'url': 'https://example.com',
        }
        clean = scraper.sanitize_job_data(job_data)
        assert '<script>' not in clean['title']
        assert 'Python Dev' in clean['title'] or 'alert' not in clean['title']

    def test_sanitize_job_data_bad_url(self):
        scraper = BaseScraper()
        job_data = {'title': 'Dev', 'url': 'javascript:alert(1)'}
        clean = scraper.sanitize_job_data(job_data)
        assert clean['url'] == ''


class TestDemoScraper:
    """Demo scraper tests."""

    def test_demo_scraper_returns_jobs(self):
        scraper = DemoScraper()
        jobs = scraper.scrape()
        assert len(jobs) >= 2
        assert len(jobs) <= 3
        for job in jobs:
            assert 'title' in job
            assert 'company' in job
            assert 'source' in job


class TestScraperRegistry:
    """Scraper registry tests."""

    def test_get_all_scrapers_excludes_demo(self):
        scrapers = get_all_scrapers()
        names = [s.source_name for s in scrapers]
        assert 'Demo (Fallback)' not in names
        assert 'Internshala' in names
        assert 'JSearch' in names
        assert 'RapidAPI Jobs' in names

    def test_get_fallback_scraper(self):
        scraper = get_fallback_scraper()
        assert scraper.source_name == 'Demo (Fallback)'

    def test_rapidapi_and_jsearch_in_registry(self):
        scrapers = get_all_scrapers()
        names = [s.source_name for s in scrapers]
        assert 'RapidAPI Jobs' in names
        assert 'JSearch' in names


# ── Mock-JSON Response Tests for RapidAPI ─────────────────


# ── Mock-JSON Response Tests for RapidAPI ─────────────────

MOCK_RAPIDAPI_RESPONSE = {
    'data': [
        {
            'title': 'Senior Java Developer',
            'company_name': 'Infosys Technologies',
            'city': 'Bangalore',
            'salary': '12,00,000 - 18,00,000',
            'skills': ['Java', 'Spring Boot', 'Microservices', 'SQL'],
            'url': 'https://example.com/job/java-dev-123',
            'posted_date': '2 days ago',
            'description': 'Looking for senior Java developer with 5+ years of experience in Spring Boot and microservices architecture.',
        },
        {
            'title': 'React Native Developer',
            'company_name': 'Flipkart Pvt Ltd',
            'city': 'Bangalore',
            'salary': '15,00,000 - 22,00,000',
            'skills': ['React Native', 'JavaScript', 'Redux'],
            'url': 'https://example.com/job/rn-dev-456',
            'posted_date': '1 week ago',
            'description': 'Building cross-platform mobile applications for millions of users.',
        },
        {
            'title': 'Data Science Intern',
            'company_name': 'TechStartup',
            'city': 'Hyderabad',
            'salary': '25,000/month',
            'skills': ['Python', 'Machine Learning', 'Statistics', 'TensorFlow'],
            'url': 'https://example.com/job/ds-intern-789',
            'posted_date': 'Today',
            'description': 'Work on cutting-edge ML models for recommendation systems.',
        },
        {
            'title': 'Part-time DevOps Consultant',
            'company_name': 'CloudOps Solutions',
            'city': 'Remote',
            'salary': '',
            'skills': ['Docker', 'Kubernetes', 'AWS', 'Terraform'],
            'url': '',
            'posted_date': '3 days ago',
            'description': 'Part-time role for DevOps automation and cloud infrastructure.',
        },
    ]
}


class TestRapidAPIScraperParsing:
    """RapidAPIJobsScraper _parse_response with mock JSON data."""

    def test_parse_response_basic(self):
        scraper = RapidAPIJobsScraper()
        jobs = []
        count = scraper._parse_response(MOCK_RAPIDAPI_RESPONSE, jobs)

        assert count == 4
        assert len(jobs) == 4

    def test_parse_first_job_fields(self):
        scraper = RapidAPIJobsScraper()
        jobs = []
        scraper._parse_response(MOCK_RAPIDAPI_RESPONSE, jobs)

        job = jobs[0]
        assert 'Senior Java Developer' in job['title']
        assert 'Infosys' in job['company']
        assert 'Bangalore' in job['location']
        assert 'Java' in job['skills']
        assert job['source'] == 'RapidAPI Jobs'
        assert job['job_type'] == 'Full-time'

    def test_parse_internship_job_type(self):
        """Title with 'Intern' should map to Internship."""
        scraper = RapidAPIJobsScraper()
        jobs = []
        scraper._parse_response(MOCK_RAPIDAPI_RESPONSE, jobs)

        assert jobs[2]['job_type'] == 'Internship'

    def test_parse_part_time_job_type(self):
        """Title with 'Part-time' should map to Part-time."""
        scraper = RapidAPIJobsScraper()
        jobs = []
        scraper._parse_response(MOCK_RAPIDAPI_RESPONSE, jobs)

        assert jobs[3]['job_type'] == 'Part-time'

    def test_parse_skills_as_list(self):
        """Skills provided as a list should be joined into a comma-separated string."""
        scraper = RapidAPIJobsScraper()
        jobs = []
        scraper._parse_response(MOCK_RAPIDAPI_RESPONSE, jobs)

        skills = jobs[0]['skills']
        assert 'Java' in skills
        assert 'Spring Boot' in skills
        assert 'Microservices' in skills

    def test_parse_empty_url_becomes_empty_string(self):
        """Jobs with no URL should get an empty string, not a placeholder."""
        scraper = RapidAPIJobsScraper()
        jobs = []
        scraper._parse_response(MOCK_RAPIDAPI_RESPONSE, jobs)

        assert jobs[3]['url'] == ''

    def test_parse_empty_response_dict(self):
        """Empty response should return 0 jobs."""
        scraper = RapidAPIJobsScraper()
        jobs = []
        count = scraper._parse_response({}, jobs)
        assert count == 0
        assert jobs == []

    def test_parse_empty_list(self):
        """Response with empty data list should return 0 jobs."""
        scraper = RapidAPIJobsScraper()
        jobs = []
        count = scraper._parse_response({'data': []}, jobs)
        assert count == 0
        assert jobs == []

    def test_parse_alternate_shape_jobs_key(self):
        """Should handle {'jobs': [...]} shape."""
        scraper = RapidAPIJobsScraper()
        response = {
            'jobs': [
                {'title': 'Python Developer', 'company_name': 'Test Co', 'city': 'Delhi'},
            ]
        }
        jobs = []
        count = scraper._parse_response(response, jobs)
        assert count == 1
        assert 'Python' in jobs[0]['title']

    def test_parse_alternate_shape_direct_array(self):
        """Should handle direct array response."""
        scraper = RapidAPIJobsScraper()
        response = [
            {'title': 'Python Developer', 'company_name': 'Acme', 'city': 'Pune'},
            {'title': 'Go Developer', 'company_name': 'Beta', 'city': 'Chennai'},
        ]
        jobs = []
        count = scraper._parse_response(response, jobs)
        assert count == 2


# ── Mock-JSON Response Tests for JSearch ─────────────────

MOCK_JSEARCH_RESPONSE = {
    'status': 'OK',
    'data': [
        {
            'job_title': 'Senior Python Developer',
            'employer_name': 'Google India',
            'job_city': 'Bangalore',
            'job_state': 'Karnataka',
            'job_country': 'IN',
            'job_min_salary': 2500000,
            'job_max_salary': 4000000,
            'job_description': 'Building scalable backend systems with Python and Django.',
            'job_apply_link': 'https://example.com/apply/python-dev-123',
            'job_required_skills': 'Python, Django, Flask, PostgreSQL',
            'job_employment_type': 'FULLTIME',
            'job_posted_at_datetime_utc': '2026-07-20T10:00:00.000Z',
        },
        {
            'job_title': 'React Native Developer',
            'employer_name': 'Flipkart',
            'job_city': 'Bangalore',
            'job_state': 'Karnataka',
            'job_country': 'IN',
            'job_min_salary': 1500000,
            'job_max_salary': 2500000,
            'job_description': 'Building cross-platform mobile apps.',
            'job_apply_link': 'https://example.com/apply/rn-dev-456',
            'job_required_skills': '',
            'job_employment_type': 'FULLTIME',
            'job_posted_at_datetime_utc': '2026-07-18T08:00:00.000Z',
        },
        {
            'job_title': 'Data Science Intern',
            'employer_name': 'TechStartup',
            'job_city': 'Hyderabad',
            'job_state': 'Telangana',
            'job_country': 'IN',
            'job_min_salary': None,
            'job_max_salary': None,
            'job_description': 'Work on ML models.',
            'job_apply_link': 'https://example.com/apply/ds-intern-789',
            'job_required_skills': ['Python', 'TensorFlow', 'Statistics'],
            'job_employment_type': 'INTERN',
            'job_posted_at_datetime_utc': '2026-07-22T12:00:00.000Z',
        },
        {
            'job_title': 'Part-time DevOps Engineer',
            'employer_name': 'CloudOps',
            'job_city': 'Remote',
            'job_state': '',
            'job_country': 'IN',
            'job_min_salary': 800000,
            'job_max_salary': 1200000,
            'job_description': 'Part-time cloud infrastructure role.',
            'job_apply_link': '',
            'job_required_skills': 'Docker, Kubernetes, AWS',
            'job_employment_type': 'PARTTIME',
            'job_posted_at_datetime_utc': '',
        },
    ]
}


class TestJSearchScraperParsing:
    """JSearchScraper _parse_response with mock JSON data."""

    def test_parse_response_basic(self):
        scraper = JSearchScraper()
        jobs = []
        count = scraper._parse_response(MOCK_JSEARCH_RESPONSE, jobs)

        assert count == 4
        assert len(jobs) == 4

    def test_parse_first_job_fields(self):
        scraper = JSearchScraper()
        jobs = []
        scraper._parse_response(MOCK_JSEARCH_RESPONSE, jobs)

        job = jobs[0]
        assert 'Senior Python Developer' in job['title']
        assert 'Google India' in job['company']
        assert 'Bangalore' in job['location']
        assert 'Karnataka' in job['location']
        assert 'Python' in job['skills']
        assert job['source'] == 'JSearch'
        assert job['job_type'] == 'Full-time'
        assert '2,500,000' in job['salary']
        assert '4,000,000' in job['salary']

    def test_parse_internship_job_type(self):
        """INTERN employment type + 'Intern' in title → Internship."""
        scraper = JSearchScraper()
        jobs = []
        scraper._parse_response(MOCK_JSEARCH_RESPONSE, jobs)

        assert jobs[2]['job_type'] == 'Internship'

    def test_parse_part_time_job_type(self):
        """PARTTIME employment type → Part-time."""
        scraper = JSearchScraper()
        jobs = []
        scraper._parse_response(MOCK_JSEARCH_RESPONSE, jobs)

        assert jobs[3]['job_type'] == 'Part-time'

    def test_parse_skills_inference(self):
        """Skills should be inferred from title when not explicitly provided."""
        scraper = JSearchScraper()
        jobs = []
        scraper._parse_response(MOCK_JSEARCH_RESPONSE, jobs)

        # Job 1 has no required_skills, should infer from title
        skills = jobs[1]['skills'].lower()
        assert 'react' in skills  # 'React Native' in title
        assert 'native' in skills or 'react' in skills

    def test_parse_skills_as_list(self):
        """Skills provided as a list should be joined."""
        scraper = JSearchScraper()
        jobs = []
        scraper._parse_response(MOCK_JSEARCH_RESPONSE, jobs)

        skills = jobs[2]['skills']
        assert 'Python' in skills
        assert 'TensorFlow' in skills
        assert 'Statistics' in skills

    def test_parse_empty_response(self):
        """Empty response should return 0 jobs."""
        scraper = JSearchScraper()
        jobs = []
        count = scraper._parse_response({}, jobs)
        assert count == 0

    def test_parse_empty_data_list(self):
        """Response with empty data list should return 0 jobs."""
        scraper = JSearchScraper()
        jobs = []
        count = scraper._parse_response({'status': 'OK', 'data': []}, jobs)
        assert count == 0
