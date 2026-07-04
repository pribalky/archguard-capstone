"""
Orchestrator — wires risk_agent, compliance_agent, and clarification_agent
into a single multi-agent system using ADK's SequentialAgent.

Improvement 3: weighted scoring replaces binary READY/NOT_READY.
Score 0-100. Thresholds:
  80-100 = READY_WITH_NOTES
  50-79  = NEEDS_WORK
  0-49   = NOT_READY

Guardrail still hard-blocks autonomous approval regardless of score.
"""

import json
from google.adk.agents import SequentialAgent
from agents.risk_agent import risk_agent
from agents.compliance_agent import compliance_agent
from agents.clarification_agent import clarification_agent
from security.audit import enforce_no_autonomous_approval, log_event

readiness_pipeline = SequentialAgent(
    name="architecture_readiness_orchestrator",
    sub_agents=[risk_agent, compliance_agent, clarification_agent],
    description=(
        "Runs a design doc through risk assessment, compliance checking "
        "(via MCP policy server), and gap clarification, producing a "
        "weighted-score readiness report."
    ),
)

# Severity → point deductions
RISK_WEIGHTS = {"HIGH": 25, "MEDIUM": 10, "LOW": 3, "UNKNOWN": 5}
STATUS_WEIGHTS = {"NOT_MET": 15, "UNCLEAR": 5, "MET": 0}
CLARIFICATION_WEIGHTS = {"HIGH": 10, "LOW": 3}

# Score thresholds
READY_WITH_NOTES = 80
NEEDS_WORK = 50


def compute_score(
    risk_findings: list,
    compliance_findings: list,
    clarification_questions: list,
) -> dict:
    """Deduct points per finding. Return score + band + breakdown."""
    deductions = {
        "risk": sum(RISK_WEIGHTS.get(f.get("severity", ""), 0) for f in risk_findings),
        "compliance": sum(STATUS_WEIGHTS.get(f.get("status", ""), 0) for f in compliance_findings),
        "clarification": sum(CLARIFICATION_WEIGHTS.get(q.get("priority", ""), 0) for q in clarification_questions),
    }
    total_deduction = sum(deductions.values())
    score = max(0, 100 - total_deduction)

    if score >= READY_WITH_NOTES:
        band = "READY_WITH_NOTES"
    elif score >= NEEDS_WORK:
        band = "NEEDS_WORK"
    else:
        band = "NOT_READY"

    return {"score": score, "band": band, "deductions": deductions}


def compile_report(
    run_id: str,
    design_name: str,
    risk_findings: list,
    compliance_findings: list,
    clarification_questions: list,
    human_sign_off: bool = False,
) -> dict:
    scoring = compute_score(risk_findings, compliance_findings, clarification_questions)

    report = {
        "design": design_name,
        "risk_findings": risk_findings,
        "compliance_findings": compliance_findings,
        "clarifications_needed": clarification_questions,
        "readiness_score": scoring["score"],
        "readiness": scoring["band"],
        "score_breakdown": scoring["deductions"],
        "human_sign_off": human_sign_off,
    }

    # Hard safety boundary — guardrail still enforced regardless of score
    report = enforce_no_autonomous_approval(report)
    log_event(run_id, "orchestrator", "final_verdict", report)
    report["audit_log_ref"] = f"logs/run_{run_id}.jsonl"
    return report
