import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import Base, engine
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


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Review Boost server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument(
        "--sms-backend",
        choices=["auto", "twilio", "email"],
        default=os.getenv("SMS_BACKEND", "auto"),
        help="SMS backend: twilio, email (carrier gateway), or auto (default)",
    )
    args = parser.parse_args()

    os.environ["SMS_BACKEND"] = args.sms_backend
    port = args.port

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
