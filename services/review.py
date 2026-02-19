import secrets
import string

import anthropic
from sqlalchemy.orm import Session


def generate_short_code(length: int = 7) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_unique_short_code(db: Session, max_retries: int = 5) -> str:
    """Generate a short code guaranteed unique in the DB. Retries on collision."""
    from models import ReviewRequest

    for attempt in range(max_retries):
        code = generate_short_code()
        exists = db.query(ReviewRequest.id).filter(
            ReviewRequest.short_code == code
        ).first()
        if not exists:
            return code
    raise RuntimeError(f"Failed to generate unique short code after {max_retries} attempts")


def generate_review_text(business_name: str, timeout: float = 30.0) -> str:
    """Generate AI review text. Raises on API failure or empty response."""
    client = anthropic.Anthropic(timeout=timeout)
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
    text = message.content[0].text.strip()
    if not text:
        raise ValueError("AI returned empty review text")
    return text
