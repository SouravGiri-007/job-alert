import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime, timezone

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Default log config — overridden by app.config when available
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5


def configure_logging(max_bytes=None, backup_count=None):
    """Allow runtime configuration of log rotation limits."""
    global _MAX_BYTES, _BACKUP_COUNT
    if max_bytes is not None:
        _MAX_BYTES = max_bytes
    if backup_count is not None:
        _BACKUP_COUNT = backup_count


def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # File handler with rotation
        fh = RotatingFileHandler(
            os.path.join(LOG_DIR, 'app.log'),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
        )
        fh.setLevel(logging.DEBUG)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


def log_event(event_type, message, level='info'):
    """Log a system event."""
    logger = get_logger('jobalert')
    timestamp = datetime.now(timezone.utc).isoformat()
    log_msg = f'[{event_type}] {message}'
    if level == 'info':
        logger.info(log_msg)
    elif level == 'error':
        logger.error(log_msg)
    elif level == 'warning':
        logger.warning(log_msg)
    elif level == 'debug':
        logger.debug(log_msg)
