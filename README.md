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

# 3. Run (choose an SMS backend)
python main.py --sms-backend twilio   # or: --sms-backend email
```

The server starts at `http://localhost:8000`. In local mode it auto-creates an ngrok tunnel for SMS callbacks.

### Required Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (review text generation) |
| `GOOGLE_MAPS_API_KEY` | Google Places API key |
| `DATABASE_URL` | PostgreSQL connection string (defaults to SQLite locally) |
| `SMS_BACKEND` | `twilio` or `email` (set via CLI locally, env var on Vercel) |
| `TWILIO_ACCOUNT_SID` | Twilio SID (required when `SMS_BACKEND=twilio`) |
| `TWILIO_AUTH_TOKEN` | Twilio auth token (required when `SMS_BACKEND=twilio`) |
| `TWILIO_FROM_NUMBER` | Twilio sender number (required when `SMS_BACKEND=twilio`) |
| `NGROK_AUTHTOKEN` | For local dev tunneling (optional) |

See `.env.example` for the full list including optional SMTP settings for the `email` backend.

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
│   └── public.py            # Short-link redirect & clipboard copy
├── services/
│   ├── review.py            # AI review generation + short codes
│   ├── google_places.py     # Google Maps place resolution
│   └── sms.py               # Twilio / email-gateway SMS
└── static/
    ├── style.css
    ├── dashboard.html       # Merchant dashboard
    └── send.html            # SMS send form
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/businesses` | List all businesses |
| GET | `/api/resolve-place?url=` | Lookup Google place |
| POST | `/api/generate` | Resolve business + generate review texts |
| POST | `/api/send` | Send previously generated review SMS |
| DELETE | `/api/review/{id}` | Delete a review request |
| GET | `/api/dashboard?business_id=` | Dashboard stats |
| GET | `/api/sms-diagnose` | Diagnose SMS backend config |
| POST | `/api/sms-test` | Send a test SMS |
| GET | `/r/{code}` | Clipboard copy & redirect to Google |

### Portal Pages

| Path | Description |
|---|---|
| `/portal/send` | SMS send form |
| `/portal/dashboard` | Merchant dashboard |
| `/` | Redirects to `/portal/send` |

## Deployment

Deployed on **Vercel** as a Python serverless function (`api/index.py` serves as the entry point). Push to main and Vercel handles the rest. Set environment variables (including `SMS_BACKEND`) in the Vercel dashboard.
