"""
Clarification Agent — identifies gaps in the design doc that block a
confident risk/compliance assessment, and produces targeted follow-up
questions rather than letting the system silently guess.
"""

from google.adk.agents import LlmAgent

CLARIFICATION_AGENT_INSTRUCTIONS = """
You are a Clarification Agent. You receive a design doc plus the findings
already produced by the Risk Agent and Compliance Agent (which may contain
UNKNOWN/UNCLEAR items).

Your job:
1. Identify every UNKNOWN/UNCLEAR/NOT_MET-due-to-missing-info item.
2. For each, write ONE specific, answerable follow-up question that would
   resolve the gap (not generic — reference the actual missing detail).
3. Prioritise questions: HIGH priority = blocks a safe go/no-go decision,
   LOW priority = nice to have.

Respond ONLY as a JSON list of objects:
{ "related_to": "...", "question": "...", "priority": "HIGH|LOW" }
"""

clarification_agent = LlmAgent(
    name="clarification_agent",
    model="gemini-2.5-flash",
    instruction=CLARIFICATION_AGENT_INSTRUCTIONS,
    description=(
        "Turns gaps in risk/compliance findings into specific, prioritised "
        "follow-up questions instead of letting the system guess."
    ),
)
