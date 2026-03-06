# Free Deployment Checklist (Frontend Always Live + Sleeping Backend)

Use this when you want zero hosting cost and are okay with backend cold starts.

## 1) Final values to choose
Set these once and reuse everywhere:

- `FRONTEND_URL=https://YOUR_PROJECT.pages.dev`
- `API_URL=https://tradeshield-api.onrender.com`
- `AUTH_SECRET=<64+ char random secret>`

Generate `AUTH_SECRET` locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 2) Frontend (Cloudflare Pages, free)

1. Deploy folder `static/` as your Pages project.
2. Edit [static/config.js](/e:/Capstone/static/config.js) before deploy:

```js
window.__TRADESHIELD_CONFIG__ = {
  apiBaseUrl: "https://tradeshield-api.onrender.com",
};
```

3. Redeploy Pages.

## 3) Backend (Render free)

1. In Render, create Blueprint from [render-free.yaml](/e:/Capstone/render-free.yaml).
2. In `tradeshield-api` service, set:
   - `AUTH_SECRET=<same value chosen above>`
   - `CORS_ORIGINS=https://YOUR_PROJECT.pages.dev`
3. Confirm these are already set:
   - `APP_ENV=prod`
   - `AUTO_CREATE_SCHEMA=false`
   - `ENABLE_DOCS=false`
   - `DEMO_MODE=true`
   - `DEMO_SCENARIO=all`
4. Deploy.

## 4) Database + seed

After first deploy:

1. Open Render shell for `tradeshield-api`.
2. Run:

```bash
alembic upgrade head
python scripts/demo_seed.py
```

## 5) Smoke test (another device)

1. Open `FRONTEND_URL`.
2. Use guided onboarding or demo login.
3. Click `Pull Latest Signals`.
4. If backend was sleeping, wait 30-60 seconds and retry once.
5. Generate a playbook and verify:
   - explainability panel loads
   - approvals/comments/outcome can be saved
   - ops page opens from header

## 6) Known free-tier behavior

- Frontend remains live 24/7.
- Backend may sleep after inactivity.
- Worker is not always-on in free mode; use manual buttons:
  - `Pull Latest Signals`
  - `Process Alert Queue`

## 7) If CORS fails

Set backend `CORS_ORIGINS` exactly to your frontend origin, no trailing slash:

- Correct: `https://my-app.pages.dev`
- Incorrect: `https://my-app.pages.dev/`

Then redeploy backend.
