"""Scraper base class and implementations for job sources.
Includes bleach sanitization on all scraped text fields.
"""
from bs4 import BeautifulSoup
import requests
import cloudscraper
import re
import time
import random
import bleach
from datetime import datetime, timezone
from urllib.parse import urljoin, quote
from utils.logger import get_logger, log_event

logger = get_logger('scrapers')

# Allowed HTML tags for scraped job descriptions
BLEACH_ALLOWED_TAGS = ['p', 'br', 'b', 'i', 'u', 'strong', 'em', 'ul', 'ol', 'li', 'span', 'div']

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
    """Sanitize scraped text: strip dangerous HTML, limit length."""
    if not text:
        return ''
    # Remove script and style elements
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Strip remaining tags or clean with bleach
    text = bleach.clean(text, tags=BLEACH_ALLOWED_TAGS, strip=True)
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
# 2. LinkedIn Public HTML Scraper
# ─────────────────────────────────────────────
class LinkedInScraper(BaseScraper):
    """LinkedIn jobs via public search pages."""

    source_name = 'LinkedIn'
    base_url = 'https://www.linkedin.com'

    SEARCH_QUERIES = [
        ('python developer', 'India'),
        ('react developer', 'India'),
        ('java developer', 'India'),
        ('data scientist', 'India'),
        ('full stack developer', 'India'),
        ('devops engineer', 'India'),
        ('frontend developer', 'India'),
        ('backend developer', 'India'),
        ('machine learning engineer', 'India'),
        ('software engineer', 'Bangalore'),
    ]

    def scrape(self):
        jobs = []
        session = get_session()
        for query, location in self.SEARCH_QUERIES:
            try:
                params = {'keywords': query, 'location': location}
                url = f'{self.base_url}/jobs/search/'
                soup = self.fetch_page(url, params=params, session=session)
                if not soup:
                    try:
                        time.sleep(random.uniform(2, 4))
                        resp = session.get(url, params=params, timeout=30, allow_redirects=True)
                        if resp.status_code == 200 and len(resp.text) > 50000:
                            soup = BeautifulSoup(resp.text, 'html.parser')
                        else:
                            logger.warning(f'LinkedIn: Bad response for {query} (status={resp.status_code}, len={len(resp.text)})')
                            continue
                    except Exception as e:
                        logger.warning(f'LinkedIn retry failed for {query}: {e}')
                        continue

                found = self._parse_listings(soup, jobs)
                if found > 0:
                    logger.info(f'LinkedIn: {found} jobs for "{query}" in {location}')
                if len(jobs) >= 80:
                    break
            except Exception as e:
                logger.error(f'LinkedIn error for {query}: {e}')
                continue

        return self.deduplicate(jobs, limit=80)

    def _parse_listings(self, soup, jobs):
        cards = soup.select('li.job-search-card__list-item')
        if not cards:
            cards = soup.select('div.base-search-card')
        if not cards:
            cards = soup.select('[class*="job-search-card"]')

        count = 0
        for card in cards[:25]:
            try:
                title_el = card.select_one('h3.base-search-card__title, h3')
                if not title_el:
                    sr = card.select_one('a span.sr-only')
                    if sr:
                        title = self.clean_text(sr.get_text())
                    else:
                        continue
                else:
                    title = self.clean_text(title_el.get_text())

                if not title or len(title) < 5 or len(title) > 200:
                    continue

                anchor = card.select_one('a.base-card__full-link')
                if not anchor:
                    anchor = card.select_one('a')
                href = anchor.get('href', '') if anchor else ''
                if not href:
                    continue
                href = re.sub(r'[?&].*$', '', href) if '/jobs/view/' in href else href
                if not href.startswith('http'):
                    href = urljoin(self.base_url, href)

                company_el = card.select_one('h4.base-search-card__subtitle a, h4.base-search-card__subtitle')
                company = self.clean_text(company_el.get_text()) if company_el else ''

                loc_el = card.select_one('span.job-search-card__location')
                location = self.clean_text(loc_el.get_text()) if loc_el else 'India'

                time_el = card.select_one('time.job-search-card__listdate')
                posted = ''
                if time_el:
                    posted = time_el.get('datetime', '') or self.clean_text(time_el.get_text())
                    if posted and len(posted) > 20:
                        posted = posted[:20]

                job_type = 'Full-time'
                title_lower = title.lower()
                if 'intern' in title_lower:
                    job_type = 'Internship'
                elif 'part-time' in title_lower or 'part time' in title_lower:
                    job_type = 'Part-time'
                elif 'contract' in title_lower:
                    job_type = 'Contract'

                job_data = {
                    'title': title,
                    'company': company,
                    'location': location if location else 'India',
                    'salary': '',
                    'skills': '',
                    'url': href,
                    'source': self.source_name,
                    'job_type': job_type,
                    'posted_date': posted if posted else 'Recently',
                    'description': '',
                }
                jobs.append(self.sanitize_job_data(job_data))
                count += 1
            except Exception as e:
                logger.debug(f'Skip LinkedIn listing: {e}')
                continue
        return count


# ─────────────────────────────────────────────
# 3. Indeed Scraper
# ─────────────────────────────────────────────
class IndeedScraper(BaseScraper):
    """Scraper for Indeed — global job search platform.
    Uses India-specific portal (in.indeed.com).
    Includes anti-block measures: homepage cookie warmup, rotating UAs, modern headers.
    """

    source_name = 'Indeed'
    base_url = 'https://in.indeed.com'

    SEARCH_QUERIES = [
        'python developer',
        'react developer',
        'java developer',
        'data scientist',
        'full stack developer',
        'devops engineer',
        'frontend developer',
        'backend developer',
        'machine learning engineer',
        'software engineer',
    ]

    # Modern browser headers to avoid 403
    CHROME_HEADERS = [
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-IN,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Ch-Ua': '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Ch-Ua': '"Google Chrome";v="126", "Chromium";v="126", "Not.A/Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
        },
    ]

    def _warmup_session(self, session):
        """Visit Indeed homepage first to get cookies before making search requests."""
        try:
            session.headers.update(random.choice(self.CHROME_HEADERS))
            resp = session.get('https://in.indeed.com/', timeout=20, allow_redirects=True)
            if resp.status_code == 200:
                logger.info('Indeed: Homepage warmup successful (cookies acquired)')
                return True
            else:
                logger.warning(f'Indeed: Homepage warmup returned {resp.status_code}')
                return False
        except Exception as e:
            logger.warning(f'Indeed: Homepage warmup failed: {e}')
            return False

    def scrape(self):
        jobs = []
        session = get_session()

        # Warm up session with homepage visit to get cookies
        self._warmup_session(session)
        time.sleep(random.uniform(2, 4))

        for query in self.SEARCH_QUERIES:
            try:
                # Rotate headers per-query
                session.headers.update(random.choice(self.CHROME_HEADERS))

                params = {
                    'q': query,
                    'l': 'India',
                    'sort': 'date',
                }
                url = f'{self.base_url}/jobs'

                # Longer random delay per query
                time.sleep(random.uniform(3.0, 6.0))

                try:
                    response = session.get(url, params=params, timeout=30, allow_redirects=True)
                    if response.status_code == 403 or response.status_code == 429:
                        logger.warning(f'Indeed 403/429 on "{query}" — waiting longer and retrying...')
                        time.sleep(random.uniform(8, 12))
                        session.headers.update(random.choice(self.CHROME_HEADERS))
                        response = session.get(url, params=params, timeout=30, allow_redirects=True)

                    response.raise_for_status()

                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' not in content_type and 'text/xml' not in content_type:
                        logger.warning(f'Indeed: Non-HTML response for "{query}": {content_type}')
                        continue

                    text = response.text
                    text_lower = text.lower()
                    block_signals = [
                        'captcha', 'robot check', 'access denied', 'cloudflare',
                        'just a moment', 'blocked', 'unusual traffic',
                        'verify you are human', 'checking your browser',
                    ]
                    blocked = any(s in text_lower for s in block_signals) and len(text) < 15000

                    if blocked:
                        logger.warning(f'Indeed: Anti-bot triggered for "{query}" — skipping')
                        continue

                    soup = BeautifulSoup(text, 'html.parser')
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code in (403, 429):
                        logger.warning(f'Indeed: Still blocked ({e.response.status_code}) on "{query}" after retry')
                        continue
                    else:
                        logger.warning(f'Indeed: HTTP {e.response.status_code} on "{query}"')
                        continue

                found = self._parse_listings(soup, jobs)
                if found > 0:
                    logger.info(f'Indeed: {found} jobs for "{query}"')
                if len(jobs) >= 60:
                    break
            except Exception as e:
                logger.error(f'Indeed error for {query}: {e}')
                continue

        return self.deduplicate(jobs, limit=60)

    def _parse_listings(self, soup, jobs):
        """Parse Indeed job cards from search results.
        Card structure:
          <div class="job_seen_beacon"> or <div class="job-card-container">
            <h2><a class="jobTitle" ...>Job Title</a></h2>
            <span class="companyName">Company</span>
            <div class="companyLocation">Location</div>
            <div class="salary-snippet">Salary</div>
            <div class="job-snippet">Description snippet</div>
        """
        cards = soup.select('div.job_seen_beacon, div.job-card-container, div[id^="job_"]')
        if not cards:
            cards = soup.select('[class*="job-card"], [class*="result"]')

        count = 0
        for card in cards[:30]:
            try:
                # Title
                title_el = card.select_one('h2 a.jobTitle, a.jobTitle, h2 a[class*="title"], a[class*="title"]')
                if not title_el:
                    title_el = card.select_one('h2 a')
                if not title_el:
                    title_el = card.select_one('a[data-testid="job-link"]')
                if not title_el:
                    continue

                title = self.clean_text(title_el.get_text())
                href = title_el.get('href', '')
                if href and not href.startswith('http'):
                    href = self.base_url + href
                if not title or len(title) < 4:
                    continue

                # Company
                company_el = card.select_one('span.companyName, [class*="company"] a, [class*="companyName"]')
                company = self.clean_text(company_el.get_text()) if company_el else ''
                if not company:
                    company_el = card.select_one('[data-testid*="company"]')
                    company = self.clean_text(company_el.get_text()) if company_el else ''

                # Location
                loc_el = card.select_one('div.companyLocation, [class*="location"]')
                location = self.clean_text(loc_el.get_text()) if loc_el else 'India'

                # Salary
                salary_el = card.select_one('div.salary-snippet span, [class*="salary"], [data-testid*="salary"]')
                salary = self.clean_text(salary_el.get_text()) if salary_el else ''

                # Skills — Indeed doesn't list skills directly, infer from title
                skills = ''
                known_skills = ['python', 'java', 'javascript', 'react', 'angular', 'vue', 'aws',
                                'docker', 'kubernetes', 'node', 'django', 'flask', 'sql', 'mongodb']
                title_lower = title.lower()
                matched = [s for s in known_skills if s in title_lower]
                if matched:
                    skills = ', '.join(matched)

                # Posted date
                date_el = card.select_one('span.date, [class*="date"], span[class*="posted"]')
                posted = self.clean_text(date_el.get_text()) if date_el else 'Recently'

                # Job type
                job_type = 'Full-time'
                title_lower = title.lower()
                if 'intern' in title_lower:
                    job_type = 'Internship'
                elif 'part-time' in title_lower or 'part time' in title_lower:
                    job_type = 'Part-time'
                elif 'contract' in title_lower:
                    job_type = 'Contract'

                # Description snippet
                desc_el = card.select_one('div.job-snippet, [class*="snippet"], [data-testid*="snippet"]')
                description = self.clean_text(desc_el.get_text()) if desc_el else ''

                job_data = {
                    'title': title,
                    'company': company,
                    'location': location if location else 'India',
                    'salary': salary,
                    'skills': skills,
                    'url': href,
                    'source': self.source_name,
                    'job_type': job_type,
                    'posted_date': posted,
                    'description': description,
                }
                jobs.append(self.sanitize_job_data(job_data))
                count += 1
            except Exception as e:
                logger.debug(f'Skip Indeed listing: {e}')
                continue
        return count


# ─────────────────────────────────────────────
# 4. Naukri Scraper
# ─────────────────────────────────────────────
class NaukriScraper(BaseScraper):
    """Scraper for Naukri.com — India's largest job portal.
    Uses aggressive DOM-flexible selectors to handle frequent site changes.
    """

    source_name = 'Naukri'
    base_url = 'https://www.naukri.com'

    SEARCH_QUERIES = [
        'python developer',
        'react developer',
        'java developer',
        'data scientist',
        'full stack developer',
        'devops engineer',
        'frontend developer',
        'backend developer',
        'machine learning engineer',
        'software engineer',
    ]

    NAUKRI_HEADERS = [
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-IN,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Upgrade-Insecure-Requests': '1',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Upgrade-Insecure-Requests': '1',
        },
    ]

    def scrape(self):
        jobs = []
        session = get_session()

        for query in self.SEARCH_QUERIES:
            try:
                session.headers.update(random.choice(self.NAUKRI_HEADERS))
                search_path = '-'.join(query.lower().split())

                # Try multiple URL patterns
                url_patterns = [
                    f'{self.base_url}/{search_path}-jobs-in-india',
                    f'{self.base_url}/jobs/{search_path}-jobs',
                    f'{self.base_url}/{search_path}-jobs',
                    f'{self.base_url}/job-search?q={query.replace(" ", "+")}',
                ]

                soup = None
                for url in url_patterns:
                    time.sleep(random.uniform(2.0, 4.0))
                    try:
                        resp = session.get(url, timeout=30, allow_redirects=True)
                        if resp.status_code == 200 and len(resp.text) > 20000:
                            soup = BeautifulSoup(resp.text, 'html.parser')
                            # Quick sanity check — look for job-like content
                            has_cards = bool(
                                soup.select('article, [class*="job"], [class*="card"], [class*="list"] li, a[href*="job-detail"], a[href*="jobs/"]')
                            )
                            if has_cards:
                                break
                            else:
                                soup = None
                        else:
                            logger.debug(f'Naukri: {resp.status_code} on {url.split(".com")[1][:40]}')
                    except Exception as e:
                        logger.debug(f'Naukri: Request failed on {url.split(".com")[1][:40]}: {e}')
                        continue

                if not soup:
                    logger.debug(f'Naukri: No valid page for "{query}"')
                    continue

                found = self._parse_listings(soup, jobs)
                if found > 0:
                    logger.info(f'Naukri: {found} jobs for "{query}"')
                if len(jobs) >= 60:
                    break
            except Exception as e:
                logger.error(f'Naukri error for {query}: {e}')
                continue

        return self.deduplicate(jobs, limit=60)

    def _parse_listings(self, soup, jobs):
        """Parse Naukri job cards from search results.
        Extremely flexible selector strategy to handle frequent DOM changes.
        Falls back through multiple known and generic card patterns.
        """
        # Try multiple card selectors in order of specificity
        card_selectors = [
            'article.jobTuple',
            'div.job-card',
            'div[class*="jobTuple"]',
            'section.job',
            'div[class*="job-card"]',
            'div[class*="list"] li',
            'div[class*="result"]',
            'div[class*="card"]',
            'li[class*="job"]',
            'article',
        ]

        cards = None
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards and len(cards) >= 2:  # At least 2 cards found
                break

        if not cards:
            # Ultimate fallback: any element with job-related text content
            all_anchors = soup.select('a[href*="job-detail"], a[href*="jobs/"], a[href*="jobsearch"]')
            if all_anchors:
                # Group by parent that likely represents a card
                parents = {}
                for a in all_anchors:
                    parent = a.find_parent(['div', 'article', 'li', 'section'])
                    if parent and parent not in parents:
                        parents[parent] = a
                cards = list(parents.keys()) if parents else all_anchors[:10]

        if not cards:
            return 0

        count = 0
        for card in cards[:30]:
            try:
                # Title — try many selectors
                title_el = (
                    card.select_one('a.title[href*="jobs"], a[class*="title"], a[class*="job-title"]')
                    or card.select_one('a[href*="job-detail"], a[href*="jobs/"]')
                    or card.select_one('h2 a, h3 a, h4 a, h2, h3, h4')
                )
                if not title_el:
                    continue

                title = self.clean_text(title_el.get_text())
                href = title_el.get('href', '') if hasattr(title_el, 'get') else ''
                if href and not href.startswith('http'):
                    href = self.base_url + href
                title_lower = title.lower()
                if not title or len(title) < 3:
                    continue

                # Company
                company_el = (
                    card.select_one('a.subTitle, a[class*="company"], a[class*="subtitle"]')
                    or card.select_one('span[class*="company"]')
                    or card.select_one('a[class*="comp"]')
                    or card.select_one('[class*="company"]')
                    or card.select_one('[class*="employer"]')
                )
                company = self.clean_text(company_el.get_text()) if company_el else ''

                # Location
                loc_el = (
                    card.select_one('span.location, span[class*="loc"], li[class*="loc"] span')
                    or card.select_one('[class*="location"]')
                    or card.select_one('[class*="place"]')
                    or card.select_one('span[class*="city"]')
                )
                location = self.clean_text(loc_el.get_text()) if loc_el else 'India'
                if not location or location.lower() in ('location', 'india', ''):
                    location = 'India'

                # Salary
                salary_el = (
                    card.select_one('span.salary, span[class*="salary"], li[class*="salary"] span')
                    or card.select_one('[class*="salary"]')
                    or card.select_one('[class*="pay"]')
                    or card.select_one('[class*="stipend"]')
                )
                salary = self.clean_text(salary_el.get_text()) if salary_el else ''

                # Experience
                exp_el = (
                    card.select_one('span.experience, span[class*="exp"]')
                    or card.select_one('[class*="experience"]')
                    or card.select_one('[class*="exp"]')
                )
                experience = self.clean_text(exp_el.get_text()) if exp_el else ''

                # Skills
                skill_els = (
                    card.select('ul.tags li a, ul[class*="skill"] li, span[class*="skill"]')
                    or card.select('[class*="skill"]')
                    or card.select('[class*="tag"]')
                )
                if skill_els:
                    skills = ', '.join([self.clean_text(s.get_text()) for s in skill_els])
                else:
                    # Infer from title
                    known_skills = ['python', 'java', 'javascript', 'react', 'angular', 'vue',
                                    'aws', 'docker', 'kubernetes', 'node', 'django', 'flask',
                                    'sql', 'mongodb', 'typescript', 'go', 'rust', 'c++', 'ruby']
                    matched = [s for s in known_skills if s in title_lower]
                    skills = ', '.join(matched) if matched else ''

                # Description
                desc_el = (
                    card.select_one('div.job-description, div[class*="desc"], span[class*="desc"]')
                    or card.select_one('[class*="description"]')
                    or card.select_one('[class*="snippet"]')
                )
                description = self.clean_text(desc_el.get_text()) if desc_el else ''

                # Job type
                job_type = 'Full-time'
                if 'intern' in title_lower:
                    job_type = 'Internship'
                elif 'part-time' in title_lower or 'part time' in title_lower:
                    job_type = 'Part-time'
                elif 'contract' in title_lower:
                    job_type = 'Contract'
                elif 'freelance' in title_lower:
                    job_type = 'Freelance'

                desc_parts = [description]
                if experience:
                    desc_parts.append(f'Experience: {experience}')
                description = ' | '.join(filter(None, desc_parts))

                job_data = {
                    'title': title,
                    'company': company if company else 'Unknown',
                    'location': location,
                    'salary': salary,
                    'skills': skills,
                    'url': href,
                    'source': self.source_name,
                    'job_type': job_type,
                    'posted_date': 'Recently',
                    'description': description,
                }
                jobs.append(self.sanitize_job_data(job_data))
                count += 1
            except Exception as e:
                logger.debug(f'Skip Naukri listing: {e}')
                continue
        return count


# ─────────────────────────────────────────────
# 5. Glassdoor Scraper
# ─────────────────────────────────────────────
class GlassdoorScraper(BaseScraper):
    """Scraper for Glassdoor — company reviews and job listings.
    Includes anti-block measures: homepage cookie warmup, rotating UAs.
    """

    source_name = 'Glassdoor'
    base_url = 'https://www.glassdoor.co.in'

    SEARCH_QUERIES = [
        'python developer',
        'react developer',
        'java developer',
        'data scientist',
        'full stack developer',
        'devops engineer',
        'frontend developer',
        'backend developer',
        'machine learning engineer',
        'software engineer',
    ]

    GD_HEADERS = [
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-IN,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Ch-Ua': '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Referer': 'https://www.google.com/',
            'Upgrade-Insecure-Requests': '1',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Ch-Ua': '"Google Chrome";v="126", "Chromium";v="126", "Not.A/Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Referer': 'https://www.google.com/',
            'Upgrade-Insecure-Requests': '1',
        },
    ]

    def _warmup_session(self, session):
        """Visit Glassdoor homepage to acquire cookies before making search requests."""
        for domain in [self.base_url, 'https://www.glassdoor.com']:
            try:
                headers = random.choice(self.GD_HEADERS)
                session.headers.update(headers)
                resp = session.get(f'{domain}/', timeout=20, allow_redirects=True)
                if resp.status_code == 200:
                    logger.info(f'Glassdoor: Homepage warmup OK ({domain})')
                    return True
                logger.debug(f'Glassdoor: Homepage warmup got {resp.status_code} on {domain}')
            except Exception as e:
                logger.debug(f'Glassdoor: Homepage warmup failed on {domain}: {e}')
                continue
        return False

    def scrape(self):
        jobs = []
        session = get_session()

        # Warm up with homepage visit
        self._warmup_session(session)
        time.sleep(random.uniform(3, 5))

        # Try multiple URL patterns across multiple Glassdoor domains
        search_urls = [
            f'{self.base_url}/Job/jobs.htm',
            'https://www.glassdoor.com/Job/jobs.htm',
        ]

        for query in self.SEARCH_QUERIES:
            try:
                headers = random.choice(self.GD_HEADERS)
                session.headers.update(headers)

                params = {
                    'sc.keyword': query,
                    'locT': 'C',
                    'locId': '1137058',  # India
                    'jobType': 'all',
                }

                soup = None
                for url in search_urls:
                    time.sleep(random.uniform(3.0, 6.0))
                    try:
                        response = session.get(url, params=params, timeout=30, allow_redirects=True)
                        if response.status_code == 403 or response.status_code == 429:
                            logger.warning(f'Glassdoor 403/429 on "{query}" — waiting and retrying...')
                            time.sleep(random.uniform(8, 12))
                            session.headers.update(random.choice(self.GD_HEADERS))
                            response = session.get(url, params=params, timeout=30, allow_redirects=True)

                        response.raise_for_status()

                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' not in content_type:
                            logger.debug(f'Glassdoor: Non-HTML from {url.split(".com")[0][-8:]}{url.split(".com")[1][:20]}: {content_type}')
                            continue

                        text = response.text
                        text_lower = text.lower()
                        block_signals = [
                            'captcha', 'robot check', 'access denied', 'cloudflare',
                            'just a moment', 'blocked', 'unusual traffic',
                            'verify you are human',
                        ]
                        if any(s in text_lower for s in block_signals) and len(text) < 15000:
                            logger.warning(f'Glassdoor: Anti-bot triggered on "{query}" — trying next domain')
                            continue

                        soup = BeautifulSoup(text, 'html.parser')
                        break  # Got valid HTML
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code in (403, 429):
                            logger.warning(f'Glassdoor: Blocked ({e.response.status_code}) on {url.split(".com")[1][:20]} — trying next')
                            continue
                        logger.warning(f'Glassdoor: HTTP {e.response.status_code} on {url.split(".com")[1][:20]}')
                    except Exception as e:
                        logger.debug(f'Glassdoor: Request error on {url.split(".com")[1][:20]}: {e}')
                        continue

                if not soup:
                    continue

                found = self._parse_listings(soup, jobs)
                if found > 0:
                    logger.info(f'Glassdoor: {found} jobs for "{query}"')
                if len(jobs) >= 60:
                    break
            except Exception as e:
                logger.error(f'Glassdoor error for {query}: {e}')
                continue

        return self.deduplicate(jobs, limit=60)

    def _parse_listings(self, soup, jobs):
        """Parse Glassdoor job cards from search results.
        Card structure:
          <li class="react-job-listing"> or <div class="jobListing">
            <a class="jobLink" ...>Job Title</a>
            <span class="job-employer">Company</span>
            <span class="job-location">Location</span>
            <span class="job-salary">Salary</span>
        """
        cards = soup.select('li.react-job-listing, div.jobListing, div[class*="job-card"], div[class*="listing"]')
        if not cards:
            cards = soup.select('[class*="job"]')

        count = 0
        for card in cards[:30]:
            try:
                # Title
                title_el = card.select_one('a.jobLink, a[class*="job-title"], a[data-test*="job-link"], a[class*="title"]')
                if not title_el:
                    title_el = card.select_one('a[href*="job-listing"]')
                if not title_el:
                    continue

                title = self.clean_text(title_el.get_text())
                href = title_el.get('href', '')
                if href and not href.startswith('http'):
                    href = self.base_url + href
                if not title or len(title) < 4:
                    continue

                # Company
                company_el = card.select_one('span.job-employer, span[class*="employer"], span[class*="company"]')
                company = self.clean_text(company_el.get_text()) if company_el else ''
                if not company:
                    company_el = card.select_one('[class*="employer"] a, [data-test*="employer"]')
                    company = self.clean_text(company_el.get_text()) if company_el else ''

                # Location
                loc_el = card.select_one('span.job-location, span[class*="location"], [data-test*="location"]')
                location = self.clean_text(loc_el.get_text()) if loc_el else 'India'
                if not location or location.lower() in ('india', 'multiple locations'):
                    location = 'India'

                # Salary
                salary_el = card.select_one('span.job-salary, span[class*="salary"], [data-test*="salary"]')
                salary = self.clean_text(salary_el.get_text()) if salary_el else ''

                # Skills — Glassdoor doesn't list skills directly, infer from title
                skills = ''
                known_skills = ['python', 'java', 'javascript', 'react', 'angular', 'vue', 'aws',
                                'docker', 'kubernetes', 'node', 'django', 'flask', 'sql', 'mongodb']
                title_lower = title.lower()
                matched = [s for s in known_skills if s in title_lower]
                if matched:
                    skills = ', '.join(matched)

                # Job type
                job_type = 'Full-time'
                title_lower = title.lower()
                if 'intern' in title_lower:
                    job_type = 'Internship'
                elif 'part-time' in title_lower or 'part time' in title_lower:
                    job_type = 'Part-time'
                elif 'contract' in title_lower:
                    job_type = 'Contract'

                # Posted date
                date_el = card.select_one('span.job-age, span[class*="age"], span[class*="date"]')
                posted = self.clean_text(date_el.get_text()) if date_el else 'Recently'

                job_data = {
                    'title': title,
                    'company': company,
                    'location': location if location else 'India',
                    'salary': salary,
                    'skills': skills,
                    'url': href,
                    'source': self.source_name,
                    'job_type': job_type,
                    'posted_date': posted,
                    'description': '',
                }
                jobs.append(self.sanitize_job_data(job_data))
                count += 1
            except Exception as e:
                logger.debug(f'Skip Glassdoor listing: {e}')
                continue
        return count


# ─────────────────────────────────────────────
# Demo Fallback (only used if all real scrapers return 0)
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
# 6. RapidAPI Indian Jobs Scraper
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
# Registry
# ─────────────────────────────────────────────
SCRAPER_REGISTRY = {
    'internshala': InternshalaScraper,
    'linkedin': LinkedInScraper,
    'indeed': IndeedScraper,
    'naukri': NaukriScraper,
    'glassdoor': GlassdoorScraper,
    'rapidapi': RapidAPIJobsScraper,
    'demo': DemoScraper,
}


def get_all_scrapers():
    """Return instances of registered scrapers, excluding demo unless all others fail."""
    return [ScraperClass() for name, ScraperClass in SCRAPER_REGISTRY.items() if name != 'demo']


def get_fallback_scraper():
    """Return demo scraper instance for fallback use."""
    return DemoScraper()
