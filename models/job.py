from extensions import db
from datetime import datetime, timezone


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200), default='')
    location = db.Column(db.String(200), default='')
    salary = db.Column(db.String(200), default='')
    skills = db.Column(db.String(500), default='')
    url = db.Column(db.String(500), default='')
    source = db.Column(db.String(100), default='')
    posted_date = db.Column(db.String(50), default='')
    description = db.Column(db.Text, default='')
    job_type = db.Column(db.String(50), default='')
    scraped_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        db.Index('idx_jobs_source', 'source'),
        db.Index('idx_jobs_title_company', 'title', 'company'),
        db.Index('idx_jobs_scraped_source', 'scraped_at', 'source'),
    )

    def __repr__(self):
        return f'<Job {self.title} at {self.company}>'

    def get_skills_list(self):
        if not self.skills:
            return []
        return [s.strip().lower() for s in self.skills.split(',') if s.strip()]

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'salary': self.salary,
            'skills': self.skills,
            'url': self.url,
            'source': self.source,
            'posted_date': self.posted_date,
            'description': self.description,
            'job_type': self.job_type,
            'scraped_at': self.scraped_at.isoformat() if self.scraped_at else None,
        }

    @staticmethod
    def is_duplicate(title, company, location):
        return Job.query.filter_by(title=title, company=company, location=location).first() is not None
