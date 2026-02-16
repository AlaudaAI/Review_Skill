"""JSON API endpoints — consumed by the portal frontend."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Business, ReviewRequest
from services import diagnose_sms, generate_review_text, generate_short_code, resolve_google_place, send_sms

router = APIRouter(prefix="/api")


def _base_url() -> str:
    return os.getenv("BASE_URL") or "http://localhost:8000"


@router.get("/resolve-place")
def resolve_place(url: str):
    if not url.strip():
        return JSONResponse({"error": "URL is required"}, status_code=400)
    result = resolve_google_place(url.strip())
    if result:
        return result
    return JSONResponse(
        {"error": "Could not resolve place. Check the URL or GOOGLE_MAPS_API_KEY."},
        status_code=404,
    )


@router.get("/businesses")
def list_businesses(db: Session = Depends(get_db)):
    rows = db.query(Business).order_by(Business.name).all()
    return [
        {"id": b.id, "name": b.name, "google_place_id": b.google_place_id}
        for b in rows
    ]


@router.post("/send")
def send_review(payload: dict, db: Session = Depends(get_db)):
    google_link = (payload.get("google_link") or "").strip()
    customer_name = (payload.get("customer_name") or "").strip()
    phones = [p.strip() for p in payload.get("phones", []) if p.strip()]
    carrier = (payload.get("carrier") or "").strip()

    if not customer_name:
        return JSONResponse({"error": "Customer name is required."}, status_code=400)
    if not phones:
        return JSONResponse({"error": "At least one phone number is required."}, status_code=400)

    place = resolve_google_place(google_link)
    if not place:
        return JSONResponse(
            {"error": "Could not resolve Google link. Check GOOGLE_MAPS_API_KEY and the link."},
            status_code=400,
        )

    biz = db.query(Business).filter(Business.google_place_id == place["place_id"]).first()
    if not biz:
        biz = Business(name=place["name"], google_place_id=place["place_id"])
        db.add(biz)
        db.commit()
        db.refresh(biz)

    sent_to: list[str] = []
    failed: list[str] = []
    errors: list[str] = []
    for phone in phones:
        review_text = generate_review_text(biz.name)
        code = generate_short_code()
        rr = ReviewRequest(
            business_id=biz.id,
            customer_name=customer_name,
            customer_contact=phone,
            contact_type="sms",
            short_code=code,
            review_text=review_text,
            status="sent",
            sent_at=datetime.now(timezone.utc),
        )
        db.add(rr)
        db.commit()

        link = f"{_base_url()}/r/{code}"
        result = send_sms(
            to=phone,
            body=f"Hi {customer_name}! Thanks for visiting {biz.name}. We'd love a quick Google review: {link}",
            carrier=carrier,
        )
        if result["ok"]:
            sent_to.append(phone)
        else:
            failed.append(phone)
            errors.append(f"{phone}: {result.get('error', 'unknown')}")

    resp = {"sent": sent_to, "failed": failed}
    if errors:
        resp["errors"] = errors
    return resp


@router.get("/dashboard")
def dashboard_stats(business_id: int, db: Session = Depends(get_db)):
    total = db.query(func.count(ReviewRequest.id)).filter(
        ReviewRequest.business_id == business_id
    ).scalar()
    clicked = db.query(func.count(ReviewRequest.id)).filter(
        ReviewRequest.business_id == business_id,
        ReviewRequest.status == "clicked",
    ).scalar()

    reviews = (
        db.query(ReviewRequest)
        .filter(ReviewRequest.business_id == business_id)
        .order_by(ReviewRequest.created_at.desc())
        .limit(100)
        .all()
    )

    return {
        "stats": {
            "total_sent": total,
            "total_clicked": clicked,
            "click_rate": round(clicked / total * 100, 1) if total else 0,
        },
        "reviews": [
            {
                "customer_name": r.customer_name,
                "customer_contact": r.customer_contact,
                "status": r.status,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "clicked_at": r.clicked_at.isoformat() if r.clicked_at else None,
            }
            for r in reviews
        ],
    }


@router.get("/sms-diagnose")
def sms_diagnose():
    """Quick diagnostic: checks SMS backend config and SMTP connectivity."""
    return diagnose_sms()
