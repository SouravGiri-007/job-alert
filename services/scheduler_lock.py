"""Database-level distributed lock for scheduler safety.

When deployed with multiple Gunicorn workers (or multiple processes),
APScheduler fires in EVERY worker. This lock ensures only one worker
runs the daily job at a time.

Usage:
    with SchedulerLock.acquire('daily_job', timeout_seconds=300) as acquired:
        if acquired:
            # Only one worker enters this block
            ...
"""
from datetime import datetime, timezone, timedelta
from extensions import db


class SchedulerLock(db.Model):
    __tablename__ = 'scheduler_locks'

    lock_name = db.Column(db.String(100), primary_key=True)
    locked_at = db.Column(db.DateTime, nullable=True)
    locked_by = db.Column(db.String(100), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    @classmethod
    def acquire(cls, name: str, timeout_seconds: int = 300, owner: str = 'default'):
        """Context manager that returns True if the lock was acquired."""
        return _LockContext(name, timeout_seconds, owner)

    @classmethod
    def _try_lock(cls, name: str, timeout_seconds: int, owner: str) -> bool:
        """Attempt to acquire the lock atomically."""
        now = datetime.now(timezone.utc)

        try:
            lock = cls.query.filter_by(lock_name=name).with_for_update().first()

            if lock is None:
                lock = cls(
                    lock_name=name,
                    locked_at=now,
                    locked_by=owner,
                    expires_at=now + timedelta(seconds=timeout_seconds),
                )
                db.session.add(lock)
                db.session.commit()
                return True

            if lock.expires_at and lock.expires_at < now:
                lock.locked_at = now
                lock.locked_by = owner
                lock.expires_at = now + timedelta(seconds=timeout_seconds)
                db.session.commit()
                return True

            db.session.rollback()
            return False

        except Exception:
            db.session.rollback()
            return False

    @classmethod
    def _release(cls, name: str):
        """Release the lock."""
        try:
            lock = cls.query.filter_by(lock_name=name).first()
            if lock:
                db.session.delete(lock)
                db.session.commit()
        except Exception:
            db.session.rollback()


class _LockContext:
    """Context manager for SchedulerLock."""

    def __init__(self, name: str, timeout_seconds: int, owner: str):
        self.name = name
        self.timeout = timeout_seconds
        self.owner = owner

    def __enter__(self):
        self.acquired = SchedulerLock._try_lock(self.name, self.timeout, self.owner)
        return self.acquired

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            SchedulerLock._release(self.name)
