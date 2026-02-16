import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Business, ReviewRequest
from services import generate_review_text, generate_short_code, resolve_google_place, send_sms

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Review Boost")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

def get_base_url() -> str:
    """Read BASE_URL from env each time — picks up ngrok URL set by parent process."""
    return os.getenv("BASE_URL") or "http://localhost:8000"


# ── Root ────────────────────────────────────────────────────────────────────


@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse("/portal/send")


# ── API: Resolve Google Place ───────────────────────────────────────────────


@app.get("/api/resolve-place", response_class=JSONResponse)
def api_resolve_place(url: str):
    """AJAX endpoint: resolve a Google Maps URL to {name, place_id}."""
    if not url.strip():
        return JSONResponse({"error": "URL is required"}, status_code=400)
    result = resolve_google_place(url.strip())
    if result:
        return JSONResponse(result)
    return JSONResponse(
        {"error": "Could not resolve place. Check the URL or GOOGLE_MAPS_API_KEY."},
        status_code=404,
    )


# ── Portal: Send ─────────────────────────────────────────────────────────────


@app.get("/portal/send", response_class=HTMLResponse)
def send_page(request: Request, db: Session = Depends(get_db)):
    businesses = db.query(Business).order_by(Business.name).all()
    return templates.TemplateResponse(
        "send.html", {"request": request, "businesses": businesses, "result": None}
    )


@app.post("/portal/send", response_class=HTMLResponse)
def send_review_request(
    request: Request,
    google_link: str = Form(...),
    customer_name: str = Form(...),
    customer_contact: str = Form(...),
    carrier: str = Form(""),
    db: Session = Depends(get_db),
):
    businesses = db.query(Business).order_by(Business.name).all()

    # Resolve Google link to place_id + name
    place = resolve_google_place(google_link.strip())
    if not place:
        return templates.TemplateResponse(
            "send.html",
            {
                "request": request,
                "businesses": businesses,
                "result": "error",
                "message": "Could not resolve Google link. Make sure GOOGLE_MAPS_API_KEY is set in .env and the link is valid.",
            },
        )

    # Find or create Business by place_id
    biz = db.query(Business).filter(Business.google_place_id == place["place_id"]).first()
    if not biz:
        biz = Business(name=place["name"], google_place_id=place["place_id"])
        db.add(biz)
        db.commit()
        db.refresh(biz)
        businesses = db.query(Business).order_by(Business.name).all()

    # Generate review text via LLM
    review_text = generate_review_text(biz.name)

    # Create review request record
    code = generate_short_code()
    rr = ReviewRequest(
        business_id=biz.id,
        customer_name=customer_name.strip(),
        customer_contact=customer_contact.strip(),
        contact_type="sms",
        short_code=code,
        review_text=review_text,
        status="sent",
        sent_at=datetime.now(timezone.utc),
    )
    db.add(rr)
    db.commit()

    # Build link and send SMS
    link = f"{get_base_url()}/r/{code}"
    sent = send_sms(
        to=customer_contact.strip(),
        body=(
            f"Hi {customer_name}! Thanks for visiting {biz.name}. "
            f"We'd love a quick Google review: {link}"
        ),
        carrier=carrier.strip(),
    )

    if sent:
        return templates.TemplateResponse(
            "send.html",
            {
                "request": request,
                "businesses": businesses,
                "result": "ok",
                "message": f"SMS sent to {customer_contact}. Link: {link}",
            },
        )
    else:
        return templates.TemplateResponse(
            "send.html",
            {
                "request": request,
                "businesses": businesses,
                "result": "error",
                "message": "SMS not configured. Set TWILIO vars in .env (or SMTP + carrier for email gateway).",
            },
        )


# ── Portal: Dashboard ────────────────────────────────────────────────────────


@app.get("/portal/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    business_id: int | None = None,
    db: Session = Depends(get_db),
):
    businesses = db.query(Business).order_by(Business.name).all()

    stats = None
    requests_list = []

    if business_id:
        total = db.query(func.count(ReviewRequest.id)).filter(
            ReviewRequest.business_id == business_id
        ).scalar()
        clicked = db.query(func.count(ReviewRequest.id)).filter(
            ReviewRequest.business_id == business_id,
            ReviewRequest.status == "clicked",
        ).scalar()

        stats = {
            "total_sent": total,
            "total_clicked": clicked,
            "click_rate": round(clicked / total * 100, 1) if total else 0,
        }

        requests_list = (
            db.query(ReviewRequest)
            .filter(ReviewRequest.business_id == business_id)
            .order_by(ReviewRequest.created_at.desc())
            .limit(100)
            .all()
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "businesses": businesses,
            "selected_id": business_id,
            "stats": stats,
            "reviews": requests_list,
        },
    )


# ── Customer: Short Link Redirect ────────────────────────────────────────────


@app.get("/r/{code}", response_class=HTMLResponse)
def review_landing(code: str, request: Request, db: Session = Depends(get_db)):
    rr = db.query(ReviewRequest).filter(ReviewRequest.short_code == code).first()
    if not rr:
        return HTMLResponse("<h1>Link not found</h1>", status_code=404)

    # Mark as clicked
    if rr.status == "sent":
        rr.status = "clicked"
        rr.clicked_at = datetime.now(timezone.utc)
        db.commit()

    biz = db.query(Business).filter(Business.id == rr.business_id).first()

    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "business_name": biz.name,
            "google_place_id": biz.google_place_id,
            "review_text": rr.review_text,
        },
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))

    # Auto-create public tunnel via ngrok when BASE_URL is not a real public URL
    base = os.getenv("BASE_URL", "").strip()
    is_local = not base or "localhost" in base or "127.0.0.1" in base

    if is_local:
        try:
            from pyngrok import ngrok

            authtoken = os.getenv("NGROK_AUTHTOKEN")
            if authtoken:
                ngrok.set_auth_token(authtoken)

            public_url = ngrok.connect(port).public_url
            os.environ["BASE_URL"] = public_url
            print(f"\n{'='*50}")
            print(f"  Public URL: {public_url}")
            print(f"  Portal:     {public_url}/portal/send")
            print(f"{'='*50}\n")
        except Exception as e:
            print(f"[ngrok] Failed: {e}")
            print("[ngrok] Fix: pip install pyngrok && ngrok config add-authtoken <token>")

    uvicorn.run("main:app", host="0.0.0.0", port=port)
