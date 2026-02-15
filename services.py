import os
import secrets
import string

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
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        print(f"[EMAIL MOCK] To: {to} | Subject: {subject} | Body: {body}")
        return True
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    msg = Mail(
        from_email=os.getenv("FROM_EMAIL", "reviews@example.com"),
        to_emails=to,
        subject=subject,
        html_content=body,
    )
    SendGridAPIClient(api_key).send(msg)
    return True


def send_sms(to: str, body: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_FROM_NUMBER")
    if not all([sid, token, from_num]):
        print(f"[SMS MOCK] To: {to} | Body: {body}")
        return True
    from twilio.rest import Client

    Client(sid, token).messages.create(body=body, from_=from_num, to=to)
    return True
