"""Public routes: short-link redirect with clipboard copy."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Business, ReviewRequest

router = APIRouter()


@router.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse("/portal/send")


@router.get("/r/{code}", response_class=HTMLResponse)
def review_landing(code: str, db: Session = Depends(get_db)):
    rr = db.query(ReviewRequest).filter(ReviewRequest.short_code == code).first()
    if not rr:
        return HTMLResponse("<h1>Link not found</h1>", status_code=404)

    if rr.status == "sent":
        rr.status = "clicked"
        rr.clicked_at = datetime.now(timezone.utc)
        db.commit()

    biz = db.query(Business).filter(Business.id == rr.business_id).first()
    review_url = f"https://search.google.com/local/writereview?placeid={biz.google_place_id}"
    review_text_json = json.dumps(rr.review_text)

    return HTMLResponse(f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Redirecting…</title>
<style>
  body {{ margin:0; display:flex; align-items:center; justify-content:center;
         min-height:100vh; font-family:system-ui,sans-serif; background:#fafafa; color:#333; }}
  .wrap {{ text-align:center; padding:2rem; }}
  .btn {{ display:inline-block; margin:.5rem; padding:.6rem 1.2rem; border:none;
          border-radius:.5rem; font-size:.9rem; cursor:pointer; text-decoration:none; }}
  .copy {{ background:#ffe17c; color:#171e19; }}
  .open {{ background:#171e19; color:#fff; }}
  .hidden {{ display:none; }}
</style>
</head>
<body>
<div class="wrap">
  <p id="status">Copying review &amp; redirecting to Google…</p>
  <div id="fallback" class="hidden">
    <button class="btn copy" onclick="doCopy()">Copy Review Text</button>
    <a class="btn open" href="{review_url}">Open Google Reviews</a>
  </div>
</div>
<script>
const reviewText = {review_text_json};
const reviewUrl = "{review_url}";
async function doCopy() {{
  try {{
    await navigator.clipboard.writeText(reviewText);
    document.querySelector('.copy').textContent = 'Copied!';
  }} catch(e) {{
    prompt('Copy this review:', reviewText);
  }}
}}
(async () => {{
  try {{
    await navigator.clipboard.writeText(reviewText);
    document.getElementById('status').textContent = 'Review copied! Redirecting…';
    setTimeout(() => {{ window.location.href = reviewUrl; }}, 1500);
  }} catch(e) {{
    document.getElementById('status').textContent = 'Tap Copy, then open Google Reviews.';
    document.getElementById('fallback').classList.remove('hidden');
  }}
}})();
</script>
</body>
</html>""")
