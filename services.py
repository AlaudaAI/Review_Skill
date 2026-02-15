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


def send_sms(to: str, body: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_FROM_NUMBER")
    if not all([sid, token, from_num]):
        print(f"[SMS SKIP] Twilio not configured. To: {to} | Body: {body}")
        return False
    from twilio.rest import Client

    Client(sid, token).messages.create(body=body, from_=from_num, to=to)
    return True
