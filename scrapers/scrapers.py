"""Scraper base class and implementations for job sources.
Lightweight sanitization via regex — no heavy HTML parser dependencies.
"""
from bs4 import BeautifulSoup
import requests
import cloudscraper
import re
import time
import random
from datetime import datetime, timezone

from utils.logger import get_logger, log_event

logger = get_logger('scrapers')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-IN,en-US;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}


def sanitize_text(text):
    """Sanitize scraped text: strip HTML tags, dangerous content, limit length.
    Uses lightweight regex instead of bleach/html5lib to avoid OOM on low-memory hosts.
    """
    if not text:
        return ''
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Strip all remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'&#\d+;', ' ', text)  # Numeric entities
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Limit length
    return text[:2000]


def get_session():
    """Create a fresh session with Cloudflare bypass.
    Uses cloudscraper to automatically solve Cloudflare JavaScript challenges.
    Falls back to regular requests.Session if cloudscraper fails.
    """
    try:
        s = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
            },
            delay=15,
        )
    except Exception as e:
        logger.warning(f'cloudscraper init failed ({e}), falling back to requests.Session')
        s = requests.Session()

    s.headers.update(HEADERS)
    uas = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    ]
    s.headers['User-Agent'] = random.choice(uas)
    return s


class BaseScraper:
    """Base class for all scrapers."""

    source_name = 'base'
    base_url = ''

    def scrape(self):
        raise NotImplementedError

    def fetch_page(self, url, params=None, session=None):
        """Fetch a page with error handling and rate limiting."""
        s = session or get_session()
        try:
            time.sleep(random.uniform(1.5, 3.0))
            response = s.get(url, params=params, timeout=30, allow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'text/xml' not in content_type:
                logger.warning(f'Non-HTML response from {url}: {content_type}')
                return None

            text = response.text
            text_lower = text.lower()
            block_signals = [
                'captcha', 'robot check', 'access denied', 'cloudflare',
                'just a moment', 'blocked', 'unusual traffic',
                'verify you are human', 'checking your browser',
            ]
            for signal in block_signals:
                if signal in text_lower and len(text) < 15000:
                    logger.warning(f'Blocked by anti-bot on {url} (signal: {signal})')
                    return None

            return BeautifulSoup(text, 'html.parser')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (403, 429, 503):
                logger.warning(f'Rate-limited/blocked ({e.response.status_code}) on {url}')
            else:
                logger.error(f'HTTP error {e.response.status_code} on {url}')
            return None
        except requests.exceptions.Timeout:
            logger.warning(f'Timeout fetching {url}')
            return None
        except requests.exceptions.ConnectionError as e:
            logger.warning(f'Connection error on {url}: {str(e)[:80]}')
            return None
        except Exception as e:
            logger.error(f'Failed to fetch {url}: {e}')
            return None

    def clean_text(self, text):
        if not text:
            return ''
        cleaned = ' '.join(text.strip().split())
        return sanitize_text(cleaned)

    def sanitize_job_data(self, job_data):
        """Apply sanitization to all text fields in a job data dict."""
        for key in ['title', 'company', 'location', 'salary', 'skills', 'description']:
            if key in job_data:
                job_data[key] = self.clean_text(job_data.get(key, ''))
        if 'url' in job_data and job_data['url']:
            # Basic URL validation
            url = job_data['url']
            if not url.startswith(('http://', 'https://')):
                job_data['url'] = ''
        return job_data

    def deduplicate(self, jobs, key_fields=('title', 'company'), limit=50):
        """Deduplicate jobs by key fields."""
        seen = set()
        unique = []
        for j in jobs:
            key = tuple(j.get(f, '').lower() for f in key_fields)
            if key not in seen:
                seen.add(key)
                unique.append(j)
        return unique[:limit]


# ─────────────────────────────────────────────
# 1. Internshala Scraper
# ─────────────────────────────────────────────
class InternshalaScraper(BaseScraper):
    """Scraper for Internshala - India's largest internship platform."""

    source_name = 'Internshala'
    base_url = 'https://internshala.com'

    SEARCH_URLS = [
        'https://internshala.com/internships/work-from-home/web-development,backend-development,frontend-development,app-development,machine-learning,data-science',
        'https://internshala.com/internships/web-development,backend-development,frontend-development,app-development,machine-learning,data-science,python,java,react,node-js',
        'https://internshala.com/jobs/',
        'https://internshala.com/jobs/work-from-home',
        'https://internshala.com/internships/work-from-home',
    ]

    def scrape(self):
        jobs = []
        session = get_session()
        for url in self.SEARCH_URLS:
            try:
                soup = self.fetch_page(url, session=session)
                if not soup:
                    continue
                found = self._parse_listings(soup, jobs)
                logger.info(f'Internshala: {found} jobs from {url.split(".com")[1][:50]}')
            except Exception as e:
                logger.error(f'Error scraping {self.source_name}: {e}')

        return self.deduplicate(jobs, limit=60)

    def _parse_listings(self, soup, jobs):
        listings = soup.select('div.individual_internship')
        count = 0
        for listing in listings:
            try:
                title_el = listing.select_one('a.job-title-href')
                if not title_el:
                    continue
                title = self.clean_text(title_el.get_text())
                href = title_el.get('href', '')
                if href and not href.startswith('http'):
                    href = self.base_url + href
                if not title or len(title) < 3:
                    continue

                company_el = listing.select_one('p.company-name')
                company = self.clean_text(company_el.get_text()) if company_el else ''

                loc_el = listing.select_one('div.locations')
                location = self.clean_text(loc_el.get_text()) if loc_el else 'India'

                stipend_el = listing.select_one('span.stipend')
                salary = self.clean_text(stipend_el.get_text()) if stipend_el else ''

                detail_items = listing.select('div.detail-row-1 div.row-1-item')
                duration = ''
                for item in detail_items:
                    text = self.clean_text(item.get_text())
                    if re.search(r'month|week|day', text, re.I):
                        duration = text
                        break

                skill_els = listing.select('span.job_skill')
                skills = ', '.join([self.clean_text(s.get_text()) for s in skill_els])

                is_job = '/jobs/' in href
                job_type = 'Job' if is_job else 'Internship'

                job_data = {
                    'title': title,
                    'company': company,
                    'location': location if location else 'India',
                    'salary': salary,
                    'skills': skills,
                    'url': href,
                    'source': self.source_name,
                    'job_type': job_type,
                    'posted_date': 'Recently',
                    'description': f"{duration} {'(Work from home)' if 'work-from-home' in href else ''}".strip(),
                }
                jobs.append(self.sanitize_job_data(job_data))
                count += 1
            except Exception as e:
                logger.debug(f'Skip listing: {e}')
                continue
        return count


# ─────────────────────────────────────────────
# 2. Demo Fallback (only used if all real scrapers return 0)
# ─────────────────────────────────────────────
class DemoScraper(BaseScraper):
    """Fallback demo scraper — only used when real scrapers return 0 jobs."""

    source_name = 'Demo (Fallback)'
    base_url = ''

    SAMPLE_JOBS = [
        {'title': 'Python Developer', 'company': 'TCS', 'location': 'Bangalore, India', 'salary': '8-15 LPA', 'skills': 'python, django, flask, sql', 'url': 'https://internshala.com', 'source': 'Demo (Fallback)', 'job_type': 'Full-time', 'description': '', 'posted_date': 'Recently'},
        {'title': 'React Developer', 'company': 'Infosys', 'location': 'Hyderabad, India', 'salary': '6-12 LPA', 'skills': 'react, javascript, redux, css', 'url': 'https://internshala.com', 'source': 'Demo (Fallback)', 'job_type': 'Full-time', 'description': '', 'posted_date': 'Recently'},
        {'title': 'Data Analytics Intern', 'company': 'StartupXYZ', 'location': 'Remote, India', 'salary': '10-20k/month', 'skills': 'python, excel, sql, tableau', 'url': 'https://internshala.com', 'source': 'Demo (Fallback)', 'job_type': 'Internship', 'description': '', 'posted_date': 'Recently'},
    ]

    def scrape(self):
        import random
        count = random.randint(2, 3)
        selected = random.sample(self.SAMPLE_JOBS, min(count, len(self.SAMPLE_JOBS)))
        return [self.sanitize_job_data(job.copy()) for job in selected]


# ─────────────────────────────────────────────
# 3. RapidAPI Indian Jobs Scraper
# ─────────────────────────────────────────────
class RapidAPIJobsScraper(BaseScraper):
    """Scraper for the Indian Jobs API via RapidAPI.
    Uses POST requests with JSON payload to fetch structured job data.

    Requires RAPIDAPI_KEY to be set in the app config (or env var).
    """

    source_name = 'RapidAPI Jobs'
    base_url = 'https://indian-jobs-api.p.rapidapi.com'

    SEARCH_QUERIES = [
        ('python developer', 'Bangalore'),
        ('python developer', 'Hyderabad'),
        ('react developer', 'Bangalore'),
        ('java developer', 'Bangalore'),
        ('java developer', 'Mumbai'),
        ('data scientist', 'Bangalore'),
        ('full stack developer', 'Bangalore'),
        ('full stack developer', 'Delhi'),
        ('devops engineer', 'Bangalore'),
        ('frontend developer', 'Bangalore'),
        ('backend developer', 'Bangalore'),
        ('machine learning engineer', 'Hyderabad'),
        ('software engineer', 'Bangalore'),
        ('software engineer', 'Pune'),
    ]

    def _get_api_key(self):
        """Retrieve the Indian Jobs RapidAPI key from config, falling back to env."""
        try:
            from flask import current_app
            key = current_app.config.get('RAPIDAPI_INDIANJOBS_KEY', '')
        except (RuntimeError, ImportError):
            import os
            key = os.environ.get('RAPIDAPI_INDIANJOBS_KEY', '')
        if not key:
            logger.warning('RAPIDAPI_INDIANJOBS_KEY not configured — RapidAPIJobsScraper will return 0 jobs')
        return key

    def _get_api_host(self):
        """Retrieve the RapidAPI host from config."""
        try:
            from flask import current_app
            host = current_app.config.get('RAPIDAPI_INDIANJOBS_HOST', 'indian-jobs-api.p.rapidapi.com')
        except (RuntimeError, ImportError):
            host = 'indian-jobs-api.p.rapidapi.com'
        return host

    def scrape(self):
        api_key = self._get_api_key()
        if not api_key:
            return []

        api_host = self._get_api_host()
        url = f'{self.base_url}/api/v1/get-job-listings'

        headers = {
            'Content-Type': 'application/json',
            'x-rapidapi-host': api_host,
            'x-rapidapi-key': api_key,
        }

        jobs = []

        for query, city in self.SEARCH_QUERIES:
            try:
                payload = {
                    'search': query,
                    'city': city,
                    'workMode': 0,
                    'experience': 0,
                    'jobAge': 30,
                    'page': 1,
                }

                time.sleep(random.uniform(0.3, 0.8))
                response = requests.post(url, json=payload, headers=headers, timeout=25)

                if response.status_code == 429:
                    logger.warning(f'RapidAPI rate-limited — backing off')
                    time.sleep(5)
                    continue

                if response.status_code == 401 or response.status_code == 403:
                    logger.error(f'RapidAPI auth failed ({response.status_code}) — check RAPIDAPI_KEY')
                    break

                response.raise_for_status()

                data = response.json()
                found = self._parse_response(data, jobs)

                if found > 0:
                    logger.info(f'RapidAPI Jobs: {found} jobs for "{query}" in {city}')

                if len(jobs) >= 60:
                    break

            except requests.exceptions.Timeout:
                logger.warning(f'RapidAPI timeout for {query} in {city}')
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f'RapidAPI request error for {query}: {e}')
                continue
            except ValueError as e:
                logger.warning(f'RapidAPI JSON parse error for {query}: {e}')
                continue
            except Exception as e:
                logger.error(f'RapidAPI error for {query}: {e}')
                continue

        return self.deduplicate(jobs, limit=60)

    def _parse_response(self, data, jobs):
        """Parse the JSON response from RapidAPI into job data dicts.

        Handles multiple possible response shapes:
          - {'data': [{'title': '...', 'company_name': '...', ...}, ...]}
          - {'jobs': [{'title': '...', 'company_name': '...', ...}, ...]}
          - {'results': [{'title': '...', 'company_name': '...', ...}, ...]}
          - Direct array: [{'title': '...', ...}, ...]
        """
        listings = []

        if isinstance(data, list):
            listings = data
        elif isinstance(data, dict):
            for key in ('data', 'jobs', 'results', 'listings', 'jobList', 'items', 'records'):
                candidate = data.get(key, [])
                if isinstance(candidate, list) and len(candidate) > 0:
                    listings = candidate
                    break
            # Also check for nested structure like {'response': {'data': [...]}}
            if not listings:
                for key in ('response', 'result', 'output'):
                    nested = data.get(key, {})
                    if isinstance(nested, dict):
                        listings = self._extract_list_from_dict(nested)
                        if listings:
                            break

        if not listings:
            return 0

        count = 0
        for item in listings[:30]:
            try:
                if not isinstance(item, dict):
                    continue

                # Extract fields with flexible key matching
                title = self._get_field(item, ['title', 'jobTitle', 'job_title', 'position', 'name', 'designation'])
                if not title or len(title) < 4:
                    continue

                company = self._get_field(item, ['company', 'company_name', 'companyName', 'employer', 'organization', 'firm', 'companyName_raw'])
                location = self._get_field(item, ['location', 'city', 'job_location', 'jobLocation', 'loc', 'work_location', 'place'])
                salary = self._get_field(item, ['salary', 'salary_range', 'salaryRange', 'pay', 'compensation', 'stipend', 'salary_max', 'salary_min', 'salary_range_raw'])
                description = self._get_field(item, ['description', 'job_description', 'jobDescription', 'desc', 'summary', 'details'])
                url = self._get_field(item, ['url', 'link', 'apply_url', 'applyLink', 'job_url', 'jobUrl', 'source_url'])
                posted_date = self._get_field(item, ['posted_date', 'postedDate', 'date', 'created_at', 'createdAt', 'published_date', 'publishedDate', 'age'])

                # Handle skills — could be a string or list
                skills_raw = self._get_field(item, ['skills', 'skill', 'key_skills', 'keySkills', 'tags', 'technologies'])
                if isinstance(skills_raw, list):
                    skills = ', '.join(str(s) for s in skills_raw if s)
                else:
                    skills = str(skills_raw) if skills_raw else ''

                location = location if location else 'India'

                # Infer job type from title
                job_type = 'Full-time'
                title_lower = title.lower()
                if 'intern' in title_lower:
                    job_type = 'Internship'
                elif 'part-time' in title_lower or 'part time' in title_lower:
                    job_type = 'Part-time'
                elif 'contract' in title_lower:
                    job_type = 'Contract'
                elif 'freelance' in title_lower:
                    job_type = 'Freelance'

                # Infer skills from title if none provided
                if not skills:
                    known_skills = ['python', 'java', 'javascript', 'react', 'angular', 'vue',
                                    'aws', 'docker', 'kubernetes', 'node', 'django', 'flask',
                                    'sql', 'mongodb', 'typescript', 'go', 'rust', 'c++', 'ruby']
                    matched = [s for s in known_skills if s in title_lower]
                    if matched:
                        skills = ', '.join(matched)

                # Format salary if it's a number
                if salary and salary.replace('.', '').replace('-', '').isdigit():
                    try:
                        sal_val = float(salary.replace('-', '').strip())
                        if sal_val < 1000:  # Looks like an hourly/daily rate
                            salary = f'₹{salary}'
                        else:
                            salary = f'₹{int(sal_val):,}'
                    except (ValueError, TypeError):
                        pass

                job_data = {
                    'title': title,
                    'company': company if company else 'Unknown',
                    'location': location,
                    'salary': salary if salary else '',
                    'skills': skills,
                    'url': url if url else '',
                    'source': self.source_name,
                    'job_type': job_type,
                    'posted_date': posted_date if posted_date else 'Recently',
                    'description': description if description else '',
                }
                jobs.append(self.sanitize_job_data(job_data))
                count += 1
            except Exception as e:
                logger.debug(f'Skip RapidAPI listing: {e}')
                continue

        return count

    def _get_field(self, item, possible_keys):
        """Get a field value from a dict, trying multiple possible keys."""
        for key in possible_keys:
            value = item.get(key)
            if value is not None and value != '':
                return str(value)
        return ''

    @staticmethod
    def _extract_list_from_dict(d):
        """Recursively search a dict for the first list value."""
        for key, value in d.items():
            if isinstance(value, list) and len(value) > 0:
                return value
        for key, value in d.items():
            if isinstance(value, dict):
                result = RapidAPIJobsScraper._extract_list_from_dict(value)
                if result:
                    return result
        return []


# ─────────────────────────────────────────────
# 4. JSearch API Scraper (replaces Indeed, Glassdoor, LinkedIn)
# ─────────────────────────────────────────────
class JSearchScraper(BaseScraper):
    """Job search via JSearch RapidAPI — aggregates data from Indeed, Glassdoor, LinkedIn, and more.

    API: GET https://jsearch.p.rapidapi.com/search
    Requires RAPIDAPI_JSEARCH_KEY to be set in the app config.
    """

    source_name = 'JSearch'
    base_url = 'https://jsearch.p.rapidapi.com'

    SEARCH_QUERIES = [
        'python developer India',
        'react developer India',
        'java developer India',
        'data scientist India',
        'full stack developer India',
        'devops engineer India',
        'frontend developer India',
        'backend developer India',
        'machine learning engineer India',
        'software engineer Bangalore',
    ]

    def _get_api_key(self):
        try:
            from flask import current_app
            key = current_app.config.get('RAPIDAPI_JSEARCH_KEY', '')
        except (RuntimeError, ImportError):
            import os
            key = os.environ.get('RAPIDAPI_JSEARCH_KEY', '')
        if not key:
            logger.warning('RAPIDAPI_JSEARCH_KEY not configured — JSearchScraper will return 0 jobs')
        return key

    def _get_api_host(self):
        try:
            from flask import current_app
            host = current_app.config.get('RAPIDAPI_JSEARCH_HOST', 'jsearch.p.rapidapi.com')
        except (RuntimeError, ImportError):
            host = 'jsearch.p.rapidapi.com'
        return host

    def scrape(self):
        api_key = self._get_api_key()
        if not api_key:
            return []

        api_host = self._get_api_host()
        headers = {
            'x-rapidapi-host': api_host,
            'x-rapidapi-key': api_key,
        }

        jobs = []

        for query in self.SEARCH_QUERIES:
            try:
                params = {
                    'query': query,
                    'page': '1',
                    'num_pages': '1',
                    'country': 'in',
                }

                time.sleep(random.uniform(0.5, 1.0))
                response = requests.get(
                    f'{self.base_url}/search',
                    params=params,
                    headers=headers,
                    timeout=20,
                )

                if response.status_code == 429:
                    logger.warning('JSearch rate-limited — backing off')
                    time.sleep(5)
                    continue

                if response.status_code == 401 or response.status_code == 403:
                    logger.error(f'JSearch auth failed ({response.status_code}) — check RAPIDAPI_JSEARCH_KEY')
                    break

                response.raise_for_status()
                data = response.json()
                found = self._parse_response(data, jobs)

                if found > 0:
                    logger.info(f'JSearch: {found} jobs for "{query}"')

                if len(jobs) >= 80:
                    break

            except requests.exceptions.Timeout:
                logger.warning(f'JSearch timeout for "{query}"')
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f'JSearch request error for "{query}": {e}')
                continue
            except ValueError as e:
                logger.warning(f'JSearch JSON parse error for "{query}": {e}')
                continue
            except Exception as e:
                logger.error(f'JSearch error for "{query}": {e}')
                continue

        return self.deduplicate(jobs, limit=80)

    def _parse_response(self, data, jobs):
        """Parse JSearch API response into job data dicts.

        Expected response shape:
        {
            'status': 'OK',
            'data': [
                {
                    'job_title': '...',
                    'employer_name': '...',
                    'job_city': '...',
                    'job_state': '...',
                    'job_country': 'IN',
                    'job_min_salary': ...,
                    'job_max_salary': ...,
                    'job_description': '...',
                    'job_apply_link': '...',
                    'job_required_skills': '...',
                    'job_employment_type': 'FULLTIME',
                    'job_posted_at_datetime_utc': '...',
                }
            ]
        }
        """
        if not isinstance(data, dict):
            return 0

        listings = data.get('data', [])
        if not isinstance(listings, list) or len(listings) == 0:
            return 0

        count = 0
        for item in listings[:30]:
            try:
                if not isinstance(item, dict):
                    continue

                title = item.get('job_title', '') or ''
                if not title or len(str(title).strip()) < 4:
                    continue

                company = item.get('employer_name', '') or ''
                city = item.get('job_city', '') or ''
                state = item.get('job_state', '') or ''
                country = item.get('job_country', '') or ''

                # Build location string
                location_parts = [p for p in [city, state, 'India' if country and (country.upper() == 'IN' or 'india' in country.lower()) else country] if p]
                location = ', '.join(location_parts) if location_parts else 'India'

                # Build salary string
                min_sal = item.get('job_min_salary')
                max_sal = item.get('job_max_salary')
                salary = ''
                if min_sal or max_sal:
                    if min_sal and max_sal:
                        salary = f'{int(min_sal):,} - {int(max_sal):,} INR'
                    elif min_sal:
                        salary = f'From {int(min_sal):,} INR'
                    elif max_sal:
                        salary = f'Up to {int(max_sal):,} INR'

                description = item.get('job_description', '') or ''
                url = item.get('job_apply_link', '') or ''
                posted = item.get('job_posted_at_datetime_utc', '') or ''
                if posted and len(posted) > 10:
                    posted = posted[:10]  # Just the date part

                # Skills
                skills_raw = item.get('job_required_skills', '')
                if isinstance(skills_raw, list):
                    skills = ', '.join(str(s) for s in skills_raw if s)
                else:
                    skills = str(skills_raw) if skills_raw else ''

                # Infer skills from title if none provided
                title_lower = str(title).lower()
                if not skills:
                    known_skills = ['python', 'java', 'javascript', 'react', 'angular', 'vue',
                                    'aws', 'docker', 'kubernetes', 'node', 'django', 'flask',
                                    'sql', 'mongodb', 'typescript', 'go', 'rust', 'c++', 'ruby']
                    matched = [s for s in known_skills if s in title_lower]
                    if matched:
                        skills = ', '.join(matched)

                # Job type
                emp_type = item.get('job_employment_type', '') or ''
                job_type_map = {
                    'FULLTIME': 'Full-time',
                    'PARTTIME': 'Part-time',
                    'CONTRACTOR': 'Contract',
                    'INTERN': 'Internship',
                    'FREELANCE': 'Freelance',
                    'TEMPORARY': 'Contract',
                }
                job_type = job_type_map.get(emp_type.upper(), 'Full-time')
                if job_type == 'Full-time':
                    if 'intern' in title_lower:
                        job_type = 'Internship'
                    elif 'part-time' in title_lower or 'part time' in title_lower:
                        job_type = 'Part-time'
                    elif 'contract' in title_lower:
                        job_type = 'Contract'

                job_data = {
                    'title': str(title),
                    'company': str(company) if company else 'Unknown',
                    'location': location,
                    'salary': salary,
                    'skills': skills,
                    'url': url,
                    'source': self.source_name,
                    'job_type': job_type,
                    'posted_date': posted if posted else 'Recently',
                    'description': str(description)[:2000] if description else '',
                }
                jobs.append(self.sanitize_job_data(job_data))
                count += 1
            except Exception as e:
                logger.debug(f'Skip JSearch listing: {e}')
                continue

        return count


# ─────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────
SCRAPER_REGISTRY = {
    'internshala': InternshalaScraper,
    'rapidapi': RapidAPIJobsScraper,
    'jsearch': JSearchScraper,
    'demo': DemoScraper,
}


def get_all_scrapers():
    """Return instances of registered scrapers, excluding demo unless all others fail."""
    return [ScraperClass() for name, ScraperClass in SCRAPER_REGISTRY.items() if name != 'demo']


def get_fallback_scraper():
    """Return demo scraper instance for fallback use."""
    return DemoScraper()
