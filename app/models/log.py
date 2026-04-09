from datetime import UTC, datetime

from ..extensions import db


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    method = db.Column(db.String(10), nullable=False)
    path = db.Column(db.String(512), nullable=False)
    headers = db.Column(db.JSON, nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    response_status = db.Column(db.Integer, nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    timestamp = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    user = db.relationship("User", back_populates="logs")