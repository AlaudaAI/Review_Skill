# ReviewBoost

Help local businesses get more Google reviews. Send customers a personalized link that pre-fills a review and redirects them to Google Maps.

## How It Works

1. Merchant enters a Google Maps link + customer phone numbers
2. System generates an AI-written review and a short link
3. Customer receives SMS, clicks the link, copies the review, and posts it on Google

## Quick Start

```bash
# 1. Clone & install
git clone <repo-url> && cd Review_Skill
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in your API keys (see below)

# 3. Run
python main.py
```

The server starts at `http://localhost:8000`. In local mode it auto-creates an ngrok tunnel for SMS callbacks.

### Required Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (review text generation) |
| `GOOGLE_MAPS_API_KEY` | Google Places API key |
| `DATABASE_URL` | PostgreSQL connection string (defaults to SQLite locally) |
| `TWILIO_ACCOUNT_SID` | Twilio SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | Twilio sender number |
| `NGROK_AUTHTOKEN` | For local dev tunneling |

See `.env.example` for the full list including optional SMTP settings.

## Project Structure

```
.
├── main.py                  # FastAPI app entry point
├── database.py              # SQLAlchemy engine & session
├── models.py                # Business, ReviewRequest models
├── requirements.txt
├── vercel.json              # Vercel deployment config
├── api/
│   └── index.py             # Vercel serverless entry
├── routes/
│   ├── api.py               # JSON API endpoints
│   └── public.py            # Landing page & redirects
├── services/
│   ├── review.py            # AI review generation + short codes
│   ├── google_places.py     # Google Maps place resolution
│   └── sms.py               # Twilio / email-gateway SMS
├── static/
│   ├── style.css
│   ├── dashboard.html       # Merchant dashboard
│   └── send.html            # SMS send form
└── templates/
    ├── base.html
    ├── landing.html          # Customer-facing review page
    └── setup.html
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/businesses` | List all businesses |
| GET | `/api/resolve-place?url=` | Lookup Google place |
| POST | `/api/send` | Send review request SMS |
| GET | `/api/dashboard?business_id=` | Dashboard stats |
| GET | `/r/{code}` | Customer landing page |

## Deployment

Deployed on **Vercel** as a Python serverless function. Push to main and Vercel handles the rest. Set environment variables in the Vercel dashboard.
