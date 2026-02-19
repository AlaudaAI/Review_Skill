import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMS_GATEWAYS = {
    "tmobile": {"gateway": "tmomail.net", "label": "T-Mobile / Mint / Metro"},
    "att": {"gateway": "txt.att.net", "label": "AT&T / Cricket"},
    "verizon": {"gateway": "vtext.com", "label": "Verizon"},
    "sprint": {"gateway": "messaging.sprintpcs.com", "label": "Sprint"},
}


def _send_email_internal(to: str, subject: str, body: str) -> dict:
    """Send email. Returns {"ok": True} or {"ok": False, "error": "reason"}."""
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    if not smtp_user or not smtp_pass:
        return {"ok": False, "error": "SMTP_USER or SMTP_PASSWORD env var is missing"}

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to, msg.as_string())
        return {"ok": True}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok": False, "error": f"SMTP auth failed (check SMTP_USER/SMTP_PASSWORD): {e}"}
    except smtplib.SMTPException as e:
        return {"ok": False, "error": f"SMTP error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Email send error: {e}"}


def _send_sms_via_email(to: str, body: str, carrier: str) -> dict:
    """Send SMS via carrier email gateway. Returns {"ok": True/False, "error": ...}."""
    entry = SMS_GATEWAYS.get(carrier)
    if not entry:
        return {"ok": False, "error": f"Unknown carrier: '{carrier}'. Supported: {list(SMS_GATEWAYS.keys())}"}
    gateway = entry["gateway"]

    digits = "".join(c for c in to if c.isdigit())
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        return {"ok": False, "error": f"Invalid US phone number: {to}"}

    sms_email = f"{digits}@{gateway}"
    result = _send_email_internal(to=sms_email, subject="", body=body)
    if result["ok"]:
        logger.info("SMS-GW sent to %s via %s", to, sms_email)
    else:
        logger.error("SMS-GW error: %s", result["error"])
    return result


def _send_via_twilio(to: str, body: str) -> dict:
    """Send SMS via Twilio. Returns {"ok": True/False, "error": ...}."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_FROM_NUMBER")
    if not all([sid, token, from_num]):
        return {"ok": False, "error": "Twilio env vars not set (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)"}
    try:
        from twilio.rest import Client

        msg = Client(sid, token).messages.create(body=body, from_=from_num, to=to)
        logger.info("SMS sent to %s | SID: %s", to, msg.sid)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"Twilio failed: {e}"}


def diagnose_sms() -> dict:
    """Check SMS backend configuration and SMTP connectivity."""
    backend = os.getenv("SMS_BACKEND", "twilio").lower()
    info = {"backend": backend}

    if backend == "twilio":
        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        from_num = os.getenv("TWILIO_FROM_NUMBER")
        info["twilio_configured"] = bool(sid and token and from_num)
        if not info["twilio_configured"]:
            info["error"] = "Missing TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_FROM_NUMBER"
        return info

    # email backend — test SMTP connection
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    info["smtp_host"] = smtp_host
    info["smtp_port"] = smtp_port
    info["smtp_user_set"] = bool(smtp_user)
    info["smtp_pass_set"] = bool(smtp_pass)

    if not smtp_user or not smtp_pass:
        info["error"] = "SMTP_USER or SMTP_PASSWORD not set"
        return info

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            info["smtp_login"] = "ok"
    except smtplib.SMTPAuthenticationError as e:
        info["smtp_login"] = "failed"
        info["error"] = f"SMTP auth failed: {e}"
    except Exception as e:
        info["smtp_login"] = "failed"
        info["error"] = f"SMTP connection error: {e}"

    return info


def send_sms(to: str, body: str, carrier: str = "") -> dict:
    """Send SMS. Backend chosen by SMS_BACKEND env var: twilio or email.
    Returns {"ok": True/False, "error": "reason"}.
    """
    backend = os.getenv("SMS_BACKEND", "twilio").lower()

    if backend == "twilio":
        return _send_via_twilio(to, body)

    if not carrier:
        return {"ok": False, "error": f"Email backend requires carrier selection. SMS_BACKEND={backend}"}
    return _send_sms_via_email(to, body, carrier)
