"""
Unit tests for agents/domain_utils.py.

Run with:
    pytest tests/test_domain_utils.py -v

These are pure-function tests — no agent, no MCP server, no network — so
they should run in well under a second and can be added to CI / the eval
harness's "no regressions" gate without needing API keys or a running
policy server.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.domain_utils import (
    DOMAINS,
    SEVERITIES,
    UNCLASSIFIED,
    build_heatmap_matrix,
    green_path,
    group_by_domain,
    next_action,
    normalize_domain,
)


# ── normalize_domain / group_by_domain ──────────────────────────────────────

def test_group_by_domain_handles_missing_and_invalid_domains():
    """A finding with no `domain` key, an empty string, or a value the LLM
    invented (e.g. a typo or a domain outside the 6-item taxonomy) must all
    land in the 'Unclassified' bucket rather than being dropped, raising, or
    silently trusted as a fake 7th domain. Valid domains must be grouped
    under their exact canonical key."""
    findings = [
        {"id": 1, "domain": "Security"},
        {"id": 2},  # missing domain entirely
        {"id": 3, "domain": ""},  # empty string
        {"id": 4, "domain": "SECURITY"},  # wrong case — must NOT silently match
        {"id": 5, "domain": "Secuirty"},  # typo the model might plausibly emit
        {"id": 6, "domain": "Data"},
    ]

    grouped = group_by_domain(findings)

    # Every canonical domain key is always present, even if empty.
    for d in DOMAINS:
        assert d in grouped
    assert UNCLASSIFIED in grouped

    assert [f["id"] for f in grouped["Security"]] == [1]
    assert [f["id"] for f in grouped["Data"]] == [6]
    # missing / empty / wrong-case / typo'd domains all fall through together
    assert sorted(f["id"] for f in grouped[UNCLASSIFIED]) == [2, 3, 4, 5]

    # Sanity: normalize_domain itself agrees with the grouping behavior above
    assert normalize_domain("Security") == "Security"
    assert normalize_domain("SECURITY") == UNCLASSIFIED
    assert normalize_domain(None) == UNCLASSIFIED
    assert normalize_domain("") == UNCLASSIFIED


# ── build_heatmap_matrix ─────────────────────────────────────────────────────

def test_heatmap_matrix_counts_risk_and_compliance_findings_correctly():
    """Verifies the domain x severity matrix shape and cell counts, and that
    compliance findings are folded onto the severity axis via status
    (NOT_MET -> HIGH column, UNCLEAR -> MEDIUM column), while MET findings
    are excluded from the heatmap entirely (they're positive signals, not
    risk cells) and unclassified-domain findings don't pollute any row."""
    risk_findings = [
        {"domain": "Security", "severity": "HIGH"},
        {"domain": "Security", "severity": "HIGH"},
        {"domain": "Data", "severity": "LOW"},
        {"domain": "NotARealDomain", "severity": "HIGH"},  # must be excluded
    ]
    compliance_findings = [
        {"domain": "Security", "status": "NOT_MET"},  # -> Security/HIGH
        {"domain": "Ops", "status": "UNCLEAR"},        # -> Ops/MEDIUM
        {"domain": "Ops", "status": "MET"},            # excluded (positive signal)
    ]

    result = build_heatmap_matrix(risk_findings, compliance_findings)

    assert result["domains"] == DOMAINS
    assert result["severities"] == SEVERITIES

    matrix = result["matrix"]
    assert len(matrix) == 6
    assert all(len(row) == 4 for row in matrix)

    security_row = matrix[DOMAINS.index("Security")]
    data_row = matrix[DOMAINS.index("Data")]
    ops_row = matrix[DOMAINS.index("Ops")]

    # Security: 2 HIGH risk findings + 1 NOT_MET compliance finding -> HIGH=3
    assert security_row[SEVERITIES.index("HIGH")] == 3
    # Data: 1 LOW risk finding
    assert data_row[SEVERITIES.index("LOW")] == 1
    # Ops: 1 UNCLEAR -> MEDIUM column, the MET finding must NOT be counted anywhere
    assert ops_row[SEVERITIES.index("MEDIUM")] == 1
    assert sum(ops_row) == 1  # MET finding excluded, so total Ops count stays at 1

    # Total cells counted == total findings minus the excluded ones
    # (1 invalid-domain risk finding + 1 MET compliance finding excluded)
    total_counted = sum(sum(row) for row in matrix)
    assert total_counted == len(risk_findings) + len(compliance_findings) - 2


# ── next_action rule priority ────────────────────────────────────────────────

def test_next_action_rule_priority_and_fallback():
    """The rule table is priority-ordered and first-match-wins. This test
    pins down the trickiest ordering case: a Security finding that is BOTH
    HIGH severity in general framing and would also match a hypothetical
    'any blocker' rule must resolve via the Security-specific HIGH rule
    (highest priority), not fall through to a generic fallback. Also checks
    the MEDIUM-security branch, an unmatched domain/severity combo hitting
    the default action, and that Unclassified domains always hit fallback."""
    # Security + HIGH -> most specific, highest-priority rule
    assert next_action({"domain": "Security", "severity": "HIGH"}) == "Book security design review"
    # Security + NOT_MET (no severity field at all) also hits the same rule
    assert next_action({"domain": "Security", "status": "NOT_MET"}) == "Book security design review"
    # Security + MEDIUM -> the second, lower-priority security rule
    assert next_action({"domain": "Security", "severity": "MEDIUM"}) == "Request pen-test / threat model"
    # Data domain + any blocker -> escalate to governance, regardless of severity label
    assert next_action({"domain": "Data", "status": "NOT_MET"}) == "Escalate to data governance"
    # Ops + LOW is not a blocker and matches no rule -> falls back to default
    assert next_action({"domain": "Ops", "severity": "LOW"}) == "Open backlog ticket"
    # Domain missing/invalid entirely -> always falls back, never raises
    assert next_action({"severity": "HIGH"}) == "Open backlog ticket"
    assert next_action({"domain": "TotallyMadeUp", "severity": "HIGH"}) == "Open backlog ticket"


# ── green_path (bonus coverage, keeps parity with plan's spec) ──────────────

def test_green_path_returns_empty_list_when_no_positive_signals():
    """When there are no MET compliance findings and no LOW risk findings,
    green_path must return an empty list (not None, not a falsy string) so
    the UI/CLI can cleanly hide the section."""
    risk_findings = [{"domain": "Security", "severity": "HIGH", "area": "Auth", "finding": "no auth"}]
    compliance_findings = [{"domain": "Data", "status": "NOT_MET", "checklist": "dor", "criterion": "PII reviewed"}]

    result = green_path(risk_findings, compliance_findings)
    assert result == []
