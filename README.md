# TradeShield AI

India-first supply chain disruption intelligence platform for enterprise importers.

This codebase now has the minimum operational foundation for a real product:
- authenticated multi-tenant workspaces
- RBAC and audit logs
- worker-based ingestion instead of web-process polling
- persisted ingestion runs and source-health tracking
- queued alert delivery with retries and real delivery adapters
- workspace user administration
- recomputation of impact and playbooks when supply-map or event facts change
- Postgres and Alembic support
- Docker-based local deployment path

## Product Surface
- Web dashboard at `/`
- Auth:
  - `POST /v1/auth/register`
  - `POST /v1/auth/login`
  - `GET /v1/auth/me`
  - `GET /v1/demo/status`
  - `POST /v1/demo/status`
- Supply chain and risk:
  - `GET /v1/clients/{client_id}/supply-map`
  - `POST /v1/clients/{client_id}/supply-map`
  - `POST /v1/clients/{client_id}/supply-map/import-csv`
  - `GET /v1/events`
  - `GET /v1/clients/{client_id}/exposures?event_id=`
  - `GET /v1/clients/{client_id}/risk-scores?window=`
  - `GET /v1/clients/{client_id}/events/{event_id}/explainability`
  - `GET /v1/clients/{client_id}/events/{event_id}/recommendation-override`
  - `POST /v1/clients/{client_id}/events/{event_id}/recommendation-override`
  - `POST /v1/clients/{client_id}/playbooks/generate`
  - `GET /v1/playbooks/{playbook_id}`
  - `GET /v1/playbooks/{playbook_id}/approvals`
  - `PATCH /v1/playbooks/{playbook_id}/approvals/{approval_id}`
  - `GET /v1/playbooks/{playbook_id}/comments`
  - `POST /v1/playbooks/{playbook_id}/comments`
  - `GET /v1/clients/{client_id}/events/{event_id}/outcome`
  - `POST /v1/clients/{client_id}/events/{event_id}/outcome`
  - `GET /v1/playbooks/{playbook_id}/brief`
- Alerts:
  - `GET /v1/alerts/subscriptions`
  - `POST /v1/alerts/subscriptions`
  - `PATCH /v1/alerts/subscriptions/{subscription_id}`
  - `DELETE /v1/alerts/subscriptions/{subscription_id}`
  - `GET /v1/alerts/deliveries`
  - `POST /v1/alerts/dispatch`
  - `POST /v1/webhooks/test`
- Operations:
  - `POST /v1/ingestion/run`
  - `GET /v1/ops/overview`
  - `GET /v1/ops/metrics`
  - `GET /v1/ops/ingestion/runs`
  - `GET /v1/ops/source-health`
- Workspace admin:
  - `GET /v1/users`
  - `POST /v1/users`
  - `PATCH /v1/users/{user_id}`
  - `GET /v1/audit-logs`

## What Changed In This Slice
- Removed ingestion polling from FastAPI startup. The web app no longer doubles as the worker.
- Added `IngestionRun` and `SourceHealth` models for persisted pipeline visibility.
- Fixed dedupe to use stable source identity instead of unstable timestamps.
- Updated duplicate event handling to refresh existing events and invalidate stale downstream scoring.
- Added alert queue semantics with statuses: `queued`, `processing`, `delivered`, `retry_scheduled`, `blocked`, `failed`.
- Added SMTP email support and Twilio WhatsApp support when configured.
- Added admin APIs to create and update workspace users.
- Added ops/admin sections in the UI for pulling signals, dispatching alerts, and managing team members.
- Added CSV import path for supply-map onboarding.
- Added disruption workflow tracking with playbook comments and event outcomes.
- Added supply-map versioning and analyst recommendation overrides.
- Impact assessments and playbooks now recompute when supply-map version, event updates, or override updates change.

## Local Development
1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create `.env` from `.env.example`.
4. For quick local SQLite development:
   ```env
   APP_ENV=dev
   DATABASE_URL=sqlite:///./tradeshield.db
   AUTO_CREATE_SCHEMA=true
   ```
5. Run the web app:
   ```bash
   uvicorn app.main:app --reload
   ```
6. In a second terminal, run the worker:
   ```bash
   python -m app.worker
   ```
7. Open:
   - Dashboard: `http://127.0.0.1:8000/`
   - Ops page: `http://127.0.0.1:8000/ops`
   - Docs: `http://127.0.0.1:8000/docs`

## Demo Mode
- Configure in `.env`:
  - `DEMO_MODE=true|false`
  - `DEMO_SCENARIO=tariff|congestion|all`
- Demo replay fixtures live in `demo/fixtures`.
- Seed a deterministic showcase workspace:
  ```bash
  python scripts/demo_seed.py
  ```
- Reset and reseed in one command:
  ```bash
  python scripts/demo_reset.py
  ```

### Frontend Offline Demo (Backend Optional)
- Set `offlineDemo: true` in `static/config.js`, or open the app with `?offline=1`.
- In offline demo mode, the UI uses `static/demo-fixtures/offline-demo.json`.
- Supported flow offline: sign-in, dashboard refresh, playbook generation, approvals, comments, outcomes, policies, supply-map edits.

## Docker Deployment
Start Postgres, web, and worker:
```bash
docker compose up --build
```

Before using this in a shared environment:
- replace `AUTH_SECRET`
- set real SMTP and/or Twilio credentials if you want delivery outside the dashboard channel
- run `alembic upgrade head` against Postgres before traffic

## Free Deployment (Frontend Always Live, Backend Sleeps/Wakes)
This matches your requirement: keep UI always reachable and wake backend only when needed.

1. Deploy frontend (`static/`) to Cloudflare Pages (free):
   - Create a new Pages project and upload/deploy the `static` directory.
   - In `static/config.js`, set:
     ```js
     window.__TRADESHIELD_CONFIG__ = { apiBaseUrl: "https://YOUR_API_DOMAIN" };
     ```
2. Deploy backend on Render free using `render-free.yaml`:
   - Blueprint file provisions one web service (`tradeshield-api`) + Postgres.
   - Set `AUTH_SECRET` to a strong value.
   - Set `CORS_ORIGINS` to your Pages URL.
3. Seed demo data once from Render shell:
   ```bash
   python scripts/demo_seed.py
   ```

Notes for free mode:
- Free backend instances can sleep after inactivity and take ~30-60 seconds to wake.
- Frontend stays live continuously.
- Worker is intentionally not always-on in free mode. Use these buttons when needed:
  - `Pull Latest Signals`
  - `Process Alert Queue`
- For automatic 15-minute ingestion and dispatch, switch to paid web+worker deployment (`render.yaml`).

Step-by-step checklist:
- [DEPLOY_FREE_CHECKLIST.md](/e:/Capstone/DEPLOY_FREE_CHECKLIST.md)

For true no-sleep 24/7 on free tier:
- [DEPLOY_ALWAYS_FREE_ORACLE.md](/e:/Capstone/DEPLOY_ALWAYS_FREE_ORACLE.md)

## 24/7 Cloud Deployment (Render Blueprint)
If you want the app live even when your PC is off, use the included Render blueprint.

1. Push this repo to GitHub.
2. In Render, create a new Blueprint and select the repo.
3. Render will provision:
   - `tradeshield-web` (FastAPI web)
   - `tradeshield-worker` (ingestion + alerts)
   - `tradeshield-db` (Postgres)
4. Update `AUTH_SECRET` in both services to the same long random value.
5. Deploy; migrations run via `preDeployCommand: alembic upgrade head`.
6. Seed demo data once from the web service shell:
   ```bash
   python scripts/demo_seed.py
   ```

Blueprint file:
- `render.yaml`

## Postgres and Migrations
Use Postgres outside prototype mode.

Example:
```env
APP_ENV=prod
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tradeshield
AUTO_CREATE_SCHEMA=false
AUTH_SECRET=replace-with-a-long-random-secret
ENABLE_DOCS=false
```

Run migrations:
```bash
alembic upgrade head
```

Create a new migration after schema changes:
```bash
alembic revision -m "describe change"
```

## Worker Model
- `uvicorn app.main:app` serves the API and dashboard only.
- `python -m app.worker` runs polling, dedupe, alert queueing, and alert dispatch.
- Manual ops routes remain available for admins and analysts when you want to pull data or drain the queue on demand.
- For live stability, configure connector controls:
  - `ENABLED_CONNECTORS=gdelt,usgs,ukmto,opensky,newsapi,spire` or `all`
  - `INGESTION_BACKOFF_ERROR_THRESHOLD=3` to trigger cooldown after consecutive failures
  - `INGESTION_ERROR_BACKOFF_MINUTES=30` cooldown window before retry

## Environment Notes
- `dev` and `test`: schema auto-create can stay enabled.
- `staging` and `prod`: run Alembic migrations and set `AUTO_CREATE_SCHEMA=false`.
- `prod`: docs should be disabled and `AUTH_SECRET` must be replaced.
- Do not run more than one polling worker against the same environment unless you introduce distributed locking.

## Security Notes
- Callback/webhook test URLs are restricted to `https` and reject loopback/private-local targets.
- Tenant routes reject cross-workspace access even if a user knows another `client_id`.
- Audit trails are stored in `auditlog`.
- The workspace must always retain at least one active admin.

## Testing
Run:
```bash
pytest -q
```

Current coverage includes:
- secure registration and authenticated workspace flow
- tenant isolation enforcement
- user admin and audit access
- persisted ingestion runs and source health
- queued alert delivery for dashboard channel
- assessment and playbook recomputation after supply-map changes
- webhook SSRF guard
- supply-map idempotency behavior
- demo seed lifecycle and deterministic replay ingestion
- explainability and override delta responses
- end-to-end showcase narrative flow

## Near-Term Gaps
- Replace the custom bearer token with OIDC or enterprise SSO for external pilots.
- Add distributed worker locking before running multiple workers.
- Add analyst review queues and contradictory-source handling.
- Add CSV import/export and deeper ERP/TMS integrations.
