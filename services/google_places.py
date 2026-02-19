import json
import logging
import os
import re
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def resolve_google_place(user_input: str) -> dict | None:
    """Resolve a Google Maps URL OR a business name to {name, place_id}."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    text = user_input.strip()

    if not text:
        return None

    is_url = text.startswith("http") or "google.com/maps" in text or "goo.gl/" in text

    if is_url:
        url = text if text.startswith("http") else "https://" + text
        full_url = _follow_redirects(url) or url
        logger.info("Redirected URL: %s", full_url)

        place_id = _extract_place_id(full_url)
        if place_id:
            name = _extract_name_from_url(full_url) or "Business"
            if api_key:
                api_name = _get_place_name(place_id, api_key)
                if api_name:
                    name = api_name
            return {"name": name, "place_id": place_id}

        query = _extract_name_from_url(full_url)
        coords = _extract_coords(full_url)
        logger.info("Extracted from URL — query: %s, coords: %s", query, coords)

        if api_key and query:
            result = _find_place_from_text(query, coords, api_key)
            if result:
                return result

        if api_key and coords and not query:
            result = _find_place_from_text(f"{coords[0]},{coords[1]}", coords, api_key)
            if result:
                return result
    else:
        logger.info("Searching by name: %s", text)
        if api_key:
            result = _find_place_from_text(text, None, api_key)
            if result:
                return result

    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY is not set!")
    return None


def _follow_redirects(url: str) -> str | None:
    try:
        import requests as req
    except ImportError:
        logger.error("'requests' not installed — run: pip install requests")
        return None

    ua_strategies = [
        ("bot", {"User-Agent": "facebookexternalhit/1.1"}),
        ("browser", {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }),
    ]

    for label, headers in ua_strategies:
        try:
            resp = req.get(url, allow_redirects=True, timeout=15, headers=headers)
            logger.info("%s UA — HTTP %s, final URL: %s", label, resp.status_code, resp.url)

            if "google.com/maps" in resp.url:
                return resp.url

            maps_url = _find_maps_url_in_html(resp.text[:200_000])
            if maps_url:
                logger.info("Found via %s UA: %s", label, maps_url)
                return maps_url
        except Exception as e:
            logger.warning("%s UA request failed: %s", label, e)

    return None


def _find_maps_url_in_html(body: str) -> str | None:
    patterns = [
        r'<meta[^>]+content="(https://(?:www\.)?google\.[a-z.]+/maps/[^"]+)"',
        r'<link[^>]+href="[^"]*?(https://(?:www\.)?google\.[a-z.]+/maps/[^"&]+)',
        r'(https://(?:www\.)?google\.[a-z.]+/maps/(?:place|search)/[^\s"\'<>\\]+)',
        r'(https://(?:www\.)?google\.[a-z.]+/maps/[^\s"\'<>\\]+)',
        r'(https%3A%2F%2F(?:www\.)?google\.\w+%2Fmaps%2F[^\s"\'<>]+)',
        r'<meta[^>]+content="\d+;\s*url=(https://[^"]+)"',
        r'window\.location(?:\.href\s*=\s*|\.replace\s*\(\s*|\.assign\s*\(\s*)["\']'
        r'(https://[^"\']+)',
        r'href="(https://[^"]*google\.[^"]*\/maps\/[^"]+)"',
    ]
    for pattern in patterns:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            found = m.group(1)
            if "%" in found:
                found = urllib.parse.unquote(found)
            return found
    return None


def _extract_place_id(url: str) -> str | None:
    m = re.search(r"place_id[=:]([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"!1s(ChIJ[A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def _extract_name_from_url(url: str) -> str | None:
    m = re.search(r"/maps/place/([^/@]+)", url)
    if m:
        return urllib.parse.unquote_plus(m.group(1)).replace("+", " ")
    m = re.search(r"/maps/search/([^/@]+)", url)
    if m:
        return urllib.parse.unquote_plus(m.group(1)).replace("+", " ")
    return None


def _extract_coords(url: str) -> tuple[float, float] | None:
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return None


def _find_place_from_text(
    query: str, coords: tuple | None, api_key: str
) -> dict | None:
    body_dict: dict = {"textQuery": query}
    if coords:
        body_dict["locationBias"] = {
            "circle": {
                "center": {"latitude": coords[0], "longitude": coords[1]},
                "radius": 500.0,
            }
        }
    try:
        body_bytes = json.dumps(body_dict).encode("utf-8")
        req = urllib.request.Request(
            "https://places.googleapis.com/v1/places:searchText",
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.id,places.displayName",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        places = data.get("places", [])
        logger.info("Places API response: %d results", len(places))
        if places:
            p = places[0]
            return {
                "name": p.get("displayName", {}).get("text", query),
                "place_id": p["id"],
            }
    except Exception as e:
        logger.error("Places API error: %s", e)
    return None


def _get_place_name(place_id: str, api_key: str) -> str | None:
    try:
        req = urllib.request.Request(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "displayName",
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data.get("displayName", {}).get("text")
    except Exception as e:
        logger.error("Place Details API error: %s", e)
    return None
