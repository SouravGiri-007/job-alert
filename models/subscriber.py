from extensions import db
from datetime import datetime, timezone


class Subscriber(db.Model):
    __tablename__ = 'subscribers'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    role = db.Column(db.String(100), default='')
    skills = db.Column(db.String(500), default='')
    location = db.Column(db.String(200), default='')
    experience = db.Column(db.String(50), default='')
    job_type = db.Column(db.String(50), default='')
    frequency = db.Column(db.String(20), default='daily')
    is_verified = db.Column(db.Boolean, default=False, index=True)
    verification_token = db.Column(db.String(100), unique=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    email_histories = db.relationship('EmailHistory', back_populates='subscriber', lazy='dynamic')

    __table_args__ = (
        db.Index('idx_subscriber_verified_active', 'is_verified', 'is_active'),
    )

    def __repr__(self):
        return f'<Subscriber {self.email}>'

    def get_skills_list(self):
        if not self.skills:
            return []
        return [s.strip().lower() for s in self.skills.split(',') if s.strip()]

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'role': self.role,
            'skills': self.skills,
            'location': self.location,
            'experience': self.experience,
            'job_type': self.job_type,
            'frequency': self.frequency,
            'is_verified': self.is_verified,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
