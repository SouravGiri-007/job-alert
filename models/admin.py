"""Admin user model with bcrypt password hashing.
Moves away from config-based auth to a database-backed admin user.
"""
import bcrypt
from datetime import datetime, timezone
from extensions import db


class AdminUser(db.Model):
    """Persistent admin user with hashed passwords."""

    __tablename__ = 'admin_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Flask-Login protocol
    is_authenticated = True
    is_anonymous = False

    def __repr__(self):
        return f'<AdminUser {self.username}>'

    def get_id(self):
        return str(self.id)

    def set_password(self, password: str) -> None:
        """Hash and store password using bcrypt."""
        self.password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        if not self.password_hash:
            return False
        return bcrypt.checkpw(
            password.encode('utf-8'),
            self.password_hash.encode('utf-8')
        )

    @classmethod
    def seed_default_admin(cls, username: str, password: str) -> 'AdminUser':
        """Create the default admin user if none exists. Called at startup."""
        admin = cls.query.filter_by(username=username).first()
        if not admin:
            admin = cls(username=username)
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
        return admin
