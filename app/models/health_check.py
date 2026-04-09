from datetime import UTC, datetime

from ..extensions import db


class SiteHealthCheck(db.Model):
    __tablename__ = "site_health_checks"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False, index=True)
    checked_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    is_up = db.Column(db.Boolean, nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    response_time_ms = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.String(512), nullable=True)

    site = db.relationship("Site", back_populates="health_checks")