# Test Strategy (Showcase Focus)

## Priorities
- Prove deterministic demo reliability.
- Prove end-to-end decision loop integrity.
- Prove explainability output correctness.
- Preserve existing tenant/security behavior.

## High-value integration tests
1. Demo seed/reset lifecycle:
- demo workspace, policies, and replay events are created predictably.
2. Demo mode determinism:
- repeated ingestion of replay data produces stable fingerprints and duplicate behavior.
3. Explainability endpoint:
- returns weighted factors, assumptions, rationale, and base/override comparison.
4. Override delta correctness:
- active analyst override produces non-null override estimate and delta fields.
5. Narrative E2E:
- onboarding/setup -> ingest -> playbook -> approval -> comment -> outcome.

## Existing suite retained
- auth and tenant isolation
- webhook SSRF guard
- supply-map idempotency
- alert queue and backoff behavior

## Non-goals for this sprint
- performance/load testing
- chaos/failover testing
- fuzz/property-based testing
