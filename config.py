import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    _db_url = os.environ.get('JOB_ALERT_DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = _db_url if _db_url.startswith(('sqlite://', 'postgresql://', 'mysql://')) else f'sqlite:///{os.path.join(BASE_DIR, "database.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Admin credentials (used only for seeding first user)
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

    # SMTP Configuration
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    MAIL_FROM = os.environ.get('MAIL_FROM', 'noreply@jobalert.com')
    MAIL_FROM_NAME = os.environ.get('MAIL_FROM_NAME', 'Smart Job Alert')

    # Scheduler
    SCHEDULER_API_ENABLED = True
    SCHEDULE_HOUR = int(os.environ.get('SCHEDULE_HOUR', 8))
    SCHEDULE_MINUTE = int(os.environ.get('SCHEDULE_MINUTE', 0))

    # App
    APP_NAME = 'Smart Job Alert'
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')

    # Send parallel — set >1 to enable concurrent email sending
    EMAIL_WORKERS = int(os.environ.get('EMAIL_WORKERS', 4))

    # RapidAPI
    RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', '')
    RAPIDAPI_LINKEDIN_HOST = os.environ.get('RAPIDAPI_LINKEDIN_HOST', 'linkedin-job-search-api.p.rapidapi.com')
    RAPIDAPI_INDIANJOBS_KEY = os.environ.get('RAPIDAPI_INDIANJOBS_KEY', '')
    RAPIDAPI_INDIANJOBS_HOST = os.environ.get('RAPIDAPI_INDIANJOBS_HOST', 'indian-jobs-api.p.rapidapi.com')

    # Pagination
    PER_PAGE = 10

    # CSRF / Security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour

    # Rate limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI = "memory://"

    # Logging
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 10 * 1024 * 1024))  # 10 MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 5))
