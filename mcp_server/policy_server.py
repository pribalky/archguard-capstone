"""
Mock MCP server exposing a governance/compliance checklist as a callable tool.

In a real deployment this would sit in front of an actual policy repository
(Confluence, Drive, internal governance wiki) so the checklist can be updated
independently of agent code. Here it's a small static repository served over
MCP, which is enough to demonstrate real MCP tool-calling rather than a
hardcoded prompt.

Each criterion carries a `domain` tag (one of the 6 governance domains in
agents/domain_utils.py: Security, Data, Integration, Ops, Compliance,
Architecture) so the Compliance Agent can attach it to each finding. These
tags mirror the `[domain:X]` annotations in the policies/*.md files — the
.md files are the human-readable source of truth for what each criterion
means, but nothing parses them at runtime; this dict is what's actually
served, so keep the two in sync by hand when either changes.

Run standalone for testing:
    python mcp_server/policy_server.py
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("governance-policy-server")

# --- Mock policy repository -------------------------------------------------
# In production: swap this dict for a real fetch from a doc store.
# Each criterion is a {"text": ..., "domain": ...} object (was a plain string
# prior to the domain-tagging feature).
CHECKLISTS = {
    "definition_of_ready": [
        {"text": "Problem statement and target outcome are clearly defined", "domain": "Architecture"},
        {"text": "Data classification and data flows are documented", "domain": "Data"},
        {"text": "Integration points and dependent systems are identified", "domain": "Integration"},
        {"text": "Non-functional requirements (availability, latency, scale) stated", "domain": "Ops"},
        {"text": "Rollback / failure-mode plan documented", "domain": "Ops"},
        {"text": "Owning team and on-call support identified", "domain": "Ops"},
    ],
    "security_baseline": [
        {"text": "Authentication and authorization model defined", "domain": "Security"},
        {"text": "Data encryption at rest and in transit confirmed", "domain": "Data"},
        {"text": "Third-party/external API dependencies risk-assessed", "domain": "Security"},
        {"text": "PII / sensitive data handling reviewed against policy", "domain": "Data"},
    ],
    # NOTE: this key was previously misspelled "compliance_obowasp_cwe" and has
    # been corrected project-wide (this dict, compliance_agent.py's
    # instructions, and the .md filename all now agree on the same key).
    "compliance_owasp_cwe": [
        {"text": "Input validation approach documented (OWASP alignment)", "domain": "Security"},
        {"text": "Known CWE categories considered for this component type", "domain": "Compliance"},
        {"text": "Audit logging of decisions/actions in place", "domain": "Compliance"},
        {"text": "Human override / sign-off path exists for automated decisions", "domain": "Compliance"},
    ],
}


@mcp.tool()
def get_checklist(checklist_name: str) -> dict:
    """Return a named governance checklist.

    Args:
        checklist_name: one of 'definition_of_ready', 'security_baseline',
            'compliance_owasp_cwe'.

    Returns:
        dict with the checklist name and its list of criteria. Each
        criterion is an object: {"text": "<criterion text>", "domain": "<one
        of Security|Data|Integration|Ops|Compliance|Architecture>"}.
    """
    items = CHECKLISTS.get(checklist_name)
    if items is None:
        return {
            "error": f"Unknown checklist '{checklist_name}'",
            "available": list(CHECKLISTS.keys()),
        }
    return {"checklist_name": checklist_name, "criteria": items}


@mcp.tool()
def list_checklists() -> list[str]:
    """Return the names of all available governance checklists."""
    return list(CHECKLISTS.keys())


if __name__ == "__main__":
    mcp.run()