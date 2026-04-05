# medbot-backend
# Dawa — Kenya Medical Assistant (Backend)

> Django + PostgreSQL RAG-powered medical chatbot API.
> Deployed on **Render**. Paired with a static HTML/JS frontend on **Vercel**.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [API Reference](#3-api-reference)
4. [File Structure](#4-file-structure)
5. [How It Works](#5-how-it-works)
6. [Local Development](#6-local-development)
7. [Deploying to Render](#7-deploying-to-render)
8. [Environment Variables](#8-environment-variables)
9. [Database](#9-database)
10. [Running Tests](#10-running-tests)
11. [Admin Panel](#11-admin-panel)
12. [Bugs Fixed](#12-bugs-fixed)
13. [Tech Stack](#13-tech-stack)

---

## 1. Project Overview

Dawa is a Kenyan medical assistant chatbot. Users describe their symptoms in plain English or Swahili and receive first-aid guidance for 50+ diseases common in Kenya. If an emergency keyword is detected (e.g. "snake bite", "unconscious", "not breathing"), the system requests the user's GPS location and finds nearby hospitals via OpenStreetMap.

**What the backend does:**

- Extracts symptoms from free-form text using spaCy NLP
- Detects emergency keywords and returns structured emergency responses
- Retrieves the most relevant disease and first-aid procedure using TF-IDF cosine similarity (RAG)
- Queries the OpenStreetMap Overpass API for nearby hospitals when an emergency is triggered
- Stores chat sessions, symptom logs, emergency logs, and feedback in PostgreSQL
- Serves all data as JSON — no HTML templates

---

## 2. Architecture

```
Frontend (Vercel)                Backend (Render)               Database (Render)
─────────────────                ────────────────               ─────────────────
index.html                       Django 4.2                     PostgreSQL
  │                                │                              │
  │  POST /api/chat/               │                              │
  ├────────────────────────────►   │  MedicalNLPProcessor         │
  │                                │    extract_symptoms()        │
  │                                │    detect_emergency()        │
  │                                │         │                    │
  │                                │  RAGRetriever                │
  │                                │    retrieve_first_aid()  ◄───┤ Disease
  │                                │    TF-IDF cosine sim         │ FirstAidProcedure
  │  { type, message, symptoms }   │         │                    │
  │◄────────────────────────────   │  JsonResponse                │
  │                                │                              │
  │  POST /api/hospitals/          │                              │
  ├────────────────────────────►   │  Overpass API (OSM)          │
  │                                │    nearby hospitals      ◄───┤ EmergencyLog
  │  { hospitals[], user_location} │                              │
  │◄────────────────────────────   │                              │
  │                                │                              │
  │  POST /api/feedback/           │                              │
  ├────────────────────────────►   │                          ────┤ FirstAidFeedback
  │  { status, feedback_id }       │                              │
  │◄────────────────────────────   │                              │
```

---

## 3. API Reference

All endpoints accept and return `application/json`. No authentication required. The client generates and persists a `session_id` UUID in `localStorage`.

---

### `GET /api/health/`

Health check used by Render to verify the service is running.

**Response**
```json
{ "status": "ok" }
```

---

### `POST /api/chat/`

Process a user symptom message through NLP and RAG retrieval.

**Request body**
```json
{
  "message": "I have fever, headache and body aches",
  "session_id": "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | ✅ | Free-form symptom description (max 5000 chars) |
| `session_id` | string | ✅ | Client-generated UUID, persisted in localStorage |

**Normal response** — symptom matched
```json
{
  "type": "normal",
  "message": "**Based on your symptoms, you may have Malaria**\n\n**First Aid Steps:**\n...",
  "symptoms_detected": ["fever", "headache", "muscle_pain"],
  "session_id": "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
}
```

**Emergency response** — emergency keyword detected
```json
{
  "type": "emergency",
  "severity": "CRITICAL",
  "message": "🚨 SNAKE BITE — Medical Emergency...",
  "emergencies": [
    { "keyword": "snake bite", "severity": "CRITICAL", "message": "..." }
  ],
  "action": "request_location",
  "emergency_id": 42,
  "session_id": "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
}
```

**Error response**
```json
{ "type": "error", "message": "Message cannot be empty." }
```

| HTTP status | Meaning |
|---|---|
| 200 | Success (normal or emergency) |
| 400 | Missing/invalid fields |
| 429 | Rate limited (1 request/second per session) |
| 500 | Server error |

---

### `POST /api/hospitals/`

Query OpenStreetMap for hospitals and clinics near the user's GPS location. Called automatically by the frontend after an emergency response.

**Request body**
```json
{
  "latitude": -0.7192,
  "longitude": 37.1605,
  "session_id": "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx",
  "emergency_id": 42
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `latitude` | float | ✅ | User's GPS latitude |
| `longitude` | float | ✅ | User's GPS longitude |
| `session_id` | string | ✅ | Same UUID used in /api/chat/ |
| `emergency_id` | int | ❌ | From emergency response — links location to the log |

**Response**
```json
{
  "hospitals": [
    {
      "name": "Murang'a County Referral Hospital",
      "lat": -0.7180,
      "lon": 37.1520,
      "address": "Hospital Road, Murang'a",
      "phone": "+254 60 2030200",
      "distance": 0.87
    }
  ],
  "user_location": { "lat": -0.7192, "lng": 37.1605 }
}
```

Searches within a 5 km radius. Returns up to 10 deduplicated results sorted by distance (km).

| HTTP status | Meaning |
|---|---|
| 200 | Success |
| 400 | Missing or invalid coordinates |
| 503 | Overpass API timed out or unavailable |

---

### `POST /api/feedback/`

Record a star rating and optional comment after a diagnosis.

**Request body**
```json
{
  "session_id": "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx",
  "disease": "Malaria",
  "rating": 5,
  "feedback": "Very helpful, thank you!"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | ✅ | Same UUID used throughout the session |
| `disease` | string | ❌ | Disease name extracted from the response |
| `rating` | int | ✅ | 1–5 star rating |
| `feedback` | string | ❌ | Free-text comment (max 5000 chars) |

**Response**
```json
{ "status": "success", "feedback_id": 17 }
```

| HTTP status | Meaning |
|---|---|
| 200 | Feedback saved |
| 400 | Missing session_id or invalid rating |
| 500 | Server error |

---

## 4. File Structure

```
medbot-backend/
│
├── .env.example                  ← copy to .env for local dev (never commit .env)
├── .gitignore
├── manage.py                     ← Django CLI entry point
├── requirements.txt              ← pinned Python dependencies
├── render.yaml                   ← Render deploy config (build + start commands)
│
├── static/
│   └── .gitkeep                  ← empty placeholder so Git tracks the folder
│
├── medical_chatbot/              ← Django PROJECT package
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py               ← all config: DB, CORS, cache, security, logging
│   ├── urls.py                   ← root router → hands /api/ to chatbot.urls
│   └── wsgi.py
│
└── chatbot/                      ← Django APP package
    ├── __init__.py
    ├── admin.py                  ← Django admin registrations for all models
    ├── analytics.py              ← daily analytics aggregation helper
    ├── apps.py                   ← AppConfig
    ├── models.py                 ← all ORM models (see Database section)
    ├── nlp_processor.py          ← symptom extraction + emergency detection
    ├── rag_retriever.py          ← TF-IDF cosine similarity retrieval
    ├── tests.py                  ← smoke tests for all 4 endpoints
    ├── urls.py                   ← app-level URL patterns
    ├── views.py                  ← health_check, process_message,
    │                                get_nearby_hospitals, submit_feedback
    │
    ├── migrations/
    │   ├── __init__.py
    │   └── 0001_initial.py       ← auto-generated schema migration
    │
    └── management/
        ├── __init__.py
        └── commands/
            ├── __init__.py
            └── populate_kenya_data.py  ← seeds 50+ diseases, symptoms,
                                           first-aid procedures, emergency keywords
```

---

## 5. How It Works

### Symptom Extraction — Two-Pass NLP

**Pass 1 — Database symptom records**

Every `Symptom` row has a `name` and `alternative_names` (comma-separated variations). The processor checks if any of these appear in the lowercased, punctuation-stripped user input.

**Pass 2 — Hardcoded Kenyan/Swahili dictionary**

A built-in dictionary maps canonical symptom keys to a list of text patterns including Swahili terms:

```python
"fever": ["fever", "joto", "homa", "hot body", "high temperature", ...]
"diarrhea": ["diarrhea", "kuhara", "running stomach", "watery stool", ...]
```

Results from both passes are deduplicated and returned as a list.

---

### Emergency Detection

The `EmergencyKeyword` table is checked against the user message. If any keyword matches, the system returns an `emergency` type response immediately — skipping RAG entirely — and sets `action: "request_location"` to trigger the GPS flow in the frontend.

Emergency severity levels: `CRITICAL` → `URGENT` → `CAUTION`

Covered emergencies include: unconscious person, snake bite, severe bleeding, heart attack, stroke, eclampsia, postpartum haemorrhage, choking, drowning, poisoning, cerebral malaria, seizures, burns, fainting.

---

### RAG Retrieval — TF-IDF Cosine Similarity

1. A query string is built: `extracted_symptoms + raw_user_input`
2. All disease records are scored against the query using `TfidfVectorizer` with bigrams (`ngram_range=(1,2)`)
3. Diseases with a cosine similarity score above `0.04` are returned, ranked highest first
4. If TF-IDF returns nothing, a keyword substring fallback scores diseases by how many symptom strings appear in their `search_text` field
5. The top 3 matches are returned with their attached `FirstAidProcedure`

The full disease corpus is cached in `DatabaseCache` for 1 hour. Per-query results are cached for 5 minutes. All cached data is stored as plain Python dicts (not ORM objects) to avoid unpickling errors across workers.

---

### Hospitals — OpenStreetMap Overpass API

When the frontend sends GPS coordinates after an emergency:

1. An Overpass QL query searches for `hospital`, `clinic`, `health_post`, and `healthcare` nodes and ways within 5 km
2. `way` elements use their `center` coordinates
3. Haversine formula calculates distance in km
4. Results are deduplicated by name + approximate coordinates
5. Top 10 sorted by distance are returned

---

## 6. Local Development

### Prerequisites

- Python 3.11
- PostgreSQL running locally
- Git

### Setup

```bash
# Clone the repo
git clone https://github.com/your-username/medbot-backend.git
cd medbot-backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Download NLP models
python -m spacy download en_core_web_sm
python -m nltk.downloader -d /tmp/nltk_data punkt punkt_tab stopwords wordnet
```

### Configure environment

```bash
# Copy the example file — then edit it with your Postgres credentials
cp .env.example .env
```

Open `.env` and update:
```
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(50))">
DB_NAME=medical_chatbot
DB_USER=postgres
DB_PASSWORD=yourpassword
```

### Set up the database

```bash
# Create the Postgres database
createdb medical_chatbot

# Run migrations
python manage.py migrate

# Create the cache table
python manage.py createcachetable

# Seed diseases, symptoms, first-aid procedures, and emergency keywords
python manage.py populate_kenya_data
```

### Run the development server

```bash
python manage.py runserver
# API available at http://localhost:8000/api/
```

Point the frontend `API_BASE` to `http://localhost:8000/api` for local testing.

### Re-seed the database

If you want to reset and repopulate all medical data:

```bash
python manage.py populate_kenya_data --force
```

---

## 7. Deploying to Render

### Step 1 — Create the PostgreSQL database

Render Dashboard → **New** → **PostgreSQL**

| Field | Value |
|---|---|
| Name | `medbot-db` |
| Database | `medbot` |
| User | `medbot_user` |
| Region | Oregon |
| Plan | Free |

### Step 2 — Create the Web Service

Render Dashboard → **New** → **Web Service** → connect your GitHub repo

| Field | Value |
|---|---|
| Name | `medbot-api` |
| Runtime | Python 3 |
| Region | Oregon (must match DB) |
| Branch | `main` |

`render.yaml` is read automatically — no manual build/start command needed.

### Step 3 — Link the database

Web Service → **Environment** → **Linked Services** → **Add Database** → select `medbot-db`

This injects `DATABASE_URL` automatically.

### Step 4 — Set environment variables

Web Service → **Environment** → **Add Environment Variable**

| Key | Value |
|---|---|
| `SECRET_KEY` | Click **Generate** |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `medbot-api.onrender.com` |
| `CORS_ALLOWED_ORIGINS` | `https://your-frontend.vercel.app` |
| `NLTK_DATA` | `/tmp/nltk_data` |

### Step 5 — Deploy

Push to `main`. Render runs the full build command:

```bash
pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m nltk.downloader -d /tmp/nltk_data punkt punkt_tab stopwords wordnet
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py populate_kenya_data --force
```

Once the health check at `/api/health/` returns `{"status":"ok"}` the service is live.

### Step 6 — Update the frontend

In `index.html` update:
```js
const API_BASE = 'https://medbot-api.onrender.com/api';
```

---

## 8. Environment Variables

| Variable | Required | Description | Example |
|---|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key — 50+ random chars | `abc123...` |
| `DEBUG` | ✅ | `True` locally, `False` on Render | `False` |
| `ALLOWED_HOSTS` | ✅ | Comma-separated, no spaces | `medbot-api.onrender.com` |
| `DATABASE_URL` | ✅ on Render | Full Postgres connection string — injected automatically by Render | `postgresql://user:pass@host/db` |
| `DB_NAME` | Local only | Database name when `DATABASE_URL` not set | `medical_chatbot` |
| `DB_USER` | Local only | Database user | `postgres` |
| `DB_PASSWORD` | Local only | Database password | `yourpassword` |
| `DB_HOST` | Local only | Database host | `localhost` |
| `DB_PORT` | Local only | Database port | `5432` |
| `CORS_ALLOWED_ORIGINS` | ✅ | Comma-separated frontend URLs | `https://medbot.vercel.app` |
| `NLTK_DATA` | ✅ | Writable directory for NLTK corpora | `/tmp/nltk_data` |

> **Never put real values in `.env.example` or commit a `.env` file.**
> On Render, set everything in the dashboard. No `.env` file is needed in the repo.

---

## 9. Database

### Models

| Model | Purpose |
|---|---|
| `Disease` | Disease records with name, description, and common symptoms |
| `Symptom` | Individual symptoms with Swahili/English alternative names |
| `FirstAidProcedure` | Step-by-step first aid linked to a Disease |
| `EmergencyKeyword` | Keywords that trigger emergency responses |
| `UserProfile` | Per-session user record (no login required) |
| `ChatSession` | One conversation per session_id |
| `ChatMessage` | Individual messages within a session |
| `SymptomLog` | Extracted symptoms and matched diseases per request |
| `EmergencyLog` | Emergency detections with optional GPS location |
| `FirstAidFeedback` | Star ratings and comments |
| `ChatAnalytics` | Daily aggregated metrics |

### Seeded data (via `populate_kenya_data`)

- **50+ diseases** across: mosquito-borne, waterborne, respiratory, parasitic, STIs, skin, NCDs, eye/ENT, maternal, malnutrition
- **45 symptom types** with Swahili/English variations
- **24 first-aid procedures** with step-by-step instructions, warnings, and when-to-seek-help guidance
- **21 emergency keywords** covering CRITICAL and URGENT scenarios

### Cache table

The `DatabaseCache` backend stores NLP symptom lookups, RAG disease corpus, and per-query results. The table is created during deployment:

```bash
python manage.py createcachetable
```

---

## 10. Running Tests

```bash
python manage.py test chatbot
```

Tests cover:

| Test | What it checks |
|---|---|
| `HealthCheckTest` | `GET /api/health/` returns `{"status":"ok"}` |
| `ChatEndpointTest` | Missing message → 400, missing session_id → 400, empty message → 400, valid message → 200 |
| `HospitalEndpointTest` | Missing coords → 400, invalid coords → 400, out-of-range coords → 400 |
| `FeedbackEndpointTest` | Missing session_id → 400, invalid rating → 400, valid feedback → 200 |

---

## 11. Admin Panel

Create a superuser then visit `/admin/`:

```bash
python manage.py createsuperuser
```

The admin panel gives full CRUD access to all models including diseases, symptoms, first-aid procedures, emergency keywords, chat sessions, feedback, and analytics.

---

## 12. Bugs Fixed

| # | File | Bug | Fix |
|---|---|---|---|
| 1 | `settings.py` | `SECURE_SSL_REDIRECT = True` caused infinite redirect loop on Render (Render terminates TLS at proxy) | Set to `False`, kept `SECURE_PROXY_SSL_HEADER` |
| 2 | `settings.py` | `STATICFILES_DIRS = [./static/]` crashed `collectstatic` when dir didn't exist | Guarded with `os.path.isdir()` |
| 3 | `settings.py` | `STATICFILES_STORAGE` string deprecated in Django 4.2 | Replaced with `STORAGES` dict |
| 4 | `settings.py` | `ALLOWED_HOSTS` split didn't strip whitespace | Added `.strip()` |
| 5 | `rag_retriever.py` | `RAGRetriever \| None` is Python 3.10+ only syntax | Changed to `Optional[RAGRetriever]` |
| 6 | `rag_retriever.py` | ORM objects stored in `DatabaseCache` raised `OperationalError` on unpickle | Converted all cached data to plain dicts before `cache.set()` |
| 7 | `nlp_processor.py` | `nltk.download()` wrote to read-only home dir on Render | Added `NLTK_DATA=/tmp/nltk_data` env var + explicit `download_dir` param |
| 8 | `requirements.txt` | `Django==4.2.0` had known CVEs | Updated to `4.2.16` |
| 9 | `requirements.txt` | spaCy version drift between `3.7.0` and `3.7.4` | Pinned consistently to `3.7.4` |
| 10 | `render.yaml` | `migrate` without `--noinput` hung waiting for stdin | Added `--noinput` |
| 11 | `render.yaml` | Gunicorn sync workers blocked for 10s during Overpass API calls | Added `--worker-class gthread --threads 4` |
| 12 | `render.yaml` | Outdated pip caused wheel build failures | Added `pip install --upgrade pip` as first build step |
| 13 | `populate_kenya_data.py` | Disease loop used fragile `diseases_raw[key]` back-reference | Rewritten as clean `for key, (name, desc, syms) in DISEASE_DATA.items()` |

---

## 13. Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 4.2 |
| Database | PostgreSQL (Render managed) |
| Cache | Django DatabaseCache (no Redis needed) |
| NLP | spaCy `en_core_web_sm` + NLTK |
| Retrieval | scikit-learn TF-IDF cosine similarity |
| Hospital data | OpenStreetMap Overpass API |
| Static files | WhiteNoise |
| WSGI server | Gunicorn (gthread workers) |
| Hosting | Render (free tier
