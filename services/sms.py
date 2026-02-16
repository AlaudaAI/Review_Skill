import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMS_GATEWAYS = {
    "tmobile": "tmomail.net",
    "att": "txt.att.net",
    "verizon": "vtext.com",
    "sprint": "messaging.sprintpcs.com",
}


def _send_email_internal(to: str, subject: str, body: str) -> bool:
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    if not smtp_user or not smtp_pass:
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
    return True


def _send_sms_via_email(to: str, body: str, carrier: str) -> bool:
    gateway = SMS_GATEWAYS.get(carrier)
    if not gateway:
        print(f"[SMS-GW SKIP] Unknown carrier: {carrier}")
        return False

    digits = "".join(c for c in to if c.isdigit())
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        print(f"[SMS-GW ERROR] Invalid US phone number: {to}")
        return False

    sms_email = f"{digits}@{gateway}"
    try:
        return _send_email_internal(to=sms_email, subject="", body=body)
    except Exception as e:
        print(f"[SMS-GW ERROR] {e}")
        return False


def send_sms(to: str, body: str, carrier: str = "") -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_FROM_NUMBER")

    if all([sid, token, from_num]):
        try:
            from twilio.rest import Client

            msg = Client(sid, token).messages.create(body=body, from_=from_num, to=to)
            print(f"[SMS SENT] To: {to} | SID: {msg.sid}")
            return True
        except Exception as e:
            print(f"[SMS ERROR] Twilio failed: {e}")

    if carrier:
        print(f"[SMS] Falling back to email gateway (carrier={carrier})")
        return _send_sms_via_email(to, body, carrier)

    print(f"[SMS SKIP] No Twilio and no carrier specified. To: {to}")
    return False
