from extensions import db
from datetime import datetime, timezone


class ScraperHistory(db.Model):
    __tablename__ = 'scraper_histories'

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False, index=True)
    jobs_found = db.Column(db.Integer, default=0)
    jobs_new = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')  # pending, success, failed
    error_message = db.Column(db.Text, default='')
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    finished_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<ScraperHistory {self.source} - {self.status}>'

    @property
    def duration(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'source': self.source,
            'jobs_found': self.jobs_found,
            'jobs_new': self.jobs_new,
            'status': self.status,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'duration': self.duration,
        }
