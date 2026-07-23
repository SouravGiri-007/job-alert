import os
import sys
import warnings

# Add project directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from config import Config
from extensions import db, login_manager, csrf, limiter
from utils.logger import configure_logging


def _check_security(app: Flask):
    """Emit warnings for common production security gaps."""
    if app.config['SECRET_KEY'] == 'dev-secret-key-change-in-production':
        warnings.warn(
            'SECURITY: Using default SECRET_KEY. Set SECRET_KEY environment variable '
            'to a random value in production.',
            RuntimeWarning
        )
    if app.debug:
        warnings.warn(
            'SECURITY: Flask debug mode is enabled. Disable in production by setting '
            'FLASK_DEBUG=0 or not passing debug=True.',
            RuntimeWarning
        )
    if not app.config.get('RESEND_API_KEY'):
        warnings.warn(
            'SECURITY: Resend API key not configured. Email delivery will fail.',
            RuntimeWarning
        )


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Configure logging rotation from app config
    configure_logging(
        max_bytes=app.config.get('LOG_MAX_BYTES', 10 * 1024 * 1024),
        backup_count=app.config.get('LOG_BACKUP_COUNT', 5),
    )

    # Import models to register them with SQLAlchemy
    from models.subscriber import Subscriber
    from models.job import Job
    from models.email_history import EmailHistory
    from models.scraper_history import ScraperHistory
    from models.admin import AdminUser
    from services.scheduler_lock import SchedulerLock  # noqa: F401 — registers model

    # Register blueprints
    from routes.main import main_bp
    from routes.admin import admin_bp, load_admin_user
    from routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')

    # Register user loader for Flask-Login
    login_manager.user_loader(load_admin_user)

    # Create tables and seed admin (non-fatal if DB is down)
    with app.app_context():
        try:
            db.create_all()
            # Seed default admin user if none exists
            AdminUser.seed_default_admin(
                app.config['ADMIN_USERNAME'],
                app.config['ADMIN_PASSWORD'],
            )
        except Exception as e:
            app.logger.error(
                f'Database init failed: {e}. '
                'The app will retry on the first request.'
            )

    # Initialize scheduler (only if DB is available)
    from scheduler.scheduler import init_scheduler
    try:
        init_scheduler(app)
    except Exception as e:
        app.logger.error(f'Scheduler init failed: {e}. Scheduler will be unavailable until DB is reachable.')

    # Run security checks
    _check_security(app)

    # Context processor for templates
    @app.context_processor
    def inject_globals():
        return {
            'app_name': app.config['APP_NAME'],
            'app_url': app.config['APP_URL'],
        }

    return app


# Module-level app for Gunicorn (used by: gunicorn app:app)
app = create_app()

if __name__ == '__main__':
    import os
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug, port=5000)
