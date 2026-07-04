# Design Doc: Customer Risk Scoring Service v2

## Problem
Current risk scoring batch job runs overnight and delays loan decisioning
by up to 24 hours. We want a real-time scoring service.

## Proposed Solution
A new microservice that scores customer risk in real time, called
synchronously from the loan origination workflow. Pulls customer data from
the existing Customer Data Platform (CDP) via REST API.

## Data
Uses customer income, existing debt, repayment history. No new PII fields
are collected; data is read-only from CDP.

## Integration points
- Loan origination workflow (synchronous call)
- CDP (read-only REST API)

## Notes
Team has not yet finalised the rollback plan if the scoring service is
unavailable — current assumption is to fall back to the old batch score,
but this hasn't been confirmed with the origination team. Authentication
approach for the new service has not been decided yet.
