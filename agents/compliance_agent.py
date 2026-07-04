"""
Compliance Agent — checks the design doc against governance checklists
fetched live from the MCP policy server (mcp_server/policy_server.py),
rather than having criteria hardcoded into the prompt. This is the agent
that demonstrates real MCP tool usage.
"""

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import MCPToolset
from mcp import StdioServerParameters

# Connects to the local policy server over stdio. In production this would
# point at a real governance doc repository exposed via MCP instead.
policy_toolset = MCPToolset(
    connection_params=StdioServerParameters(
        command="python",
        args=["mcp_server/policy_server.py"],
    )
)

COMPLIANCE_AGENT_INSTRUCTIONS = """
You are a Compliance Agent reviewing a proposed design doc against your
organisation's governance checklists.

Steps:
1. Call list_checklists to see available checklists.
2. Call get_checklist for 'definition_of_ready', 'security_baseline', and
   'compliance_owasp_cwe'.
3. Each checklist's `criteria` field is a list of OBJECTS, not plain
   strings. Each object has two fields:
   - "text": the criterion text itself — use this as the "criterion" value
     in your output.
   - "domain": one of Security | Data | Integration | Ops | Compliance |
     Architecture — copy this value UNCHANGED into your output's "domain"
     field. Do not rename, translate, or reinterpret it, and never invent a
     domain that isn't one of those six.
4. For each criterion in each checklist, determine from the design doc
   whether it is: MET, NOT_MET, or UNCLEAR (insufficient info to judge).
5. Output a JSON list of objects:
   { "checklist": ..., "criterion": ..., "domain": ...,
     "status": "MET|NOT_MET|UNCLEAR", "evidence_or_gap": "short explanation" }

   "criterion" must be the criterion's "text" value (a plain string) — never
   output the raw {text, domain} object as the criterion value.

Do not invent evidence. If the design doc doesn't address a criterion,
mark it UNCLEAR or NOT_MET — never assume compliance.
Respond ONLY with the JSON list, no extra prose.
"""

compliance_agent = LlmAgent(
    name="compliance_agent",
    model="gemini-2.5-flash",
    instruction=COMPLIANCE_AGENT_INSTRUCTIONS,
    description=(
        "Checks a design doc against governance checklists fetched live "
        "from the MCP policy server."
    ),
    tools=[policy_toolset],
)