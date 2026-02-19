import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from database import Base, engine, get_configured_base_url
from routes import api_router, public_router

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Review Boost")

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(api_router)
app.include_router(public_router)

# ── Static files ─────────────────────────────────────────────────────────────
_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static), name="static")


# ── Portal pages (served as static HTML) ─────────────────────────────────────
@app.get("/portal/send")
def portal_send():
    return FileResponse(_static / "send.html")


@app.get("/portal/dashboard")
def portal_dashboard():
    return FileResponse(_static / "dashboard.html")


# ── Local dev entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Review Boost server")
    parser.add_argument(
        "--sms-backend",
        choices=["twilio", "email"],
        required=True,
        help="SMS backend: twilio or email (carrier gateway)",
    )
    args = parser.parse_args()

    os.environ["SMS_BACKEND"] = args.sms_backend
    port = int(os.getenv("PORT", "8000"))

    base = get_configured_base_url()
    is_local = not base or "localhost" in base or "127.0.0.1" in base

    if is_local:
        try:
            from pyngrok import ngrok

            authtoken = os.getenv("NGROK_AUTHTOKEN")
            if authtoken:
                ngrok.set_auth_token(authtoken)

            public_url = ngrok.connect(port).public_url
            os.environ["BASE_URL"] = public_url
            logger.info("Public URL: %s", public_url)
            logger.info("Portal:     %s/portal/send", public_url)
        except Exception as e:
            logger.warning("ngrok failed: %s", e)
            logger.warning("Fix: pip install pyngrok && ngrok config add-authtoken <token>")

    uvicorn.run("main:app", host="0.0.0.0", port=port)
