import os
import secrets
import smtplib
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic


def generate_short_code(length: int = 7) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_review_text(business_name: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write a short, natural-sounding 5-star Google review for "
                    f"a business called '{business_name}'. "
                    f"Keep it 2-3 sentences, warm and authentic. "
                    f"No hashtags or emojis. Return only the review text."
                ),
            }
        ],
    )
    return message.content[0].text.strip()


def send_email(to: str, subject: str, body: str) -> bool:
    """Send email via SMTP (e.g. Gmail). No third-party SDK needed."""
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    if not smtp_user or not smtp_pass:
        print(f"[EMAIL SKIP] SMTP not configured. To: {to} | Subject: {subject}")
        return False

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, to, msg.as_string())

    print(f"[EMAIL SENT] To: {to} | Subject: {subject}")
    return True


SMS_GATEWAYS = {
    "tmobile": "tmomail.net",      # T-Mobile / Mint / Metro
    "att": "txt.att.net",           # AT&T / Cricket
    "verizon": "vtext.com",         # Verizon
    "sprint": "messaging.sprintpcs.com",  # Sprint / legacy
}


def send_sms_via_email(to: str, body: str, carrier: str) -> bool:
    """Send SMS through carrier email-to-SMS gateway using existing SMTP."""
    gateway = SMS_GATEWAYS.get(carrier)
    if not gateway:
        print(f"[SMS-GW SKIP] Unknown carrier: {carrier}")
        return False

    # Strip non-digits from phone number
    digits = "".join(c for c in to if c.isdigit())
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]  # remove country code
    if len(digits) != 10:
        print(f"[SMS-GW ERROR] Invalid US phone number: {to}")
        return False

    sms_email = f"{digits}@{gateway}"
    try:
        # Reuse existing send_email — plain text, no subject needed
        return send_email(to=sms_email, subject="", body=body)
    except Exception as e:
        print(f"[SMS-GW ERROR] To: {sms_email} | Error: {e}")
        return False


def send_sms(to: str, body: str, carrier: str = "") -> bool:
    """Send SMS via Twilio if configured, otherwise fall back to email gateway."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_FROM_NUMBER")

    # Try Twilio first
    if all([sid, token, from_num]):
        try:
            from twilio.rest import Client

            msg = Client(sid, token).messages.create(body=body, from_=from_num, to=to)
            print(f"[SMS SENT] To: {to} | SID: {msg.sid} | Status: {msg.status}")
            return True
        except Exception as e:
            print(f"[SMS ERROR] Twilio failed: {e}")

    # Fall back to email-to-SMS gateway
    if carrier:
        print(f"[SMS] Falling back to email gateway (carrier={carrier})")
        return send_sms_via_email(to, body, carrier)

    print(f"[SMS SKIP] No Twilio and no carrier specified. To: {to}")
    return False
