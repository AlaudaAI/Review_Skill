from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    google_place_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    review_requests = relationship("ReviewRequest", back_populates="business")


class ReviewRequest(Base):
    __tablename__ = "review_requests"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    customer_contact = Column(String, nullable=False)
    short_code = Column(String, unique=True, index=True, nullable=False)
    review_text = Column(Text, nullable=False)
    status = Column(String, default="pending")  # pending -> sent -> clicked
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)

    business = relationship("Business", back_populates="review_requests")
