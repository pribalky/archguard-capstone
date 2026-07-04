# Security Baseline — Architecture Governance Checklist

## Purpose
Minimum security controls required for all new services in regulated banking environments.
Updated: 2026-07. Owner: Architecture Centre of Excellence.

> **Note on `[domain:X]` tags:** these tag each criterion with one of the six
> governance domains (Security, Data, Integration, Ops, Compliance,
> Architecture) used for grouping, the risk heatmap, and next-action
> suggestions. This file is the human-readable source of truth for what each
> tag *should* be — it is documentation only and is not parsed at runtime.
> The tags actually served to agents live in `mcp_server/policy_server.py`'s
> `CHECKLISTS` dict; if you change a domain here, update that dict too so the
> two don't drift.

## Criteria

- [domain:Security] Authentication and authorization model defined
- [domain:Data]     Data encryption at rest and in transit confirmed
- [domain:Security] Third-party/external API dependencies risk-assessed
- [domain:Data]     PII / sensitive data handling reviewed against policy