from ..extensions import db
from .base import TimestampMixin


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)

    sites = db.relationship("Site", back_populates="user", cascade="all, delete-orphan")
    logs = db.relationship("Log", back_populates="user")

    def set_password(self, password: str) -> None:
        from ..extensions import bcrypt

        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        from ..extensions import bcrypt

        return bcrypt.check_password_hash(self.password_hash, password)