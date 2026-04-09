from ..extensions import db
from .base import TimestampMixin


class IpFilter(TimestampMixin, db.Model):
    __tablename__ = "ip_filters"

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)

    site = db.relationship("Site", back_populates="ip_filters")


class Site(TimestampMixin, db.Model):
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.String(6), unique=True, nullable=False)
    base_url = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    enable_ip_filter = db.Column(db.Boolean, nullable=False, default=False)
    ip_filter_mode = db.Column(db.String(10), nullable=False, default="whitelist")

    user = db.relationship("User", back_populates="sites")
    cookies = db.relationship(
        "Cookie", back_populates="site", cascade="all, delete-orphan"
    )
    ip_filters = db.relationship(
        "IpFilter", back_populates="site", cascade="all, delete-orphan"
    )
    health_checks = db.relationship(
        "SiteHealthCheck", back_populates="site", cascade="all, delete-orphan"
    )