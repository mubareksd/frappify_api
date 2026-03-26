from datetime import UTC, datetime

from .extensions import db


class TimestampMixin:
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


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
        from .extensions import bcrypt

        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        from .extensions import bcrypt

        return bcrypt.check_password_hash(self.password_hash, password)


class Site(TimestampMixin, db.Model):
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.String(6), unique=True, nullable=False)
    base_url = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    user = db.relationship("User", back_populates="sites")
    cookies = db.relationship(
        "Cookie", back_populates="site", cascade="all, delete-orphan"
    )


class Cookie(TimestampMixin, db.Model):
    __tablename__ = "cookies"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    cookie_name = db.Column(db.String(255), nullable=False)
    cookie_value = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    path = db.Column(db.String(255), nullable=False, default="/")
    domain = db.Column(db.String(255), nullable=False)

    site = db.relationship("Site", back_populates="cookies")


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    method = db.Column(db.String(10), nullable=False)
    path = db.Column(db.String(512), nullable=False)
    headers = db.Column(db.JSON, nullable=False)
    response_status = db.Column(db.Integer, nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    timestamp = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    user = db.relationship("User", back_populates="logs")
