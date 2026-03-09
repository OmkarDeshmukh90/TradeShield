# TradeShield AI

> **India-first supply chain disruption intelligence platform for enterprise importers.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

TradeShield AI continuously monitors global disruption signals—tariffs, port congestion, geopolitical events, and natural disasters—and translates them into scored risk assessments, AI-generated playbooks, and real-time alerts for enterprise supply-chain teams.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development (SQLite)](#local-development-sqlite)
- [Configuration Reference](#configuration-reference)
- [API Reference](#api-reference)
- [Demo Mode](#demo-mode)
- [Testing](#testing)
- [Deployment](#deployment)
  - [Docker (Local / Staging)](#docker-local--staging)
  - [Free Cloud Deployment (Render + Cloudflare Pages)](#free-cloud-deployment-render--cloudflare-pages)
  - [24/7 Production Deployment (Render Blueprint)](#247-production-deployment-render-blueprint)
- [Database & Migrations](#database--migrations)
- [Worker Model](#worker-model)
- [Security](#security)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

TradeShield AI gives import-heavy enterprises a real-time view of supply chain exposure. It ingests signals from public and commercial data sources, maps them to each workspace's supplier network, and produces prioritised risk scores with explainable factor breakdowns. Analysts can approve AI-generated response playbooks, track incident outcomes, and receive alerts via dashboard, email, or WhatsApp.

---

## Key Features

| Feature | Description |
|---|---|
| 🔐 **Multi-tenant Auth & RBAC** | Workspace isolation, role-based access, and full audit trails |
| 📡 **Automated Ingestion** | Worker-based connectors (GDELT, USGS, UKMTO, OpenSky, NewsAPI, Spire) with backoff and source-health tracking |
| 🗺️ **Supply Map** | CSV-importable supplier network with versioning |
| 📊 **Risk Scoring** | Exposure scoring with explainability factor breakdown and analyst override deltas |
| 📋 **Playbook Automation** | AI-generated response playbooks with approval, comment, and outcome workflows |
| 🔔 **Alert Delivery** | Queued, retried alert delivery via dashboard, SMTP email, and Twilio WhatsApp |
| 🖥️ **Operations Dashboard** | `/ops` page for ingestion runs, source health, metrics, and queue management |
| 🎭 **Demo Mode** | Deterministic fixture replay for showcasing without external dependencies |
| 🐳 **Docker Ready** | Single `docker compose up --build` for the full stack |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Browser                          │
│              Dashboard (/)  ·  Ops (/ops)                   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────────┐
│               FastAPI App  (uvicorn app.main:app)            │
│   Auth · Tenant APIs · Explainability · Static Pages        │
└────────────────────────┬────────────────────────────────────┘
                         │ SQLModel / Alembic
┌────────────────────────▼────────────────────────────────────┐
│              Database  (SQLite dev · PostgreSQL prod)        │
│  Workspaces · Events · Exposures · Playbooks · Audit Logs   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│             Worker  (python -m app.worker)                   │
│   Ingestion cycle · Dedupe · Alert queue · Dispatch         │
└─────────────────────────────────────────────────────────────┘
```

**Flow:**
1. **Ingestion** — Worker fetches external events, normalises, dedupes, and upserts into the database.
2. **Scoring** — Exposures are mapped against the workspace supply map; impact assessments and playbooks are computed (and recomputed on change).
3. **Decision Loop** — Analysts approve playbooks, add comments, and record incident outcomes.
4. **Alerts** — Queued deliveries are dispatched with retry semantics via the configured channel.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.116 |
| **ORM / Schema** | [SQLModel](https://sqlmodel.tiangolo.com/) + [Alembic](https://alembic.sqlalchemy.org/) |
| **Runtime** | Python 3.11+ / [Uvicorn](https://www.uvicorn.org/) |
| **Database** | SQLite (dev) · PostgreSQL 16 (prod) |
| **HTTP Client** | [HTTPX](https://www.python-httpx.org/) |
| **Validation** | [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| **Alerts** | SMTP · Twilio WhatsApp |
| **Containerisation** | Docker · Docker Compose |
| **Cloud Deploy** | Render · Cloudflare Pages |
| **Testing** | [pytest](https://pytest.org/) |

---

## Getting Started

### Prerequisites

- Python 3.11 or higher
- `pip`
- Docker & Docker Compose *(optional, for containerised setup)*

### Local Development (SQLite)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/OmkarDeshmukh90/TradeShield.git
   cd TradeShield
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # macOS / Linux
   .venv\Scripts\activate           # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   For quick SQLite development, the defaults in `.env.example` work out of the box:
   ```env
   APP_ENV=dev
   DATABASE_URL=sqlite:///./tradeshield.db
   AUTO_CREATE_SCHEMA=true
   ```

5. **Start the web app:**
   ```bash
   uvicorn app.main:app --reload
   ```

6. **Start the worker** *(in a second terminal):*
   ```bash
   python -m app.worker
   ```

7. **Open your browser:**

   | URL | Description |
   |---|---|
   | `http://127.0.0.1:8000/` | Main dashboard |
   | `http://127.0.0.1:8000/ops` | Operations page |
   | `http://127.0.0.1:8000/docs` | Interactive API docs (Swagger UI) |

---

## Configuration Reference

Copy `.env.example` to `.env` and adjust values for your environment.

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `dev` | Environment: `dev`, `test`, `staging`, `prod` |
| `DATABASE_URL` | `sqlite:///./tradeshield.db` | SQLAlchemy database URL |
| `AUTO_CREATE_SCHEMA` | `true` | Auto-create tables (disable in prod; use Alembic) |
| `AUTH_SECRET` | `change-me-dev-secret` | JWT signing secret — **must be replaced in production** |
| `ACCESS_TOKEN_TTL_MINUTES` | `480` | Token lifetime in minutes |
| `ENABLE_DOCS` | `true` | Serve `/docs` Swagger UI (disable in prod) |
| `CORS_ORIGINS` | `http://127.0.0.1:8000,...` | Comma-separated allowed origins |
| `DEMO_MODE` | `false` | Enable fixture-based demo replay |
| `DEMO_SCENARIO` | `all` | Scenario to replay: `tariff`, `congestion`, or `all` |
| `ENABLED_CONNECTORS` | `all` | Comma-separated connector list or `all` |
| `INGESTION_INTERVAL_SECONDS` | `900` | Ingestion poll cycle (15 min) |
| `INGESTION_ERROR_BACKOFF_MINUTES` | `30` | Backoff window after consecutive failures |
| `INGESTION_BACKOFF_ERROR_THRESHOLD` | `3` | Error count before backoff triggers |
| `ALERT_MAX_ATTEMPTS` | `5` | Max alert delivery attempts |
| `ALERT_RETRY_BACKOFF_SECONDS` | `60` | Delay between retries |
| `NEWS_API_KEY` | *(empty)* | NewsAPI key for news connector |
| `SPIRE_API_KEY` | *(empty)* | Spire key for maritime AIS connector |
| `SMTP_HOST` / `SMTP_PORT` | *(empty)* | SMTP credentials for email alerts |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | *(empty)* | Twilio credentials for WhatsApp alerts |

---

## API Reference

All endpoints are prefixed with `/v1`. Interactive documentation is available at `/docs` when `ENABLE_DOCS=true`.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/auth/register` | Register a new workspace |
| `POST` | `/v1/auth/login` | Obtain an access token |
| `GET` | `/v1/auth/me` | Get the current authenticated user |

### Supply Chain & Risk

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/clients/{client_id}/supply-map` | Retrieve the workspace supply map |
| `POST` | `/v1/clients/{client_id}/supply-map` | Create or update the supply map |
| `POST` | `/v1/clients/{client_id}/supply-map/import-csv` | Bulk-import supply map from CSV |
| `GET` | `/v1/events` | List ingested disruption events |
| `GET` | `/v1/clients/{client_id}/exposures` | Get supplier exposures for an event |
| `GET` | `/v1/clients/{client_id}/risk-scores` | Get risk scores for a time window |
| `GET` | `/v1/clients/{client_id}/events/{event_id}/explainability` | Factor-weight breakdown for a risk score |
| `GET` | `/v1/clients/{client_id}/events/{event_id}/recommendation-override` | Retrieve analyst override |
| `POST` | `/v1/clients/{client_id}/events/{event_id}/recommendation-override` | Set analyst override |
| `POST` | `/v1/clients/{client_id}/playbooks/generate` | Generate a response playbook |
| `GET` | `/v1/playbooks/{playbook_id}` | Get playbook details |
| `GET` | `/v1/playbooks/{playbook_id}/approvals` | List approvals |
| `PATCH` | `/v1/playbooks/{playbook_id}/approvals/{approval_id}` | Update approval status |
| `GET` | `/v1/playbooks/{playbook_id}/comments` | List playbook comments |
| `POST` | `/v1/playbooks/{playbook_id}/comments` | Add a comment |
| `GET` | `/v1/clients/{client_id}/events/{event_id}/outcome` | Get incident outcome |
| `POST` | `/v1/clients/{client_id}/events/{event_id}/outcome` | Record incident outcome |
| `GET` | `/v1/playbooks/{playbook_id}/brief` | Get playbook executive brief |

### Alerts

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/alerts/subscriptions` | List alert subscriptions |
| `POST` | `/v1/alerts/subscriptions` | Create a subscription |
| `PATCH` | `/v1/alerts/subscriptions/{subscription_id}` | Update a subscription |
| `DELETE` | `/v1/alerts/subscriptions/{subscription_id}` | Delete a subscription |
| `GET` | `/v1/alerts/deliveries` | List delivery records |
| `POST` | `/v1/alerts/dispatch` | Manually trigger alert dispatch |
| `POST` | `/v1/webhooks/test` | Test a webhook URL |

### Operations

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/ingestion/run` | Manually trigger an ingestion run |
| `GET` | `/v1/ops/overview` | Operational overview |
| `GET` | `/v1/ops/metrics` | Ingestion and alert metrics |
| `GET` | `/v1/ops/ingestion/runs` | Ingestion run history |
| `GET` | `/v1/ops/source-health` | Connector source health |

### Workspace Administration

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/users` | List workspace users |
| `POST` | `/v1/users` | Create a workspace user |
| `PATCH` | `/v1/users/{user_id}` | Update a user |
| `GET` | `/v1/audit-logs` | Retrieve audit log entries |

---

## Demo Mode

Demo mode replays deterministic fixtures from `demo/fixtures/` through the standard ingestion pipeline, enabling a reproducible showcase without external data sources.

**Enable in `.env`:**
```env
DEMO_MODE=true
DEMO_SCENARIO=all    # or: tariff | congestion
```

**Seed the demo workspace:**
```bash
python scripts/demo_seed.py
```

**Reset and reseed in one command:**
```bash
python scripts/demo_reset.py
```

### Offline Frontend Demo

The UI also supports a fully offline demo mode that requires no running backend:

- Set `offlineDemo: true` in `static/config.js`, or append `?offline=1` to any URL.
- Data is served from `static/demo-fixtures/offline-demo.json`.
- Supported flows: sign-in, dashboard refresh, playbook generation, approvals, comments, outcomes, policies, and supply-map edits.

---

## Testing

Run the full test suite:
```bash
pytest -q
```

**Test coverage includes:**
- Secure registration and authenticated workspace flow
- Tenant isolation enforcement
- User administration and audit log access
- Persisted ingestion runs and source health tracking
- Queued alert delivery for the dashboard channel
- Assessment and playbook recomputation after supply-map changes
- Webhook SSRF guard
- Supply-map idempotency behaviour
- Demo seed lifecycle and deterministic replay ingestion
- Explainability and override delta responses
- End-to-end showcase narrative flow

---

## Deployment

### Docker (Local / Staging)

Start Postgres, the web service, and the worker in one command:
```bash
docker compose up --build
```

> **Before sharing this environment**, make sure to:
> - Replace the `AUTH_SECRET` placeholder in `docker-compose.yml`.
> - Set real SMTP and/or Twilio credentials for off-dashboard alert delivery.
> - Run `alembic upgrade head` against the Postgres database before accepting traffic.

### Free Cloud Deployment (Render + Cloudflare Pages)

Keeps the frontend always live while the backend wakes on demand.

1. **Deploy the frontend** (`static/`) to [Cloudflare Pages](https://pages.cloudflare.com/) (free tier):
   - Create a new Pages project and upload the `static/` directory.
   - In `static/config.js`, point the frontend at your backend:
     ```js
     window.__TRADESHIELD_CONFIG__ = { apiBaseUrl: "https://YOUR_API_DOMAIN" };
     ```

2. **Deploy the backend** on [Render](https://render.com/) using `render-free.yaml`:
   - The blueprint provisions one web service (`tradeshield-api`) and a Postgres instance.
   - Set `AUTH_SECRET` to a strong random value.
   - Set `CORS_ORIGINS` to your Cloudflare Pages URL.

3. **Seed demo data** once from the Render shell:
   ```bash
   python scripts/demo_seed.py
   ```

> **Note:** Free Render instances sleep after inactivity and take ~30–60 seconds to wake.
> In this mode, the worker is not always-on — use the **Pull Latest Signals** and
> **Process Alert Queue** buttons in the UI to trigger manually.
> For automatic 15-minute cycles, switch to the paid deployment below.

### 24/7 Production Deployment (Render Blueprint)

1. Push the repository to GitHub.
2. In Render, create a new **Blueprint** and connect the repository.
3. Render will provision:
   - `tradeshield-web` — FastAPI web service
   - `tradeshield-worker` — Ingestion and alert worker
   - `tradeshield-db` — Managed Postgres
4. Set the same `AUTH_SECRET` in both web and worker services.
5. Deploy — Alembic migrations run automatically via `preDeployCommand`.
6. Seed demo data once from the web service shell:
   ```bash
   python scripts/demo_seed.py
   ```

Blueprint file: [`render.yaml`](render.yaml)

---

## Database & Migrations

The project uses **Alembic** for schema migrations and supports both SQLite (development) and PostgreSQL (staging/production).

**Production environment variables:**
```env
APP_ENV=prod
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tradeshield
AUTO_CREATE_SCHEMA=false
AUTH_SECRET=replace-with-a-long-random-secret
ENABLE_DOCS=false
```

**Apply all pending migrations:**
```bash
alembic upgrade head
```

**Create a new migration after schema changes:**
```bash
alembic revision --autogenerate -m "describe change"
```

> **Environment guidelines:**
> - `dev` / `test` — `AUTO_CREATE_SCHEMA=true` is acceptable.
> - `staging` / `prod` — always use Alembic; set `AUTO_CREATE_SCHEMA=false`.
> - Do not run more than one polling worker against the same environment without introducing distributed locking.

---

## Worker Model

TradeShield separates the API process from the ingestion/alert process for operational clarity and stability.

| Process | Command | Responsibilities |
|---|---|---|
| **Web App** | `uvicorn app.main:app` | Serves the REST API and static dashboard only |
| **Worker** | `python -m app.worker` | Ingestion polling, deduplication, alert queuing, and dispatch |

Manual ops routes remain available so admins and analysts can trigger ingestion or drain the alert queue on demand without requiring a dedicated worker.

**Connector control variables:**
```env
ENABLED_CONNECTORS=gdelt,usgs,ukmto,opensky,newsapi,spire   # or: all
INGESTION_BACKOFF_ERROR_THRESHOLD=3    # consecutive failures before cooldown
INGESTION_ERROR_BACKOFF_MINUTES=30     # cooldown window before retry
```

---

## Security

- **Webhook / callback URLs** — Restricted to `https`; loopback and private-network targets are rejected to prevent SSRF.
- **Tenant isolation** — All tenant routes reject cross-workspace access, even if the caller knows another `client_id`.
- **Audit trail** — All significant actions are persisted in the `auditlog` table.
- **Admin quorum** — The workspace must retain at least one active admin at all times.
- **Production checklist** — Replace `AUTH_SECRET`, disable `/docs`, and use Alembic migrations before accepting production traffic.

---

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) for the full intentional deferral list.

**Planned near-term improvements:**
- Replace the custom bearer token with OIDC / enterprise SSO for external pilots.
- Add distributed worker locking for horizontal scale.
- Analyst review queues for contradictory-source handling.
- CSV export and deeper ERP/TMS native integrations.

---

## Contributing

Contributions are welcome! To get started:

1. Fork the repository and create a feature branch.
2. Install dependencies and run the test suite to confirm a clean baseline:
   ```bash
   pip install -r requirements.txt
   pytest -q
   ```
3. Make your changes, add or update tests as needed, and ensure `pytest -q` still passes.
4. Open a pull request with a clear description of the problem and your solution.

Please follow the existing code style and keep pull requests focused on a single concern.

---

## License

This project is licensed under the [MIT License](LICENSE).
