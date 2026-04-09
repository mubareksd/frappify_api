from ..extensions import db
from .base import TimestampMixin


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