import json
import os
import re
import secrets
import smtplib
import string
import urllib.parse
import urllib.request
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


# ── Google Place Resolution ──────────────────────────────────────────────────


def resolve_google_place(google_url: str) -> dict | None:
    """Resolve a Google Maps URL to {name, place_id}. Uses GOOGLE_API_KEY."""
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()

    # Ensure URL has a scheme
    url = google_url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    # Step 1: Follow redirects to get full URL (handles goo.gl short links)
    full_url = _follow_redirects(url) or url

    # Step 2: Try to extract place_id directly from URL
    place_id = _extract_place_id(full_url)
    if place_id:
        name = _extract_name_from_url(full_url) or "Business"
        if api_key:
            api_name = _get_place_name(place_id, api_key)
            if api_name:
                name = api_name
        return {"name": name, "place_id": place_id}

    # Step 3: Extract name/query from URL, use Places API to find place_id
    query = _extract_name_from_url(full_url)
    coords = _extract_coords(full_url)

    if api_key and query:
        result = _find_place_from_text(query, coords, api_key)
        if result:
            return result

    # Step 4: If we have coords but no name, try reverse geocode style search
    if api_key and coords and not query:
        result = _find_place_from_text(f"{coords[0]},{coords[1]}", coords, api_key)
        if result:
            return result

    return None


def _follow_redirects(url: str) -> str | None:
    """Follow HTTP redirects and return the final Google Maps URL.

    Google short links (maps.app.goo.gl) sometimes return a 200 HTML page
    with a JavaScript/meta-refresh redirect instead of a proper HTTP 302,
    so we parse the HTML body as a fallback.
    """
    import http.client
    import ssl

    max_redirects = 10
    current_url = url

    for _ in range(max_redirects):
        try:
            parsed = urllib.parse.urlparse(current_url)

            if parsed.scheme == "https":
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection(parsed.hostname, timeout=10, context=ctx)
            else:
                conn = http.client.HTTPConnection(parsed.hostname, timeout=10)

            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query

            conn.request("GET", path, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            })
            resp = conn.getresponse()

            # ── Proper HTTP redirect ──
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.getheader("Location")
                conn.close()
                if not location:
                    return current_url
                if location.startswith("/"):
                    location = f"{parsed.scheme}://{parsed.hostname}{location}"
                current_url = location
                continue

            # ── 200 OK ──
            if resp.status == 200:
                # Already on a Maps URL? Done.
                if "/maps/place/" in current_url or "/maps/search/" in current_url:
                    conn.close()
                    return current_url

                # Parse HTML body for embedded redirect
                body = resp.read(100_000).decode("utf-8", errors="ignore")
                conn.close()

                # 1) Full Maps URL anywhere in the page
                m = re.search(
                    r'(https://www\.google\.[a-z.]+/maps/place/[^\s"\'<>\\]+)', body
                )
                if m:
                    return urllib.parse.unquote(m.group(1))

                # 2) <meta http-equiv="refresh" content="0;url=...">
                m = re.search(
                    r'<meta[^>]+content="\d+;\s*url=(https://[^"]+)"', body, re.IGNORECASE
                )
                if m:
                    current_url = m.group(1)
                    continue

                # 3) window.location = "..."
                m = re.search(
                    r'window\.location\s*[=.]\s*["\']?(https://[^\s"\'<>]+)', body
                )
                if m:
                    current_url = m.group(1)
                    continue

                # 4) Generic <a href="https://...google.../maps/...">
                m = re.search(
                    r'href="(https://[^"]*google\.[^"]*\/maps\/[^"]+)"', body
                )
                if m:
                    return urllib.parse.unquote(m.group(1))

                return current_url

            conn.close()
            return current_url

        except Exception as e:
            print(f"[RESOLVE] Redirect step failed for {current_url}: {e}")
            return current_url if current_url != url else None

    return current_url


def _extract_place_id(url: str) -> str | None:
    """Try to extract a Place ID directly from the URL."""
    # Pattern: place_id=... or place_id:...
    m = re.search(r"place_id[=:]([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    # Pattern in data param: !1sChIJ... (place IDs start with ChIJ)
    m = re.search(r"!1s(ChIJ[A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def _extract_name_from_url(url: str) -> str | None:
    """Extract business name or search query from Google Maps URL path."""
    # /maps/place/BUSINESS_NAME/...
    m = re.search(r"/maps/place/([^/@]+)", url)
    if m:
        return urllib.parse.unquote_plus(m.group(1)).replace("+", " ")
    # /maps/search/QUERY/...
    m = re.search(r"/maps/search/([^/@]+)", url)
    if m:
        return urllib.parse.unquote_plus(m.group(1)).replace("+", " ")
    return None


def _extract_coords(url: str) -> tuple[float, float] | None:
    """Extract lat/lng from a Google Maps URL."""
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return None


def _find_place_from_text(
    query: str, coords: tuple | None, api_key: str
) -> dict | None:
    """Use Google Places 'Find Place from Text' API."""
    params: dict = {
        "input": query,
        "inputtype": "textquery",
        "fields": "place_id,name",
        "key": api_key,
    }
    if coords:
        params["locationbias"] = f"point:{coords[0]},{coords[1]}"
    try:
        qs = urllib.parse.urlencode(params)
        url = f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json?{qs}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        if data.get("candidates"):
            c = data["candidates"][0]
            return {"name": c.get("name", query), "place_id": c["place_id"]}
    except Exception as e:
        print(f"[RESOLVE] Places API error: {e}")
    return None


def _get_place_name(place_id: str, api_key: str) -> str | None:
    """Get place name from Place ID via Place Details API."""
    params = {"place_id": place_id, "fields": "name", "key": api_key}
    try:
        qs = urllib.parse.urlencode(params)
        url = f"https://maps.googleapis.com/maps/api/place/details/json?{qs}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data.get("result", {}).get("name")
    except Exception as e:
        print(f"[RESOLVE] Place Details API error: {e}")
    return None


# ── SMS Sending ──────────────────────────────────────────────────────────────

SMS_GATEWAYS = {
    "tmobile": "tmomail.net",
    "att": "txt.att.net",
    "verizon": "vtext.com",
    "sprint": "messaging.sprintpcs.com",
}


def _send_email_internal(to: str, subject: str, body: str) -> bool:
    """Internal helper: send email via SMTP (used by SMS gateway fallback)."""
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
    """Send SMS through carrier email-to-SMS gateway."""
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
    """Send SMS via Twilio if configured, otherwise fall back to email gateway."""
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
