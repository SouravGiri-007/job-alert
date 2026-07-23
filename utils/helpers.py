import secrets
import csv
import io
from datetime import datetime, timezone
from flask import flash


def generate_token():
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


def flash_success(message):
    flash(message, 'success')


def flash_error(message):
    flash(message, 'error')


def flash_info(message):
    flash(message, 'info')


def flash_warning(message):
    flash(message, 'warning')


def format_datetime(dt):
    """Format datetime for display."""
    if dt is None:
        return 'N/A'
    if isinstance(dt, str):
        return dt
    return dt.strftime('%Y-%m-%d %H:%M')


def format_duration(seconds):
    """Format seconds into human-readable duration."""
    if seconds is None:
        return 'N/A'
    if seconds < 60:
        return f'{seconds:.1f}s'
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f'{minutes}m {secs}s'


def generate_csv(data, fieldnames):
    """Generate CSV file content from data."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow(row)
    output.seek(0)
    return output.getvalue()

