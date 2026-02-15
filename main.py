import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Business, ReviewRequest
from services import generate_review_text, generate_short_code, send_email, send_sms

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Review Boost")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

def get_base_url() -> str:
    """Read BASE_URL from env each time — picks up ngrok URL set by parent process."""
    return os.getenv("BASE_URL") or "http://localhost:8000"


# ── Portal: Setup ────────────────────────────────────────────────────────────


@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse("/portal/setup")


@app.get("/portal/setup", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    businesses = db.query(Business).order_by(Business.created_at.desc()).all()
    return templates.TemplateResponse(
        "setup.html", {"request": request, "businesses": businesses}
    )


@app.post("/portal/setup", response_class=RedirectResponse)
def setup_create(
    name: str = Form(...),
    google_place_id: str = Form(...),
    db: Session = Depends(get_db),
):
    biz = Business(name=name, google_place_id=google_place_id.strip())
    db.add(biz)
    db.commit()
    return RedirectResponse("/portal/setup", status_code=303)


@app.post("/portal/setup/delete/{biz_id}", response_class=RedirectResponse)
def setup_delete(biz_id: int, db: Session = Depends(get_db)):
    biz = db.query(Business).filter(Business.id == biz_id).first()
    if biz:
        db.query(ReviewRequest).filter(ReviewRequest.business_id == biz_id).delete()
        db.delete(biz)
        db.commit()
    return RedirectResponse("/portal/setup", status_code=303)


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
    business_id: int = Form(...),
    customer_name: str = Form(...),
    customer_contact: str = Form(...),
    contact_type: str = Form(...),
    db: Session = Depends(get_db),
):
    biz = db.query(Business).filter(Business.id == business_id).first()
    businesses = db.query(Business).order_by(Business.name).all()

    if not biz:
        return templates.TemplateResponse(
            "send.html",
            {"request": request, "businesses": businesses, "result": "error", "message": "Business not found."},
        )

    # Generate review text via LLM
    review_text = generate_review_text(biz.name)

    # Create review request record
    code = generate_short_code()
    rr = ReviewRequest(
        business_id=biz.id,
        customer_name=customer_name.strip(),
        customer_contact=customer_contact.strip(),
        contact_type=contact_type,
        short_code=code,
        review_text=review_text,
        status="sent",
        sent_at=datetime.now(timezone.utc),
    )
    db.add(rr)
    db.commit()

    # Build link and send
    link = f"{get_base_url()}/r/{code}"

    if contact_type == "email":
        sent = send_email(
            to=customer_contact.strip(),
            subject=f"{biz.name} would love your review!",
            body=(
                f"<p>Hi {customer_name},</p>"
                f"<p>Thanks for visiting <b>{biz.name}</b>! "
                f"We'd really appreciate a quick Google review.</p>"
                f'<p><a href="{link}">Leave a review &rarr;</a></p>'
                f"<p>It only takes a moment. Thank you!</p>"
            ),
        )
    else:
        sent = send_sms(
            to=customer_contact.strip(),
            body=(
                f"Hi {customer_name}! Thanks for visiting {biz.name}. "
                f"We'd love a quick Google review: {link}"
            ),
        )

    if sent:
        return templates.TemplateResponse(
            "send.html",
            {
                "request": request,
                "businesses": businesses,
                "result": "ok",
                "message": f"Sent to {customer_contact} via {contact_type}. Link: {link}",
            },
        )
    else:
        hint = "Set SMTP_USER and SMTP_PASSWORD in .env" if contact_type == "email" else "Set TWILIO vars in .env"
        return templates.TemplateResponse(
            "send.html",
            {
                "request": request,
                "businesses": businesses,
                "result": "error",
                "message": f"{contact_type.upper()} not configured. {hint}",
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
            # Set env var so uvicorn child process inherits it
            os.environ["BASE_URL"] = public_url
            print(f"\n{'='*50}")
            print(f"  Public URL: {public_url}")
            print(f"  Portal:     {public_url}/portal/setup")
            print(f"{'='*50}\n")
        except Exception as e:
            print(f"[ngrok] Failed: {e}")
            print("[ngrok] Fix: pip install pyngrok && ngrok config add-authtoken <token>")

    uvicorn.run("main:app", host="0.0.0.0", port=port)
