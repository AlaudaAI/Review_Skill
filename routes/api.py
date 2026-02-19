"""JSON API endpoints — consumed by the portal frontend."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_configured_base_url, get_db
from models import Business, ReviewRequest
from services import SMS_GATEWAYS, diagnose_sms, generate_review_text, generate_unique_short_code, resolve_google_place, send_sms

router = APIRouter(prefix="/api")


def _base_url(request: Request) -> str:
    env = get_configured_base_url()
    if env:
        return env.rstrip("/")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}"


@router.get("/carriers")
def list_carriers():
    return [{"value": k, "label": v["label"]} for k, v in SMS_GATEWAYS.items()]


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


@router.post("/generate")
def generate_reviews(request: Request, payload: dict, db: Session = Depends(get_db)):
    """Resolve business, generate reviews, create DB records with real links."""
    google_link = (payload.get("google_link") or "").strip()
    phones = [p.strip() for p in payload.get("phones", []) if p.strip()]

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

    base = _base_url(request)
    reviews = []
    for phone in phones:
        try:
            review_text = generate_review_text(biz.name)
        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to generate review text: {e}"},
                status_code=502,
            )
        code = generate_unique_short_code(db)
        link = f"{base}/r/{code}"
        sms_body = f"Thanks for visiting {biz.name}! We'd love a quick Google review: {link}"

        rr = ReviewRequest(
            business_id=biz.id,
            customer_contact=phone,
            short_code=code,
            review_text=review_text,
            status="pending",
        )
        db.add(rr)
        db.commit()
        db.refresh(rr)

        reviews.append({
            "id": rr.id,
            "phone": phone,
            "review_text": review_text,
            "sms_body": sms_body,
            "link": link,
        })

    return {
        "business_name": biz.name,
        "reviews": reviews,
    }


@router.post("/send")
def send_review(payload: dict, db: Session = Depends(get_db)):
    """Send previously generated reviews. Accepts edited sms_body and review_text."""
    items = payload.get("reviews", [])
    carrier = (payload.get("carrier") or "").strip()

    if not items:
        return JSONResponse({"error": "No reviews to send."}, status_code=400)

    sent_to: list[str] = []
    failed: list[str] = []
    errors: list[str] = []
    for item in items:
        rr_id = item.get("id")
        sms_body = (item.get("sms_body") or "").strip()
        review_text = (item.get("review_text") or "").strip()

        rr = db.query(ReviewRequest).filter(ReviewRequest.id == rr_id).first()
        if not rr:
            continue

        # Apply edits from preview
        if review_text:
            rr.review_text = review_text
        rr.status = "sent"
        rr.sent_at = datetime.now(timezone.utc)
        db.commit()

        result = send_sms(to=rr.customer_contact, body=sms_body, carrier=carrier)
        if result["ok"]:
            sent_to.append(rr.customer_contact)
        else:
            failed.append(rr.customer_contact)
            errors.append(f"{rr.customer_contact}: {result.get('error', 'unknown')}")

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
                "id": r.id,
                "customer_contact": r.customer_contact,
                "status": r.status,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "clicked_at": r.clicked_at.isoformat() if r.clicked_at else None,
            }
            for r in reviews
        ],
    }


@router.delete("/review/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db)):
    rr = db.query(ReviewRequest).filter(ReviewRequest.id == review_id).first()
    if not rr:
        return JSONResponse({"error": "Not found"}, status_code=404)
    db.delete(rr)
    db.commit()
    return {"ok": True}


@router.get("/sms-diagnose")
def sms_diagnose():
    """Quick diagnostic: checks SMS backend config and SMTP connectivity."""
    return diagnose_sms()


@router.post("/sms-test")
def sms_test(payload: dict):
    """Send a plain-text test SMS (no URL) to verify carrier gateway."""
    phone = (payload.get("phone") or "").strip()
    carrier = (payload.get("carrier") or "").strip()
    if not phone or not carrier:
        return JSONResponse({"error": "phone and carrier are required"}, status_code=400)
    result = send_sms(to=phone, body="Test message from ReviewBoost. If you see this, SMS is working!", carrier=carrier)
    return result
