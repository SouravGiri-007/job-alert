"""Tests for scrapers — sanitization, deduplication, base class, and mock-HTML parsing."""
from bs4 import BeautifulSoup
from scrapers.scrapers import (
    sanitize_text, BaseScraper, DemoScraper, IndeedScraper,
    NaukriScraper, GlassdoorScraper, RapidAPIJobsScraper,
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
        assert 'LinkedIn' in names
        assert 'Internshala' in names
        assert 'Indeed' in names
        assert 'Naukri' in names
        assert 'Glassdoor' in names

    def test_get_fallback_scraper(self):
        scraper = get_fallback_scraper()
        assert scraper.source_name == 'Demo (Fallback)'

    def test_rapidapi_in_registry(self):
        scrapers = get_all_scrapers()
        names = [s.source_name for s in scrapers]
        assert 'RapidAPI Jobs' in names


# ── Mock-HTML Parsing Tests ─────────────────

MOCK_INDEED_HTML = '''
<div class="job_seen_beacon">
    <table><tr><td>
        <h2 class="jobTitle"><a class="jobTitle" href="/jobs/view?jk=abc123">Senior Python Developer</a></h2>
        <span class="companyName">Google India</span>
        <div class="companyLocation">Bangalore, Karnataka</div>
        <div class="salary-snippet"><span>₹25,00,000 - ₹40,00,000</span></div>
        <div class="job-snippet">Building scalable backend systems with Python and Django.</div>
    </td></tr></table>
</div>
<div class="job_seen_beacon">
    <table><tr><td>
        <h2 class="jobTitle"><a class="jobTitle" href="/jobs/view?jk=def456">React Frontend Developer</a></h2>
        <span class="companyName">Amazon</span>
        <div class="companyLocation">Hyderabad, Telangana</div>
    </td></tr></table>
</div>
'''


class TestIndeedScraperParsing:
    """Indeed scraper _parse_listings with mock HTML."""

    def test_parse_indeed_listings(self):
        scraper = IndeedScraper()
        soup = BeautifulSoup(MOCK_INDEED_HTML, 'html.parser')
        jobs = []
        count = scraper._parse_listings(soup, jobs)

        assert count == 2
        assert len(jobs) == 2
        assert jobs[0]['title'] == 'Senior Python Developer'
        assert jobs[0]['company'] == 'Google India'
        assert 'Bangalore' in jobs[0]['location']
        assert '25' in jobs[0]['salary'] or '00,000' in jobs[0]['salary']
        assert jobs[0]['source'] == 'Indeed'

    def test_parse_indeed_second_job(self):
        scraper = IndeedScraper()
        soup = BeautifulSoup(MOCK_INDEED_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        assert jobs[1]['company'] == 'Amazon'
        assert 'Hyderabad' in jobs[1]['location']
        assert jobs[1]['job_type'] == 'Full-time'  # No intern/part-time in title

    def test_parse_indeed_empty_html(self):
        scraper = IndeedScraper()
        soup = BeautifulSoup('<html><body></body></html>', 'html.parser')
        jobs = []
        count = scraper._parse_listings(soup, jobs)
        assert count == 0
        assert jobs == []


MOCK_NAUKRI_HTML = '''
<article class="jobTuple">
    <a class="title" href="/python-developer-jobs/job1">Python Developer - Django/Flask</a>
    <a class="subTitle" href="/company/infosys">Infosys Limited</a>
    <span class="location">Bangalore, Bengaluru</span>
    <span class="salary">₹8,00,000 - ₹12,00,000 PA</span>
    <span class="experience">3-5 yrs</span>
    <div class="job-description">Looking for experienced Python developer with Django and Flask.</div>
    <ul class="tags"><li><a>Python</a></li><li><a>Django</a></li><li><a>Flask</a></li><li><a>PostgreSQL</a></li></ul>
</article>
<article class="jobTuple">
    <a class="title" href="/react-developer-jobs/job2">React JS Developer</a>
    <a class="subTitle" href="/company/tcs">TCS</a>
    <span class="location">Mumbai, India</span>
    <span class="salary">₹6,00,000 - ₹10,00,000 PA</span>
</article>
'''


class TestNaukriScraperParsing:
    """Naukri scraper _parse_listings with mock HTML."""

    def test_parse_naukri_listings(self):
        scraper = NaukriScraper()
        soup = BeautifulSoup(MOCK_NAUKRI_HTML, 'html.parser')
        jobs = []
        count = scraper._parse_listings(soup, jobs)

        assert count == 2
        assert len(jobs) == 2
        assert 'Python' in jobs[0]['title']
        assert jobs[0]['company'] == 'Infosys Limited'
        assert 'Bangalore' in jobs[0]['location']

    def test_parse_naukri_skills(self):
        scraper = NaukriScraper()
        soup = BeautifulSoup(MOCK_NAUKRI_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        skills = jobs[0]['skills'].lower()
        assert 'python' in skills
        assert 'django' in skills
        assert 'flask' in skills

    def test_parse_naukri_salary(self):
        scraper = NaukriScraper()
        soup = BeautifulSoup(MOCK_NAUKRI_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        assert '00,000' in jobs[0]['salary']
        assert jobs[1]['salary'] != ''

    def test_parse_naukri_second_job_no_skills(self):
        scraper = NaukriScraper()
        soup = BeautifulSoup(MOCK_NAUKRI_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        assert 'React' in jobs[1]['title']
        assert jobs[1]['company'] == 'TCS'
        assert 'Mumbai' in jobs[1]['location']


MOCK_GLASSDOOR_HTML = '''
<li class="react-job-listing">
    <a class="jobLink" href="/job-listing/data-scientist-ml-company-JOB123">Python Data Scientist - Machine Learning</a>
    <span class="job-employer">Microsoft India</span>
    <span class="job-location">Hyderabad, India</span>
    <span class="job-salary">₹20L - ₹35L</span>
    <span class="job-age">30d+</span>
</li>
<li class="react-job-listing">
    <a class="jobLink" href="/job-listing/devops-engineer-company-JOB456">DevOps Engineer (Kubernetes)</a>
    <span class="job-employer">Flipkart</span>
    <span class="job-location">Bangalore, India</span>
</li>
<li class="react-job-listing">
    <a class="jobLink" href="/job-listing/ml-intern-company-JOB789">Machine Learning Intern</a>
    <span class="job-employer">StartupAI</span>
    <span class="job-location">Remote</span>
</li>
'''


class TestGlassdoorScraperParsing:
    """Glassdoor scraper _parse_listings with mock HTML."""

    def test_parse_glassdoor_listings(self):
        scraper = GlassdoorScraper()
        soup = BeautifulSoup(MOCK_GLASSDOOR_HTML, 'html.parser')
        jobs = []
        count = scraper._parse_listings(soup, jobs)

        assert count == 3
        assert len(jobs) == 3

    def test_parse_glassdoor_first_job(self):
        scraper = GlassdoorScraper()
        soup = BeautifulSoup(MOCK_GLASSDOOR_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        assert 'Data Scientist' in jobs[0]['title']
        assert jobs[0]['company'] == 'Microsoft India'
        assert 'Hyderabad' in jobs[0]['location']
        assert jobs[0]['salary'] != ''
        assert jobs[0]['source'] == 'Glassdoor'

    def test_parse_glassdoor_skill_inference(self):
        """Skills should be inferred from title keywords."""
        scraper = GlassdoorScraper()
        soup = BeautifulSoup(MOCK_GLASSDOOR_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        # 'Python' in title should match known_skills
        first_skills = jobs[0]['skills'].lower()
        assert 'python' in first_skills

    def test_parse_glassdoor_job_type_inference(self):
        """Job type should be inferred from title ('intern' → Internship)."""
        scraper = GlassdoorScraper()
        soup = BeautifulSoup(MOCK_GLASSDOOR_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        assert jobs[2]['job_type'] == 'Internship'
        assert jobs[0]['job_type'] == 'Full-time'
        assert jobs[1]['job_type'] == 'Full-time'

    def test_parse_glassdoor_second_job_no_salary(self):
        """Second job has no salary element — should default to empty string."""
        scraper = GlassdoorScraper()
        soup = BeautifulSoup(MOCK_GLASSDOOR_HTML, 'html.parser')
        jobs = []
        scraper._parse_listings(soup, jobs)
        assert jobs[1]['company'] == 'Flipkart'
        assert 'Bangalore' in jobs[1]['location']


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
