# Definition of Ready — Architecture Governance Checklist

## Purpose
Criteria a design doc must satisfy before architecture sign-off and build commencement.
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

- [domain:Architecture] Problem statement and target outcome are clearly defined
- [domain:Data]          Data classification and data flows are documented
- [domain:Integration]   Integration points and dependent systems are identified
- [domain:Ops]           Non-functional requirements (availability, latency, scale) stated
- [domain:Ops]           Rollback / failure-mode plan documented
- [domain:Ops]           Owning team and on-call support identified