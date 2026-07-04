# Customer Onboarding Portal v2

## Problem
Current onboarding takes 5 days due to manual document checks. Target: same day.

## Solution
Self-service portal with document upload and automated ID verification via Jumio API.

## Data
- Collects: name, address, national ID, selfie photo
- Classification: PII-High
- Flows: browser → portal → Jumio API → onboarding DB
- Encrypted at rest in onboarding DB

## Integration Points
- Jumio ID verification API (external) — sync — read
- Onboarding DB (internal) — write
- Notification service (internal) — async — write

## Security
- Auth: OAuth2 via existing identity provider
- Encryption in transit: TLS 1.2+
- PII handling: reviewed with data governance team
- Third-party risk: Jumio assessed at procurement, annual review due

## NFRs
- Availability: 99.5%
- Latency: <3s for document upload
- Scale: up to 500 concurrent users

## Rollback
- Feature flag controls rollout
- Fallback to manual process if portal unavailable
- Not yet confirmed with operations team

## Ownership
- Owning team: Digital Channels
- On-call: not yet assigned

## Open Gaps
- Input validation approach not documented
- CWE categories not reviewed
- Audit logging design pending
- Human override path for failed verifications not defined
