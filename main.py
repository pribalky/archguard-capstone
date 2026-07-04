"""
CLI entrypoint.

    python main.py --input examples/sample_design_doc.md

Outputs:
  1. Plain English governance summary (human-readable)
  2. Full structured JSON report (machine-readable)
"""

import argparse
import asyncio
import json

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.orchestrator_agent import readiness_pipeline, compile_report
from agents.domain_utils import DOMAINS, green_path, group_by_domain, next_action
from security.audit import new_run_id, log_event

load_dotenv()

APP_NAME = "architecture_readiness_review"
USER_ID = "local_user"


def _domain_ordered_groups(findings: list) -> list:
    """Group findings by domain (canonical order, then an Unclassified tail
    if present) and return only the non-empty (domain, findings) pairs, in
    display order. Thin wrapper around domain_utils.group_by_domain() that
    drops empty buckets and fixes the iteration order for CLI section
    headers."""
    grouped = group_by_domain(findings)
    ordered = [(d, grouped[d]) for d in DOMAINS if grouped[d]]
    if grouped.get("Unclassified"):
        ordered.append(("Unclassified", grouped["Unclassified"]))
    return ordered


def generate_summary(report: dict) -> str:
    """Convert structured report → plain English governance summary.
    Written for non-technical stakeholders and governance forums.
    No JSON. No jargon. Actionable.
    """
    name = report.get("design", "Design")
    score = report.get("readiness_score", 0)
    band = report.get("readiness", "UNKNOWN")
    breakdown = report.get("score_breakdown", {})

    risk_findings = report.get("risk_findings", [])
    high_risks = [f for f in risk_findings if f.get("severity") == "HIGH"]
    medium_risks = [f for f in risk_findings if f.get("severity") == "MEDIUM"]

    compliance = report.get("compliance_findings", [])
    not_met = [f for f in compliance if f.get("status") == "NOT_MET"]
    unclear = [f for f in compliance if f.get("status") == "UNCLEAR"]

    gaps = report.get("clarifications_needed", [])
    high_gaps = [g for g in gaps if g.get("priority") == "HIGH"]

    band_label = {
        "READY_WITH_NOTES": "✅ READY WITH NOTES",
        "NEEDS_WORK":       "⚠️  NEEDS WORK",
        "NOT_READY":        "❌ NOT READY",
    }.get(band, band)

    lines = [
        "=" * 60,
        f"ARCHITECTURE GOVERNANCE REVIEW",
        f"Design : {name}",
        f"Score  : {score}/100  →  {band_label}",
        "=" * 60,
        "",
    ]

    # Verdict paragraph
    if band == "NOT_READY":
        lines.append(
            f"This design is NOT approved to proceed. Governance score {score}/100 "
            f"reflects {len(high_risks)} critical risk(s) and {len(not_met)} unmet "
            f"compliance criteria. Human sign-off required before rework is reviewed."
        )
    elif band == "NEEDS_WORK":
        lines.append(
            f"This design requires further work before approval. Score {score}/100 "
            f"indicates gaps that must be resolved. Resubmit after addressing "
            f"HIGH priority clarifications."
        )
    else:
        lines.append(
            f"Design is provisionally acceptable. Score {score}/100. "
            f"Minor notes below must be acknowledged before sign-off."
        )

    # Green Path — positive signals, shown before blockers. Hidden entirely
    # if there are none (green_path() returns [] rather than a falsy string).
    positives = green_path(risk_findings, compliance)
    if positives:
        lines += ["", "WHAT THIS DESIGN GOT RIGHT:"]
        for p in positives:
            lines.append(f"  {p}")

    # Critical risks — grouped by domain (canonical order), each blocker
    # gets a next_action() line in addition to the agent's own recommendation.
    if high_risks:
        lines += ["", "CRITICAL RISKS (must resolve before proceeding):"]
        for domain, findings in _domain_ordered_groups(high_risks):
            lines.append(f"")
            lines.append(f"  CRITICAL RISKS — {domain}:")
            for r in findings:
                lines.append(f"    • [{r.get('area','?')}] {r.get('finding','')}")
                lines.append(f"      → {r.get('recommendation','')}")
                lines.append(f"      → Action: {next_action(r)}")

    # Medium risks — advisory, not blockers, so no domain grouping or
    # next_action here (kept as a flat list, as before).
    if medium_risks:
        lines += ["", "MODERATE RISKS (should resolve before build):"]
        for r in medium_risks:
            lines.append(f"  • [{r.get('area','?')}] {r.get('finding','')}")

    # Compliance gaps — NOT_MET items are blockers, grouped by domain with
    # a next_action() line each, same treatment as critical risks above.
    if not_met:
        lines += ["", "COMPLIANCE — NOT MET:"]
        for domain, findings in _domain_ordered_groups(not_met):
            lines.append(f"")
            lines.append(f"  COMPLIANCE — NOT MET — {domain}:")
            for f in findings:
                lines.append(f"    • [{f.get('checklist','?')}] {f.get('criterion','')}")
                lines.append(f"      Gap: {f.get('evidence_or_gap','')}")
                lines.append(f"      → Action: {next_action(f)}")

    if unclear:
        lines += ["", "COMPLIANCE — NEEDS CLARIFICATION:"]
        for f in unclear:
            lines.append(f"  • [{f.get('checklist','?')}] {f.get('criterion','')}")

    # Top clarifications
    if high_gaps:
        lines += ["", "TOP QUESTIONS BEFORE SIGN-OFF:"]
        for i, g in enumerate(high_gaps[:5], 1):
            lines.append(f"  {i}. {g.get('question','')}")

    # Score breakdown
    lines += [
        "",
        "SCORE BREAKDOWN:",
        f"  Risk deductions       : -{breakdown.get('risk', 0)} pts",
        f"  Compliance deductions : -{breakdown.get('compliance', 0)} pts",
        f"  Clarification gaps    : -{breakdown.get('clarification', 0)} pts",
        f"  Final score           : {score}/100",
        "",
        f"Audit log: {report.get('audit_log_ref', 'N/A')}",
        "Human sign-off required before any approval is actioned.",
        "=" * 60,
    ]

    return "\n".join(lines)


async def run_pipeline(design_doc_text: str, run_id: str) -> dict:
    runner = InMemoryRunner(agent=readiness_pipeline, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    log_event(run_id, "orchestrator", "run_start", {"design_doc_chars": len(design_doc_text)})

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=design_doc_text)],
    )

    risk_findings, compliance_findings, clarification_questions = [], [], []

    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=user_message
    ):
        if not event.content or not event.content.parts:
            continue
        text = "".join(p.text for p in event.content.parts if p.text)
        if not text.strip():
            continue

        author = getattr(event, "author", "unknown")
        log_event(run_id, author, "agent_output_raw", {"text": text[:2000]})

        try:
            clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            continue

        if author == "risk_agent":
            risk_findings = parsed
        elif author == "compliance_agent":
            compliance_findings = parsed
        elif author == "clarification_agent":
            clarification_questions = parsed

    return compile_report(
        run_id=run_id,
        design_name=design_doc_text.splitlines()[0].strip("# ").strip(),
        risk_findings=risk_findings,
        compliance_findings=compliance_findings,
        clarification_questions=clarification_questions,
        human_sign_off=False,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to design doc (markdown/text)")
    parser.add_argument("--json-only", action="store_true", help="Output JSON only, no summary")
    args = parser.parse_args()

    with open(args.input) as f:
        design_doc_text = f.read()

    run_id = new_run_id()
    report = asyncio.run(run_pipeline(design_doc_text, run_id))

    if args.json_only:
        print(json.dumps(report, indent=2))
    else:
        print(generate_summary(report))
        print("\n--- FULL JSON REPORT ---\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()