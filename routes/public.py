"""Public routes: landing page redirect + customer review landing."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Business, ReviewRequest

router = APIRouter()

_templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse("/portal/send")


@router.get("/r/{code}", response_class=HTMLResponse)
def review_landing(code: str, request: Request, db: Session = Depends(get_db)):
    rr = db.query(ReviewRequest).filter(ReviewRequest.short_code == code).first()
    if not rr:
        return HTMLResponse("<h1>Link not found</h1>", status_code=404)

    if rr.status == "sent":
        rr.status = "clicked"
        rr.clicked_at = datetime.now(timezone.utc)
        db.commit()

    biz = db.query(Business).filter(Business.id == rr.business_id).first()

    return _templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "business_name": biz.name,
            "google_place_id": biz.google_place_id,
            "review_text": rr.review_text,
        },
    )
