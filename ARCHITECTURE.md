# TradeShield Showcase Architecture

## Goal
Show one closed-loop decision flow with deterministic demo data:
detect disruption -> score impact -> generate playbook -> approve -> track outcome.

## Runtime Components
- API app (`uvicorn app.main:app`): auth, tenant APIs, explainability, UI/static pages.
- Worker (`python -m app.worker`): ingestion cycle + alert dispatch cycle.
- Database (SQLite/Postgres): workspace data, events, exposures, impact, playbooks, approvals, outcomes, audit logs.

## Data Flow
1. Ingestion normal mode:
- connectors fetch external events -> normalize -> dedupe/upsert -> queue alerts.
2. Ingestion demo mode:
- local fixture replay (`demo/fixtures`) -> same normalize/dedupe/upsert pipeline.
3. Scoring:
- exposures built against supply map -> impact assessment computed -> playbook generated.
4. Decision loop:
- approval step updates + comments + incident outcome tracking.
5. Explainability:
- factor-weight breakdown + base vs override delta returned via API.

## Why This Design
- Worker separation proves operational thinking (non-blocking API path).
- Tenant + RBAC + audit logs prove production-safe boundaries.
- Deterministic replay proves repeatable demos without external dependency risk.
- Explainability endpoint makes model logic inspectable and defensible.
