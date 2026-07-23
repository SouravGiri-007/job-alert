from extensions import db
from datetime import datetime, timezone


class EmailHistory(db.Model):
    __tablename__ = 'email_histories'

    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('subscribers.id'), nullable=False, index=True)
    jobs_sent = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, sent, failed
    error_message = db.Column(db.Text, default='')
    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    subscriber = db.relationship('Subscriber', back_populates='email_histories')

    __table_args__ = (
        db.Index('idx_email_sent_status', 'sent_at', 'status'),
    )

    def __repr__(self):
        return f'<EmailHistory {self.subscriber_id} - {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'subscriber_id': self.subscriber_id,
            'subscriber_email': self.subscriber.email if self.subscriber else '',
            'jobs_sent': self.jobs_sent,
            'status': self.status,
            'error_message': self.error_message,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
        }
