<div align="center">

# 🚀 Smart Job Alert

**A production-hardened job scraping & personalized email alert system built with Flask**

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=flat&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 110+ passing](https://img.shields.io/badge/Tests-110%2B%20passing-brightgreen)](https://github.com/SouravGiri-007/job-alert)
[![Security: CSRF + Rate-Limited + bcrypt](https://img.shields.io/badge/Security-CSRF%20%7C%20Rate--Limited%20%7C%20bcrypt-success)](https://github.com/SouravGiri-007/job-alert)

Collect live jobs from **6+ sources** (Internshala, LinkedIn, RapidAPI, Indeed, Naukri, Glassdoor + demo fallback), match them to subscriber preferences with an intelligent scoring system, and deliver **personalized email alerts** — automatically, on a schedule.

</div>

---

## ✨ Features

### 🔍 Multi-Source Job Scraping (5 Platforms)
- **Internshala** — India's largest internship platform, scrapes internships & jobs
- **LinkedIn** — extracts job cards from public search pages (10 queries across India)
- **Indeed** — global job search platform via India-specific portal (`in.indeed.com`)
- **Naukri** — India's largest job portal, scrapes search result pages
- **Glassdoor** — company reviews & job listings via India-specific portal
- **Demo Fallback** — sample data only used when all 5 real scrapers return nothing
- Rate-limited, anti-bot-aware fetching with rotating User-Agents (4 different UA strings)
- 🛡️ **XSS-safe** — all scraped data sanitized via `bleach` before storage

### 🧠 Smart Matching Engine
Jobs are scored against each subscriber's preferences using a weighted algorithm:
| Preference | Weight | Behavior |
|---|---|---|
| **Skills** | 4x | Hard requirement — zero overlap = rejected |
| **Role** | 3x | Fuzzy role matching with alias detection (e.g. "developer" ↔ "engineer") |
| **Location** | 2x | Supports city aliases (Bangalore ↔ Bengaluru) & remote matching |
| **Job Type** | 1x | Full-time / Internship / Part-time / Contract |
- Minimum score threshold ensures relevance
- **SQL pre-filtering** — location, job type, and skills filtered at the DB level before in-memory scoring
- Subscribers with no preferences receive the latest jobs without filtering

### 📧 Email Alert System
- **Resend API** — sends emails via HTTPS API (no SMTP needed, works everywhere including Render)
- **Threaded parallel delivery** — configurable worker count (`EMAIL_WORKERS`, default: 4) for concurrent email sending. Falls back to sequential when only 1 worker is configured.
- Beautiful **HTML email templates** with plain-text fallback
- Supports **email verification** before sending alerts
- One-click **unsubscribe** links in every email
- Automatic **retry of failed emails**

### 📊 Admin Dashboard
- Real-time **stats dashboard** with charts (subscriber growth, email delivery, job sources)
- Manage **subscribers** — view, search, filter, export to CSV, delete
- Browse **jobs** — full listing with search, source filtering, detail view
- **Scraper run history** — success/fail tracking per source
- **Email history** — sent vs. failed delivery records
- **App logs viewer** — last 200 lines in-browser
- Manual trigger buttons for **scraping** & **sending alerts**

### ⏰ Automated Scheduling
- Daily job scraping at configurable time (default: 8:00 AM)
- Automatic email dispatch after scraping
- Secondary job to retry failed emails (10:00 AM)
- Built on **APScheduler** with **database-level distributed locking** for multi-worker safety

### 🔐 Security
- ✅ **CSRF Protection** — all admin POST endpoints protected via Flask-WTF
- ✅ **Rate-Limited Login** — admin login throttled (10 req/min, 30 req/hr)
- ✅ **bcrypt Password Hashing** — admin passwords stored with bcrypt (not plaintext)
- ✅ **Input Validation** — email regex validation, field length limits, HTML tag rejection on subscribe
- ✅ **XSS Sanitization** — all scraped job data cleaned with `bleach` before storage
- ✅ **Distributed Locking** — scheduler uses database-level locks to prevent duplicate execution across workers
- ✅ **Log Rotation** — rotating file handler with configurable max size and backup count (default: 10 MB, 5 backups)
- ✅ **Security Warnings** — startup warnings for default secret key, debug mode, and missing SMTP config

---

## 🏗️ Architecture

```
job-alert/
├── app.py                  # App factory with security checks
├── config.py               # Configuration (env-vars, SMTP, scheduler, logging, CSRF)
├── extensions.py           # SQLAlchemy, Flask-Login, CSRFProtect, Flask-Limiter
├── requirements.txt        # Python dependencies
├── .gitignore              # Env, db, logs, cache excluded
├── models/                 # SQLAlchemy ORM models
│   ├── admin.py            # AdminUser with bcrypt password hashing ★ NEW
│   ├── job.py              # Job listing model (indexed: scraped_at, source, title+company)
│   ├── subscriber.py       # Subscriber model (indexed: is_verified, is_active)
│   ├── email_history.py    # Email delivery log (indexed: sent_at, status, composite index)
│   └── scraper_history.py  # Scraper run log (indexed: source, started_at)
├── routes/                 # Flask blueprints
│   ├── main.py             # Public routes (landing, subscribe, verify, unsubscribe)
│   ├── api.py              # JSON API endpoints (uses shared stats service)
│   └── admin.py            # Admin routes (rate-limited login, dashboard, CRUD)
├── scrapers/
│   └── scrapers.py         # BaseScraper + 5 scrapers + Demo fallback (bleach-sanitized)
├── services/               # Business logic layer
│   ├── email_service.py    # Resend API email sending (parallel delivery)
│   ├── matching_service.py # Job-subscriber matching algorithm (SQL pre-filtered)
│   ├── stats_service.py    # Shared dashboard stats
│   └── scheduler_lock.py   # Distributed scheduler lock model
├── tests/                  # 110+ tests across 11 files
│   ├── conftest.py         # App factory, test config, fixtures, sample data
│   ├── test_matching.py    # Matching engine (10 tests)
│   ├── test_models.py      # ORM models (9 tests)
│   ├── test_main_routes.py # Public routes (10 tests)
│   ├── test_admin_routes.py# Admin routes (11 tests)
│   ├── test_api_routes.py  # JSON API endpoints (5 tests)
│   ├── test_stats_service.py # Stats service (5 tests)
│   ├── test_scrapers.py    # Scrapers & sanitization (20+ tests)
│   ├── test_security.py    # Security features (7 tests)
│   ├── test_email_service.py # Email templates (4 tests)
│   └── test_scraper_*.py   # HTML mock scraper tests
├── scheduler/
│   └── scheduler.py        # APScheduler setup (distributed-lock safe)
├── utils/
│   ├── helpers.py          # Token generation, flash helpers, formatting
│   └── logger.py           # RotatingFileHandler-based logging
├── templates/              # Jinja2 templates (CSRF tokens in all forms)
│   ├── base.html           # Base layout
│   ├── index.html          # Landing page
│   ├── jobs.html           # Public job browser
│   ├── admin/              # Admin panel templates
│   └── emails/             # Email templates (HTML & TXT)
└── static/
    ├── css/style.css       # Application styles
    └── js/main.js          # Dark mode toggle, toasts, form validation
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- (Optional) An SMTP account for email delivery

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/SouravGiri-007/job-alert.git
cd job-alert

# 2. Create a virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the application
python app.py
```

Visit **http://localhost:5000** — you'll see the landing page with the subscription form and a sample of scraped jobs.

### Admin Panel

Navigate to **http://localhost:5000/admin** and log in:

| Field | Default Value |
|---|---|
| Username | `admin` |
| Password | `admin123` |

> ⚠️ **Change these immediately in production** by setting the `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables. The password is **hashed with bcrypt** on first run, so the plaintext env var is only used for initial seed.

---

## ⚙️ Configuration

All configuration is managed through **environment variables** (loaded from a `.env` file if present).

### Core
| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-secret-key-...` | Flask secret key — **must change in production** |
| `JOB_ALERT_DATABASE_URL` | `sqlite:///database.db` | Database URL |
| `APP_URL` | `http://localhost:5000` | Public URL (used in email links) |
| `ADMIN_USERNAME` | `admin` | Admin panel username |
| `ADMIN_PASSWORD` | `admin123` | Admin panel password (hashed on seed) |

### Resend (Email)
| Variable | Default | Description |
|---|---|---|
| `RESEND_API_KEY` | *(empty)* | Resend API key for email delivery |
| `MAIL_FROM` | `onboarding@resend.dev` | Sender email address |
| `MAIL_FROM_NAME` | `Smart Job Alert` | Sender display name |
| `EMAIL_WORKERS` | `4` | Parallel email threads |

### Security
| Variable | Default | Description |
|---|---|---|
| `WTF_CSRF_ENABLED` | `True` | Enable CSRF protection |
| `WTF_CSRF_TIME_LIMIT` | `3600` | CSRF token expiry (seconds) |

### Logging
| Variable | Default | Description |
|---|---|---|
| `LOG_MAX_BYTES` | `10485760` (10 MB) | Max log file size before rotation |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated log files to keep |

### Scheduler
| Variable | Default | Description |
|---|---|---|
| `SCHEDULE_HOUR` | `8` | Hour (24h) for daily scrape & alert job |
| `SCHEDULE_MINUTE` | `0` | Minute for daily scrape & alert job |

---

## 📖 How It Works

### User Flow
1. **User visits** the landing page, fills in the subscription form (email + job preferences)
2. **Verification email** is sent — user clicks the link to confirm
3. **Daily scheduler** scrapes job sites for new listings (protected by distributed lock)
4. **Matching engine** scores each new job against every subscriber's preferences (SQL pre-filtered)
5. **Personalized email** is sent (parallel delivery via thread pool)
6. **Unsubscribe** is one click from any alert email

### Scraper Design
- Each scraper extends `BaseScraper` and implements a `scrape()` method
- Anti-bot countermeasures: rotating User-Agents, realistic delays, CAPTCHA detection
- XSS-safe: all text fields sanitized with `bleach` before storage
- Batch duplicate detection in the scheduler (single query for all jobs)
- Demo scraper only runs as fallback when real scrapers return nothing

### Security Architecture
- **CSRF**: Flask-WTF `CSRFProtect` protects all POST endpoints. All templates include `{{ csrf_token() }}` hidden fields.
- **Rate Limiting**: Admin login is rate-limited via Flask-Limiter (10 req/min, 30 req/hour).
- **Authentication**: Admin passwords are hashed with bcrypt. The `AdminUser` model seeds the first admin from config on startup.
- **XSS Prevention**: Scraped data goes through `bleach.clean()` which strips dangerous HTML tags and attributes.
- **Input Validation**: Subscribe endpoint validates emails against RFC-ish regex, rejects HTML in text fields, and enforces length limits.

### Scheduler Safety
When deployed with multiple Gunicorn workers, APScheduler fires in every worker. A `SchedulerLock` database model provides distributed locking — only one worker acquires the lock and executes the daily job. Other workers skip.

---

## 📡 API Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| `GET` | `/` | — | Landing page |
| `POST` | `/subscribe` | — | Subscribe (CSRF-protected) |
| `GET` | `/verify/<token>` | — | Verify email |
| `GET` | `/unsubscribe/<token>` | — | Unsubscribe |
| `GET` | `/jobs` | — | Public job browser |
| `GET` | `/api/stats` | — | Dashboard stats (JSON) |
| `GET` | `/api/chart/subscribers` | — | Subscriber growth (JSON) |
| `GET` | `/api/chart/emails` | — | Email stats (JSON) |
| `GET` | `/api/chart/sources` | — | Source distribution (JSON) |
| `GET` | `/admin/login` | — | Admin login page |
| `POST` | `/admin/login` | ✋ Rate-limited | Admin login |
| `GET` | `/admin/` | ✅ | Dashboard |
| `GET` | `/admin/subscribers` | ✅ | Manage subscribers |
| `POST` | `/admin/subscribers/delete/<id>` | ✅ | Delete subscriber |
| `GET` | `/admin/subscribers/export` | ✅ | Export CSV |
| `GET` | `/admin/jobs` | ✅ | Manage jobs |
| `GET` | `/admin/jobs/<id>` | ✅ | Job detail |
| `POST` | `/admin/jobs/delete/<id>` | ✅ | Delete job |
| `POST` | `/admin/jobs/clear-old` | ✅ | Clear old jobs |
| `GET` | `/admin/email-history` | ✅ | Email history |
| `GET` | `/admin/scraper-history` | ✅ | Scraper history |
| `GET` | `/admin/logs` | ✅ | App logs |
| `POST` | `/admin/run-scraper` | ✅ | Manual scrape |
| `POST` | `/admin/run-alerts` | ✅ | Manual alerts |
| `POST` | `/admin/retry-failed` | ✅ | Retry failed |

All POST endpoints require a valid CSRF token.

---

## 🛠️ Development

```bash
# Run (debug mode auto-reloads)
python app.py

# Disable debug for production-like testing
FLASK_DEBUG=0 python app.py
```

### Adding a new scraper
1. Create a class in `scrapers/scrapers.py` extending `BaseScraper`
2. Set `source_name` and implement `scrape()`
3. Override `_parse_listings()` with CSS selectors matching the target site's HTML
4. Add to `SCRAPER_REGISTRY` — the scheduler and admin panel pick it up automatically

### Running tests
```bash
# Run all 110+ tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_matching.py -v

# Run with coverage (install pytest-cov first)
python -m pytest tests/ --cov=.
```

---

## 🐳 Deployment

### Production Checklist
- [ ] Set a **strong random `SECRET_KEY`** via environment variable
- [ ] Change **admin credentials** (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)
- [ ] Set **`RESEND_API_KEY`** for email delivery (or SMTP as fallback)
- [ ] Set `APP_URL` to your production domain
- [ ] Use **PostgreSQL** for concurrency (`JOB_ALERT_DATABASE_URL`)
- [ ] Run with a **production WSGI server** and **one scheduler process**
- [ ] Set `FLASK_DEBUG=0`
- [ ] See [`DEPLOY_RENDER.md`](DEPLOY_RENDER.md) for Render-specific setup

### Gunicorn
```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8000 "app:app" --timeout 120
```
> ⚠️ **Multi-worker note**: The scheduler uses database-level locking, so only one worker's scheduler executes the daily job. However, each worker will still have an active APScheduler instance. For zero waste, consider running a single-process scheduler worker separately.

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:create_app()"]
```

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Framework | Flask 3.0 |
| ORM | SQLAlchemy 3.1 |
| Auth | Flask-Login (bcrypt-hashed admin) |
| Security | Flask-WTF (CSRF), Flask-Limiter (Rate Limiting), bleach (XSS) |
| Scheduler | APScheduler 3.10 (with distributed lock) |
| Scraping | BeautifulSoup 4 + Requests + cloudscraper |
| Templates | Jinja2 + Chart.js |
| Email | Resend API + ThreadPoolExecutor (parallel delivery) |
| Database | SQLite / PostgreSQL (Neon, Supabase, Render) |
| Testing | pytest 7.x + pytest-flask (110+ tests) |

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Made with ❤️ by [Sourav Giri](https://github.com/SouravGiri-007)

</div>
