"""
Domain & Next-Action Logic — pure-Python utilities (no LLM calls).

Consumed by both app.py (Streamlit UI) and main.py (CLI) to group findings by
governance domain, build the risk heatmap matrix, derive a suggested next
action per blocker, and surface a "green path" of positive signals.

Nothing in this module calls an agent or the network — it only operates on
the `risk_findings` / `compliance_findings` lists already produced by the
pipeline, so it's safe to unit test in isolation.

Domain values are attacker/typo-defensive: risk_agent and compliance_agent
are LLM-driven and have no schema enforcement upstream, so a `domain` field
that is missing, misspelled, or invented is expected to happen occasionally.
Every function here normalizes untrusted `domain` strings via
`normalize_domain()` rather than trusting them as-is.
"""

from __future__ import annotations

# Canonical domain taxonomy, in the display/report order used everywhere
# (UI grouping, CLI grouping, heatmap rows).
DOMAINS = [
    "Security",
    "Data",
    "Integration",
    "Ops",
    "Compliance",
    "Architecture",
]

# Fallback bucket for anything that doesn't match a canonical domain.
UNCLASSIFIED = "Unclassified"

# Heatmap columns, in display order.
SEVERITIES = ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]

# Default action when no rule in NEXT_ACTION_RULES matches.
DEFAULT_ACTION = "Open backlog ticket"


def normalize_domain(domain: str | None) -> str:
    """Defensively validate an untrusted `domain` value from an LLM finding.

    Returns the domain unchanged if it's one of the six canonical DOMAINS
    (case-sensitive exact match, since that's what agents are instructed to
    emit). Anything else — None, empty string, a typo, a domain the model
    invented — collapses to UNCLASSIFIED rather than being trusted as-is.
    """
    if isinstance(domain, str) and domain in DOMAINS:
        return domain
    return UNCLASSIFIED


def _is_blocker(finding: dict) -> bool:
    """A finding counts as a blocker if it's a HIGH-severity risk finding or
    a NOT_MET compliance finding. Mirrors app.py's classify_finding logic."""
    return finding.get("severity") == "HIGH" or finding.get("status") == "NOT_MET"


def group_by_domain(findings: list[dict], domain_key: str = "domain") -> dict[str, list[dict]]:
    """Group a flat list of findings into {domain: [findings]}.

    Every one of the 6 canonical domains is always present as a key (even if
    empty), plus an "Unclassified" bucket for anything that didn't validate.
    This keeps UI/CLI iteration order stable and predictable regardless of
    what's actually present in the data.
    """
    grouped: dict[str, list[dict]] = {d: [] for d in DOMAINS}
    grouped[UNCLASSIFIED] = []

    for f in findings:
        domain = normalize_domain(f.get(domain_key))
        grouped[domain].append(f)

    return grouped


def _severity_bucket(finding: dict) -> str | None:
    """Map a finding (risk-shaped or compliance-shaped) onto one of the 4
    heatmap severity columns.

    Risk findings carry `severity` (HIGH/MEDIUM/LOW/UNKNOWN) directly.
    Compliance findings carry `status` instead: NOT_MET is treated as
    equivalent to a HIGH-severity blocker, UNCLEAR as MEDIUM. MET findings
    are positive signals, not risk — they're excluded from the heatmap
    entirely (they show up in green_path() instead), signaled by returning
    None.
    """
    severity = finding.get("severity")
    if severity is not None:
        return severity if severity in SEVERITIES else "UNKNOWN"

    status = finding.get("status")
    if status == "NOT_MET":
        return "HIGH"
    if status == "UNCLEAR":
        return "MEDIUM"
    if status == "MET":
        return None  # positive signal, not a risk cell

    return "UNKNOWN"


def build_heatmap_matrix(risk_findings: list[dict], compliance_findings: list[dict]) -> dict:
    """Build a 6 (domain) x 4 (severity) matrix of finding counts.

    Returns:
        {
            "domains": [...6 domain names in canonical order...],
            "severities": [...4 severity names in canonical order...],
            "matrix": [[count, count, count, count], ...] # one row per domain
        }

    Shaped this way so it can be passed straight to
    `plotly.graph_objects.Heatmap(z=matrix, x=severities, y=domains)` with no
    further transformation. Findings with an unrecognized/missing domain are
    folded into "Unclassified" via normalize_domain() but that row is
    intentionally NOT included in the returned matrix (the heatmap is scoped
    to the 6 governance domains) — callers who want visibility into
    unclassified findings should surface them separately, e.g. via
    group_by_domain().
    """
    counts = {d: {s: 0 for s in SEVERITIES} for d in DOMAINS}

    for finding in list(risk_findings) + list(compliance_findings):
        domain = normalize_domain(finding.get("domain"))
        if domain == UNCLASSIFIED:
            continue
        bucket = _severity_bucket(finding)
        if bucket is None:
            continue
        counts[domain][bucket] += 1

    matrix = [[counts[d][s] for s in SEVERITIES] for d in DOMAINS]
    return {"domains": list(DOMAINS), "severities": list(SEVERITIES), "matrix": matrix}


# Rule table (priority order — first match wins). Each entry is
# (predicate, action_string). Evaluated top-to-bottom in next_action().
def _rule_security_high(f, domain):
    return domain == "Security" and (f.get("severity") == "HIGH" or f.get("status") == "NOT_MET")


def _rule_security_medium(f, domain):
    return domain == "Security" and f.get("severity") == "MEDIUM"


def _rule_data_blocker(f, domain):
    return domain == "Data" and _is_blocker(f)


def _rule_compliance_blocker(f, domain):
    return domain == "Compliance" and _is_blocker(f)


def _rule_integration_blocker(f, domain):
    return domain == "Integration" and _is_blocker(f)


def _rule_ops_high(f, domain):
    return domain == "Ops" and f.get("severity") == "HIGH"


def _rule_architecture_blocker(f, domain):
    return domain == "Architecture" and _is_blocker(f)


NEXT_ACTION_RULES = [
    (_rule_security_high, "Book security design review"),
    (_rule_security_medium, "Request pen-test / threat model"),
    (_rule_data_blocker, "Escalate to data governance"),
    (_rule_compliance_blocker, "Resubmit with updated section"),
    (_rule_integration_blocker, "Raise RFC (Request for Change)"),
    (_rule_ops_high, "Open backlog ticket"),
    (_rule_architecture_blocker, "Update ADR (Architecture Decision Record)"),
]


def next_action(finding: dict) -> str:
    """Rule-based lookup returning one suggested action string per finding.

    Evaluates NEXT_ACTION_RULES in priority order and returns the first
    match. Falls back to DEFAULT_ACTION ("Open backlog ticket") if the
    finding's (normalized) domain matches none of the rules — this also
    covers "Unclassified" domains, by design.
    """
    domain = normalize_domain(finding.get("domain"))
    for predicate, action in NEXT_ACTION_RULES:
        if predicate(finding, domain):
            return action
    return DEFAULT_ACTION


def green_path(risk_findings: list[dict], compliance_findings: list[dict]) -> list[str]:
    """Return a list of positive-signal strings, or [] if there are none.

    - Every MET compliance criterion → "✅ [checklist] criterion"
    - Every LOW-severity risk finding → "✅ [area] finding — low impact"

    An empty return means the caller (UI/CLI) should hide the section
    entirely rather than render an empty header.
    """
    positives: list[str] = []

    for f in compliance_findings:
        if f.get("status") == "MET":
            checklist = f.get("checklist", "")
            criterion = f.get("criterion", "")
            positives.append(f"✅ [{checklist}] {criterion}")

    for f in risk_findings:
        if f.get("severity") == "LOW":
            area = f.get("area", "")
            finding_text = f.get("finding", "")
            positives.append(f"✅ [{area}] {finding_text} — low impact")

    return positives
