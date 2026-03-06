# Key Engineering Decisions (Showcase Edition)

## 1) Demo data via replay fixtures, not UI mocks
- Decision: ingest local JSON fixtures through the same ingestion service path.
- Why: preserves backend credibility (dedupe, scoring, alerts still execute).
- Rejected: static UI-only mocks (fast, but weak engineering signal).

## 2) Explainability computed from scoring inputs
- Decision: build explainability from existing exposure and supply-map metrics.
- Why: no heavy model rewrite needed for showcase timeline; remains transparent.
- Rejected: opaque LLM-generated explanations with no numeric grounding.

## 3) Correlation IDs in structured logs
- Decision: add per-request/per-worker correlation IDs.
- Why: demonstrates traceability across ingestion/scoring/alerts with low complexity.
- Rejected: full tracing stack (overkill for 1-week showcase scope).

## 4) Keep existing auth/RBAC/audit foundation
- Decision: avoid SSO/billing/distributed lock expansion.
- Why: focus portfolio signal on cohesive, high-quality core product flow.
- Rejected: breadth-first enterprise backlog in showcase sprint.

## 5) Dedicated `/ops` read-only page
- Decision: expose concise operational metrics and cooldown states.
- Why: increases trust in reliability without adding complex admin surfaces.
- Rejected: embedding all ops telemetry only inside main dashboard.
