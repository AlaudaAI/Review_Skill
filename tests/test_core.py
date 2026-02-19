from unittest.mock import patch

from models import Business, ReviewRequest


def test_generate_reviews(client, db):
    """POST /api/generate creates Business + ReviewRequest and returns review data."""
    with (
        patch("routes.api.resolve_google_place", return_value={"name": "Test Biz", "place_id": "place123"}),
        patch("routes.api.generate_review_text", return_value="Great place!"),
        patch("routes.api.generate_unique_short_code", return_value="tstcode"),
    ):
        resp = client.post("/api/generate", json={
            "google_link": "https://maps.google.com/test",
            "phones": ["1234567890"],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["business_name"] == "Test Biz"
    assert len(data["reviews"]) == 1
    assert data["reviews"][0]["review_text"] == "Great place!"
    assert "/r/tstcode" in data["reviews"][0]["link"]

    assert db.query(Business).count() == 1
    assert db.query(ReviewRequest).filter_by(short_code="tstcode").first() is not None


def test_short_link_click(client, db):
    """GET /r/{code} returns clipboard HTML and marks status as clicked."""
    biz = Business(name="Test Biz", google_place_id="place123")
    db.add(biz)
    db.commit()
    db.refresh(biz)

    rr = ReviewRequest(
        business_id=biz.id,
        customer_contact="1234567890",
        short_code="abc",
        review_text="Wonderful service!",
        status="sent",
    )
    db.add(rr)
    db.commit()

    resp = client.get("/r/abc")
    assert resp.status_code == 200
    assert "Wonderful service!" in resp.text
    assert "place123" in resp.text

    db.refresh(rr)
    assert rr.status == "clicked"
    assert rr.clicked_at is not None
