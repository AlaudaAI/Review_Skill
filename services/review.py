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
