# Fraud Detection Alert Service v3

## Problem
Fraud alerts batch-processed every 4 hours — intervention delayed.
Target: real-time alert delivery <30s from transaction event.

## Solution
Event-driven microservice consuming transaction events from Kafka,
scoring via internal ML model API, triggering alerts via notification service.
Read-only. No new data store introduced.

## Data
- Fields: transaction ID, amount, merchant, timestamp, customer ID (pseudonymised)
- Classification: Confidential — Financial
- Flows: Kafka → fraud-alert-service → ML scoring API → notification service
- Encryption in transit: TLS 1.3 enforced on all hops
- No data at rest: stateless service, no local persistence
- PII handling: reviewed and approved by Data Governance (ref: DG-2026-047)

## Integration Points
- Kafka topic: transactions.raw — async — read-only
- ML Scoring API (internal) — sync — SLA: <100ms p99
- Notification Service (internal) — async — fire-and-forget
- All dependencies risk-assessed. No external third-party APIs.

## Security
- Auth: mTLS for all service-to-service calls
- Authorisation: least-privilege service account, scoped to Kafka consumer group
- Input validation: all Kafka messages validated against Avro schema before processing
- CWE categories reviewed: CWE-20, CWE-200, CWE-319 — all mitigated
- Secrets: stored in HashiCorp Vault, 90-day rotation
- OWASP alignment confirmed by security review (ref: SR-2026-112)

## NFRs
- Availability: 99.95% (active-active, two AZs)
- Latency: <30s end-to-end from Kafka event to alert
- Scale: auto-scaling via Kubernetes HPA — load tested to 10k events/min
- Monitoring: Datadog dashboards + PagerDuty alerts configured

## Rollback
- Blue/green deployment — instant rollback via traffic switch
- Fallback: batch job re-enabled via feature flag if service unavailable
- Confirmed with Fraud Operations and Platform Engineering (sign-off: 2026-06-28)

## Audit & Compliance
- Audit logging: every scoring decision logged to immutable store, 90-day retention
- Human override: fraud analyst can suppress or escalate any alert via case management UI
- HIGH-risk alerts require analyst confirmation before customer action taken

## Ownership
- Owning team: Fraud Engineering
- On-call: PagerDuty 4-engineer rotation, 24/7 coverage
- Runbook: confluence.internal/fraud-alert-service/runbook

## Open Gaps
- Load test at 10x peak not yet completed — scheduled 2026-07-10
- DR failover test planned Q3 2026
