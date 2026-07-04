"""
ArchGuard — Architecture Governance Review Agent
Run: python -m streamlit run app.py
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from agents.domain_utils import DOMAINS, build_heatmap_matrix, green_path, group_by_domain, next_action
from agents.orchestrator_agent import (
    NEEDS_WORK,
    READY_WITH_NOTES,
    compute_score as _orchestrator_compute_score,
)

load_dotenv()

# On Streamlit Community Cloud there's no .env file — secrets are configured
# in the app's Secrets panel instead, which populates st.secrets, NOT
# os.environ. The agents/google-adk code underneath this app reads its API
# key via os.environ (same as it would locally from .env), so bridge any
# matching Streamlit secrets into the environment here. Locally, if there's
# no .streamlit/secrets.toml at all (the normal case when you're just using
# .env), st.secrets raises StreamlitSecretNotFoundError rather than behaving
# like an empty dict — so this has to be wrapped, or every local run without
# a secrets.toml file would crash on startup.
try:
    for _key in ("GEMINI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        if _key in st.secrets and not os.environ.get(_key):
            os.environ[_key] = str(st.secrets[_key])
except st.errors.StreamlitSecretNotFoundError:
    pass  # no secrets.toml at all — fine locally, .env already covers this

st.set_page_config(
    page_title="ArchGuard — Architecture Governance Review",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* SCROLLABLE SIDEBAR */
section[data-testid="stSidebar"] > div:first-child {
    overflow-y: auto !important;
    max-height: 100vh;
    padding-bottom: 2rem;
}
section[data-testid="stSidebar"] {
    min-width: 320px !important;
    max-width: 340px !important;
}

.archguard-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    border-radius: 12px; padding: 2rem 2.5rem; margin-bottom: 1.5rem;
    border: 1px solid #334155;
}
.archguard-header h1 { color: #f1f5f9; font-size: 2rem; font-weight: 700; margin: 0; }
.archguard-header p  { color: #94a3b8; margin: 0.5rem 0 0 0; font-size: 1rem; }
.archguard-badges    { margin-top: 0.75rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
.badge {
    background: #1e3a5f; border: 1px solid #3b82f6; color: #93c5fd;
    border-radius: 20px; padding: 0.2rem 0.7rem; font-size: 0.75rem; font-weight: 600;
}

.score-ring { font-size: 3.5rem; font-weight: 700; text-align: center; line-height: 1; }
.band-label { text-align: center; font-size: 1rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; margin: 0.25rem 0 1rem 0; }

.metric-box { background: #f1f5f9; border-radius: 8px; padding: 0.9rem; text-align: center; }
.metric-box .val { font-size: 1.8rem; font-weight: 700; }
.metric-box .lbl { font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }

.exec-summary {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 1.1rem 1.3rem; margin-bottom: 1rem;
}
.exec-summary h4 { margin: 0 0 0.5rem 0; color: #1e293b; font-size: 0.95rem; }
.exec-summary p  { margin: 0; color: #475569; font-size: 0.88rem; line-height: 1.6; }

.blocker-card {
    border-left: 4px solid #ef4444; padding: 0.7rem 1rem;
    margin-bottom: 0.6rem; border-radius: 0 6px 6px 0;
    background: #fef2f2;
}
.advisory-card {
    border-left: 4px solid #f59e0b; padding: 0.7rem 1rem;
    margin-bottom: 0.6rem; border-radius: 0 6px 6px 0;
    background: #fffbeb;
}
.finding-card { border-left: 4px solid; padding: 0.7rem 1rem;
    margin-bottom: 0.6rem; border-radius: 0 6px 6px 0; background: #f8fafc; }
.HIGH    { border-color: #ef4444; }
.MEDIUM  { border-color: #f59e0b; }
.LOW     { border-color: #6b7280; }
.NOT_MET { border-color: #ef4444; background: #fef2f2; }
.UNCLEAR { border-color: #f59e0b; background: #fffbeb; }
.MET     { border-color: #22c55e; background: #f0fdf4; }

.priority-item { background: #fef2f2; border-left: 4px solid #ef4444;
    border-radius: 0 6px 6px 0; padding: 0.6rem 0.9rem;
    margin-bottom: 0.5rem; font-size: 0.9rem; }
.question-item { background: #f8fafc; border-radius: 6px; padding: 0.6rem 0.9rem;
    margin-bottom: 0.5rem; border-left: 3px solid #3b82f6; font-size: 0.88rem; }
.guardrail-box { background: #1e293b; color: #f1f5f9; border-radius: 8px;
    padding: 0.9rem 1.2rem; font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem; margin-top: 0.75rem; }
.history-item { background: #f8fafc; border-radius: 6px; padding: 0.5rem 0.75rem;
    margin-bottom: 0.4rem; border-left: 3px solid #3b82f6; font-size: 0.82rem; }
.gp-good { background: #f0fdf4; border-left: 4px solid #22c55e;
    border-radius: 0 6px 6px 0; padding: 0.6rem 0.9rem; margin-bottom: 0.5rem; }
.gp-bad  { background: #fef2f2; border-left: 4px solid #ef4444;
    border-radius: 0 6px 6px 0; padding: 0.6rem 0.9rem; margin-bottom: 0.5rem; }
.reviewer-bar {
    background: #f1f5f9; border-radius: 8px; padding: 0.75rem 1rem;
    margin-bottom: 1rem; display: flex; gap: 1rem; align-items: center;
    border: 1px solid #e2e8f0; font-size: 0.85rem; color: #475569;
}
.footer { text-align: center; color: #94a3b8; font-size: 0.78rem;
    margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

# ── Helpers ────────────────────────────────────────────────────────────────────
def load(name):
    p = Path(f"examples/{name}")
    return p.read_text() if p.exists() else ""

def word_count(text): return len(text.split())

COMPLETENESS_CHECKS = [
    ("Problem statement",  r"## Problem|## problem"),
    ("Solution described", r"## Solution|## solution|## Proposed"),
    ("Data section",       r"## Data|classification|encrypt"),
    ("Integration points", r"## Integration|integration point"),
    ("Security section",   r"## Security|auth|OAuth|mTLS|TLS"),
    ("NFRs stated",        r"availability|latency|scale|99\.|SLO"),
    ("Rollback plan",      r"rollback|fallback|feature flag"),
    ("Ownership named",    r"owning team|on-call|oncall|owner"),
]

def completeness(text):
    found, missing = [], []
    for label, pattern in COMPLETENESS_CHECKS:
        (found if re.search(pattern, text, re.IGNORECASE) else missing).append(label)
    return int(len(found) / len(COMPLETENESS_CHECKS) * 100), missing

# Blocker vs Advisory split
def classify_finding(severity=None, status=None):
    if severity == "HIGH" or status == "NOT_MET":
        return "BLOCKER"
    return "ADVISORY"

# Weighted scoring — delegates to agents.orchestrator_agent.compute_score(),
# the single source of truth for weights/thresholds. (Previously this file
# had its own duplicate weight constants that had drifted out of sync with
# the orchestrator's — e.g. MEDIUM risk was -8 here vs -10 there — which
# meant the CLI and this UI could silently disagree on the same report's
# score/band. Fixed by removing the duplicate entirely.)
def compute_score(risk_f, comp_f, clarif):
    result = _orchestrator_compute_score(risk_f, comp_f, clarif)
    return result["score"], result["band"], result["deductions"]

def build_exec_summary(score, band, risk_f, comp_f, clarif, reviewer, role):
    blockers   = sum(1 for f in risk_f if f.get("severity") == "HIGH") + \
                 sum(1 for f in comp_f if f.get("status") == "NOT_MET")
    advisories = sum(1 for f in risk_f if f.get("severity") in ("MEDIUM","LOW")) + \
                 sum(1 for f in comp_f if f.get("status") == "UNCLEAR")
    high_gaps  = sum(1 for q in clarif if q.get("priority") == "HIGH")

    if band == "NOT_READY":
        verdict = f"Design must not proceed. {blockers} blocker(s) require resolution before re-review."
    elif band == "NEEDS_WORK":
        verdict = f"Design requires rework. {blockers} blocker(s) and {advisories} advisory finding(s) identified."
    else:
        verdict = f"Design provisionally acceptable. {advisories} advisory note(s) to acknowledge before sign-off."

    return (
        f"Reviewed by **{reviewer}** ({role}) · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  \n"
        f"Score **{score}/100** → {band.replace('_',' ')}  \n"
        f"{verdict}  \n"
        f"**{blockers}** blocker(s) · **{advisories}** advisory · **{high_gaps}** clarification gap(s) requiring response."
    )

# ── Good practices ─────────────────────────────────────────────────────────────
GOOD_PRACTICES = [
    {"area": "Authentication",
     "bad":  "Authentication approach not yet decided.",
     "good": "Auth: mTLS for all service-to-service calls. OAuth2 client credentials for external consumers.",
     "why":  "Undecided auth = HIGH risk. Name mechanism, not intent."},
    {"area": "Rollback Plan",
     "bad":  "Assumption is to fall back to old system — not confirmed with team.",
     "good": "Blue/green deployment. Rollback confirmed with ops team (sign-off: 2026-06-28). Feature flag controls cutover.",
     "why":  "Unconfirmed fallback = no fallback. Name mechanism + confirm with dependent team."},
    {"area": "Data Classification",
     "bad":  "Uses customer income and debt data. No new PII collected.",
     "good": "Classification: Confidential-Financial. DG review ref: DG-2026-047. No data at rest. TLS 1.3 in transit.",
     "why":  "State classification explicitly. Reference review. Mention encryption specifics."},
    {"area": "NFRs",
     "bad":  "Real-time scoring service required.",
     "good": "Availability: 99.95%. Latency: <30s. Scale: 10k events/min (load tested). Auto-scaling via K8s HPA.",
     "why":  "'Real-time' is not an NFR. Numbers + test evidence = credible."},
    {"area": "Security (OWASP/CWE)",
     "bad":  "Security will follow standard practices.",
     "good": "CWE-20, CWE-200, CWE-319 reviewed and mitigated. OWASP alignment confirmed (SR-2026-112).",
     "why":  "'Standard practices' = nothing. Name CWEs. Reference security review."},
    {"area": "Ownership",
     "bad":  "Team TBD.",
     "good": "Owning team: Fraud Engineering. On-call: PagerDuty 4-engineer rotation 24/7. Runbook: confluence/runbook.",
     "why":  "No owner = no production support. Name team, rotation, runbook."},
    {"area": "Audit Logging",
     "bad":  "Audit logging not mentioned.",
     "good": "Every decision logged to immutable store, 90-day retention. Human analyst can override via case UI.",
     "why":  "No audit log = compliance failure. State retention + human override path."},
    {"area": "Doc Versioning",
     "bad":  "No version or author on document.",
     "good": "Version: 2.1 | Author: Jane Smith | Date: 2026-07-01 | Supersedes: v2.0",
     "why":  "Real governance needs doc history. Version + author = audit trail starts at the doc."},
    {"area": "Mandatory vs Advisory",
     "bad":  "All findings listed equally — team unclear what blocks delivery.",
     "good": "BLOCKER: auth undefined (must fix). ADVISORY: CWE review pending (should fix before GA).",
     "why":  "Not all findings block delivery. Clear split = teams know exactly what stops them shipping."},
]

# ── Samples ────────────────────────────────────────────────────────────────────
samples = {
    "❌ Bad example"    : load("sample_bad.md"),
    "⚠️ Decent example" : load("sample_decent.md"),
    "✅ Good example"   : load("sample_good.md"),
    "📋 Template"       : load("design_doc_template.md"),
    "Blank"             : "",
}

ROLES = [
    "Architect",
    "Tech Lead",
    "Delivery Manager",
    "Security Reviewer",
    "Business Analyst",
    "Other",
]

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="archguard-header">
  <h1>🏛️ ArchGuard</h1>
  <p>AI-assisted architecture governance for regulated environments.<br>
  Submit a design doc → three specialist agents review risk, compliance, and readiness
  → structured verdict with score, prioritised actions, and full audit trail.<br>
  <strong>Human sign-off always required. No design approved autonomously.</strong></p>
  <div class="archguard-badges">
    <span class="badge">⚡ Google ADK Multi-Agent</span>
    <span class="badge">🔌 MCP Policy Server</span>
    <span class="badge">🔒 Human-in-the-Loop Guardrail</span>
    <span class="badge">📋 OWASP · CWE · Definition of Ready</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📚 Good Practices Guide")
    st.caption("What strong design docs look like — criterion by criterion.")
    for gp in GOOD_PRACTICES:
        with st.expander(f"✅ {gp['area']}"):
            st.markdown("**❌ Weak:**")
            st.markdown(f'<div class="gp-bad">{gp["bad"]}</div>', unsafe_allow_html=True)
            st.markdown("**✅ Strong:**")
            st.markdown(f'<div class="gp-good">{gp["good"]}</div>', unsafe_allow_html=True)
            st.caption(f"💡 {gp['why']}")

    st.divider()
    st.markdown("### 🕓 Review History")
    if not st.session_state.history:
        st.caption("No reviews yet this session.")
    else:
        for h in reversed(st.session_state.history[-5:]):
            icon = {"READY_WITH_NOTES":"✅","NEEDS_WORK":"⚠️","NOT_READY":"❌"}.get(h["band"],"?")
            st.markdown(
                f'<div class="history-item">{icon} <strong>{h["score"]}/100</strong> · {h["band"].replace("_"," ")}<br>'
                f'<small>{h["design"][:35]}...</small><br>'
                f'<small style="color:#94a3b8">{h["reviewer"]} · {h["time"]}</small></div>',
                unsafe_allow_html=True)

# ── Main columns ───────────────────────────────────────────────────────────────
col_in, col_out = st.columns([1, 1], gap="large")

with col_in:
    st.markdown("### 📄 Submit Design Document")
    st.caption(
        "Paste, upload, or choose an example. More complete doc → more actionable review. "
        "See **Good Practices** (sidebar) for what each section should contain."
    )

    # Reviewer identity
    rc1, rc2 = st.columns([1,1])
    with rc1:
        reviewer_name = st.text_input("Reviewer name", placeholder="e.g. Priya Balakrishnan")
    with rc2:
        reviewer_role = st.selectbox("Role", ROLES)

    if reviewer_role == "Other":
        reviewer_role = st.text_input("Specify role", placeholder="e.g. Platform Engineer")

    st.divider()

    prefill    = st.selectbox("Load example or template:", list(samples.keys()))
    design_doc = st.text_area(
        "Design document",
        value=samples[prefill],
        height=340,
        placeholder="Paste or type your architecture design document here...",
        label_visibility="collapsed",
    )

    uploaded = st.file_uploader("Or upload .md / .txt:", type=["md","txt"])
    if uploaded:
        design_doc = uploaded.read().decode()
        st.success(f"Loaded: {uploaded.name}")

    if design_doc.strip():
        wc = word_count(design_doc)
        comp_score, missing = completeness(design_doc)
        st.markdown("**Doc completeness:**")
        st.progress(comp_score / 100, text=f"{comp_score}% · {wc} words")
        if missing:
            st.caption(f"Missing: {', '.join(missing)}")
        else:
            st.caption("✅ All key sections detected.")

    st.divider()
    human_sign_off = st.checkbox(
        "✅ I confirm human sign-off for this review",
        help="Required. No design approved without explicit human confirmation."
    )

    reviewer_ready = bool(reviewer_name.strip()) if reviewer_name else False
    run_btn = st.button(
        "🔍 Run Governance Review",
        type="primary",
        use_container_width=True,
        disabled=not (design_doc.strip() and reviewer_ready),
    )
    if not reviewer_ready:
        st.caption("⚠️ Enter reviewer name to enable review.")

# ── Results ────────────────────────────────────────────────────────────────────
with col_out:
    st.markdown("### 📊 Readiness Report")

    if run_btn:
        status_box = st.empty()
        for step in [
            "🔴 Risk Agent reviewing security, integration & data risk...",
            "📋 Compliance Agent checking governance checklists via MCP...",
            "❓ Clarification Agent identifying gaps...",
            "🔒 Applying guardrail & compiling report...",
        ]:
            status_box.info(step)

        try:
            from main import run_pipeline
            from security.audit import new_run_id
            run_id = new_run_id()
            report = asyncio.run(run_pipeline(design_doc, run_id))
        except Exception as e:
            status_box.empty()
            st.error(f"Agent error: {e}")
            st.stop()

        status_box.empty()

        if human_sign_off:
            report["human_sign_off"] = True
            report.pop("guardrail", None)

        report["reviewer"]         = reviewer_name
        report["reviewer_role"]    = reviewer_role
        report["review_timestamp"] = datetime.now(timezone.utc).isoformat()
        design_title = design_doc.splitlines()[0].strip("# ").strip()[:40]

        risk_f  = report.get("risk_findings", [])
        comp_f  = report.get("compliance_findings", [])
        clarif  = report.get("clarifications_needed", [])
        score, band, breakdown = compute_score(risk_f, comp_f, clarif)
        report["readiness_score"] = score
        report["readiness"]       = band
        report["score_breakdown"] = breakdown

        # Persist everything needed to re-render this result across future
        # reruns — Streamlit reruns the whole script when a download_button
        # is clicked, and run_btn (a one-shot st.button()) goes back to
        # False on that rerun. Without this, the results panel would wipe
        # itself back to the "not run yet" message the moment someone
        # downloaded a report. Only a fresh "Run Governance Review" click
        # (the `if run_btn:` block above) overwrites this.
        st.session_state.last_result = {
            "report": report,
            "run_id": run_id,
            "design_title": design_title,
            "reviewer_name": reviewer_name,
            "reviewer_role": reviewer_role,
        }
        st.session_state.history.append({
            "design": design_title, "score": score, "band": band,
            "reviewer": reviewer_name,
            "time": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        })

    if "last_result" not in st.session_state:
        st.info(
            "Enter reviewer details + design document → click **Run Governance Review**.\n\n"
            "**How it works:**\n"
            "1. 🔴 **Risk Agent** — scans security, integration, data, operational risk\n"
            "2. 📋 **Compliance Agent** — checks live governance checklists via MCP\n"
            "3. ❓ **Clarification Agent** — flags gaps blocking safe go/no-go\n"
            "4. 🔒 **Guardrail** — blocks autonomous approval. Human sign-off always required.\n\n"
            "Findings split into **Blockers** (must fix) and **Advisory** (should fix)."
        )
    else:
        bundle        = st.session_state.last_result
        report        = bundle["report"]
        run_id        = bundle["run_id"]
        design_title  = bundle["design_title"]
        reviewer_name = bundle["reviewer_name"]
        reviewer_role = bundle["reviewer_role"]

        risk_f  = report.get("risk_findings", [])
        comp_f  = report.get("compliance_findings", [])
        clarif  = report.get("clarifications_needed", [])

        score, band, breakdown = compute_score(risk_f, comp_f, clarif)
        report["readiness_score"]  = score
        report["readiness"]        = band
        report["score_breakdown"]  = breakdown
        report["reviewer"]         = reviewer_name
        report["reviewer_role"]    = reviewer_role

        band_config = {
            "READY_WITH_NOTES": ("✅ READY WITH NOTES", "#22c55e"),
            "NEEDS_WORK":       ("⚠️ NEEDS WORK",       "#f59e0b"),
            "NOT_READY":        ("❌ NOT READY",         "#ef4444"),
        }
        band_label, band_color = band_config.get(band, (band, "#6b7280"))

        # Score
        st.markdown(
            f'<div class="score-ring" style="color:{band_color}">{score}</div>'
            f'<div class="band-label" style="color:{band_color}">{band_label}</div>',
            unsafe_allow_html=True)

        # Metrics
        blockers   = sum(1 for f in risk_f if f.get("severity")=="HIGH") + \
                     sum(1 for f in comp_f if f.get("status")=="NOT_MET")
        advisories = sum(1 for f in risk_f if f.get("severity") in ("MEDIUM","LOW")) + \
                     sum(1 for f in comp_f if f.get("status")=="UNCLEAR")
        gap_c      = sum(1 for q in clarif if q.get("priority")=="HIGH")

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f'<div class="metric-box"><div class="val" style="color:#ef4444">{blockers}</div><div class="lbl">Blockers</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-box"><div class="val" style="color:#f59e0b">{advisories}</div><div class="lbl">Advisory</div></div>', unsafe_allow_html=True)
        with m3:
            st.markdown(f'<div class="metric-box"><div class="val" style="color:#3b82f6">{gap_c}</div><div class="lbl">High Gaps</div></div>', unsafe_allow_html=True)

        st.divider()

        # Risk Heatmap — domain x severity, visual-only for now. Streamlit's
        # st.plotly_chart(..., on_select=...) click-to-filter behavior isn't
        # consistent enough across 1.35+ minor versions to ship blind; this
        # renders the chart with no click interaction until that's verified
        # against the actual installed Streamlit version.
        st.markdown("#### 🗺️ Risk Heatmap")
        hm = build_heatmap_matrix(risk_f, comp_f)
        z = hm["matrix"]
        cell_text = [[str(c) if c else "" for c in row] for row in z]
        heatmap_fig = go.Figure(data=go.Heatmap(
            z=z,
            x=hm["severities"],
            y=hm["domains"],
            text=cell_text,
            texttemplate="%{text}",
            textfont={"size": 14, "color": "#1e293b"},
            colorscale=[[0, "#f0fdf4"], [0.5, "#f59e0b"], [1, "#ef4444"]],
            zmin=0, zmax=2,
            showscale=False,
            hovertemplate="%{y} · %{x}: %{z}<extra></extra>",
            xgap=3, ygap=3,
        ))
        heatmap_fig.update_layout(
            margin=dict(l=10, r=10, t=30, b=10),
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=12, color="#475569"),
            xaxis=dict(side="top"),
        )
        st.plotly_chart(heatmap_fig, use_container_width=True, config={"displayModeBar": False})
        st.caption(
            "Risk findings counted by severity · compliance NOT_MET → HIGH column, "
            "UNCLEAR → MEDIUM column. MET criteria excluded (see Green Path below)."
        )

        # Green Path — positive signals, shown before the Executive Summary.
        # Hidden entirely when there are no positive signals. Collapsed by
        # default unless the design is READY_WITH_NOTES, to keep focus on
        # blockers otherwise.
        positives = green_path(risk_f, comp_f)
        if positives:
            with st.expander(f"🟢 Green Path — What's Working ({len(positives)})", expanded=(band == "READY_WITH_NOTES")):
                for p in positives:
                    st.markdown(f'<div class="gp-good">{p}</div>', unsafe_allow_html=True)

        st.divider()

        # Executive summary
        exec_summary = build_exec_summary(score, band, risk_f, comp_f, clarif, reviewer_name, reviewer_role)
        st.markdown("#### 📋 Executive Summary")
        st.markdown(f'<div class="exec-summary"><p>{exec_summary}</p></div>', unsafe_allow_html=True)

        # What to fix first — each blocker now carries a suggested next
        # action from domain_utils.next_action(). Clarification-gap items
        # have no domain, so they get no action line (None → omitted).
        priority_actions = []
        for f in risk_f:
            if f.get("severity") == "HIGH":
                priority_actions.append(("BLOCKER", f"[{f.get('area')}] {f.get('recommendation','')}", next_action(f)))
        for f in comp_f:
            if f.get("status") == "NOT_MET":
                priority_actions.append(("BLOCKER", f"[Compliance] {f.get('criterion','')} — {f.get('evidence_or_gap','')}", next_action(f)))
        for q in clarif:
            if q.get("priority") == "HIGH" and len(priority_actions) < 5:
                priority_actions.append(("BLOCKER", f"[Clarify] {q.get('question','')}", None))

        if priority_actions:
            with st.expander("🎯 What to Fix First", expanded=True):
                for i, (tag, action, suggested_action) in enumerate(priority_actions[:5], 1):
                    color = "#ef4444" if tag == "BLOCKER" else "#f59e0b"
                    action_line = (
                        f'<br><em style="color:#64748b;font-size:0.82rem">→ Action: {suggested_action}</em>'
                        if suggested_action else ""
                    )
                    st.markdown(
                        f'<div class="priority-item"><span style="color:{color};font-weight:700">[{tag}]</span> '
                        f'<strong>{i}.</strong> {action}{action_line}</div>',
                        unsafe_allow_html=True)

        # Blockers vs Advisory
        blocker_risks   = [f for f in risk_f if classify_finding(severity=f.get("severity")) == "BLOCKER"]
        advisory_risks  = [f for f in risk_f if classify_finding(severity=f.get("severity")) == "ADVISORY"]
        blocker_comp    = [f for f in comp_f if classify_finding(status=f.get("status")) == "BLOCKER"]
        advisory_comp   = [f for f in comp_f if classify_finding(status=f.get("status")) == "ADVISORY"]

        # Domain iteration order for both expanders below: the 6 canonical
        # domains, then an Unclassified tail if anything didn't validate.
        DOMAIN_ITER_ORDER = DOMAINS + ["Unclassified"]

        if blocker_risks or blocker_comp:
            with st.expander(f"🚫 Blockers — Must Fix ({len(blocker_risks)+len(blocker_comp)})", expanded=True):
                grouped_risks = group_by_domain(blocker_risks)
                grouped_comp = group_by_domain(blocker_comp)
                for domain in DOMAIN_ITER_ORDER:
                    d_risks = grouped_risks.get(domain, [])
                    d_comp = grouped_comp.get(domain, [])
                    if not d_risks and not d_comp:
                        continue
                    st.markdown(f"#### 🔴 {domain}")
                    for f in d_risks:
                        st.markdown(
                            f'<div class="blocker-card"><strong>🔴 [{f.get("area","")}]</strong> {f.get("finding","")}<br>'
                            f'<em>→ {f.get("recommendation","")}</em></div>',
                            unsafe_allow_html=True)
                    for f in d_comp:
                        st.markdown(
                            f'<div class="blocker-card"><strong>🔴 [Compliance]</strong> {f.get("criterion","")}<br>'
                            f'<em>Gap: {f.get("evidence_or_gap","")}</em></div>',
                            unsafe_allow_html=True)

        if advisory_risks or advisory_comp:
            with st.expander(f"⚠️ Advisory — Should Fix ({len(advisory_risks)+len(advisory_comp)})"):
                grouped_risks = group_by_domain(advisory_risks)
                grouped_comp = group_by_domain(advisory_comp)
                for domain in DOMAIN_ITER_ORDER:
                    d_risks = grouped_risks.get(domain, [])
                    d_comp = grouped_comp.get(domain, [])
                    if not d_risks and not d_comp:
                        continue
                    st.markdown(f"#### 🟡 {domain}")
                    for f in d_risks:
                        st.markdown(
                            f'<div class="advisory-card"><strong>⚠️ [{f.get("area","")}]</strong> {f.get("finding","")}<br>'
                            f'<em>→ {f.get("recommendation","")}</em></div>',
                            unsafe_allow_html=True)
                    for f in d_comp:
                        st.markdown(
                            f'<div class="advisory-card"><strong>⚠️ [Compliance]</strong> {f.get("criterion","")}<br>'
                            f'<em>Gap: {f.get("evidence_or_gap","")}</em></div>',
                            unsafe_allow_html=True)

        # Met criteria
        met_f = [f for f in comp_f if f.get("status") == "MET"]
        if met_f:
            with st.expander(f"✅ Criteria Met ({len(met_f)})"):
                for f in met_f:
                    st.markdown(
                        f'<div class="finding-card MET"><strong>✅ {f.get("criterion","")}</strong><br>'
                        f'<small>{f.get("evidence_or_gap","")}</small></div>',
                        unsafe_allow_html=True)

        # Clarifications
        if clarif:
            high_q = [q for q in clarif if q.get("priority") == "HIGH"]
            with st.expander(f"❓ Clarifications Needed ({len(high_q)} high priority)"):
                for i, q in enumerate(clarif, 1):
                    icon = "🔴" if q.get("priority") == "HIGH" else "🟡"
                    st.markdown(
                        f'<div class="question-item">{icon} <strong>{i}. {q.get("related_to","")}</strong><br>'
                        f'{q.get("question","")}</div>', unsafe_allow_html=True)

        # Score breakdown
        with st.expander("📉 Score Breakdown"):
            st.markdown(f"- Risk deductions: **-{breakdown.get('risk',0)} pts**")
            st.markdown(f"- Compliance deductions: **-{breakdown.get('compliance',0)} pts**")
            st.markdown(f"- Clarification gaps: **-{breakdown.get('clarification',0)} pts**")
            st.markdown(f"- **Final score: {score}/100**")
            st.caption("HIGH risk = -25pts · MEDIUM = -10pts · LOW = -3pts · NOT_MET = -15pts · UNCLEAR = -5pts")

        guardrail = report.get("guardrail")
        if guardrail:
            st.markdown(f'<div class="guardrail-box">🔒 GUARDRAIL ACTIVE<br>{guardrail}</div>', unsafe_allow_html=True)
        else:
            st.success("✅ Human sign-off confirmed. Review complete.")

        st.caption(f"Audit log: `{report.get('audit_log_ref','')}`")

        # Report MD for download
        review_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        report_md = f"""# ArchGuard Governance Review
**Design:** {design_title}  
**Reviewer:** {reviewer_name} ({reviewer_role})  
**Date:** {review_time}  
**Score:** {score}/100 — {band_label}

## Executive Summary
{exec_summary}

## Blockers — Must Fix
{chr(10).join(f'- 🔴 [{f.get("area","")}] {f.get("finding","")} → {f.get("recommendation","")}' for f in blocker_risks)}
{chr(10).join(f'- 🔴 [Compliance] {f.get("criterion","")} — {f.get("evidence_or_gap","")}' for f in blocker_comp)}

## Advisory — Should Fix
{chr(10).join(f'- ⚠️ [{f.get("area","")}] {f.get("finding","")}' for f in advisory_risks)}
{chr(10).join(f'- ⚠️ [Compliance] {f.get("criterion","")}' for f in advisory_comp)}

## Top Clarifications
{chr(10).join(f'{i+1}. {q.get("question","")}' for i,q in enumerate([q for q in clarif if q.get("priority")=="HIGH"][:5]))}

## Score Breakdown
- Risk: -{breakdown.get('risk',0)} pts  
- Compliance: -{breakdown.get('compliance',0)} pts  
- Clarification: -{breakdown.get('clarification',0)} pts  
- **Final: {score}/100**

*Audit log: {report.get('audit_log_ref','')}*  
*Human sign-off required before approval is actioned.*
"""
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("⬇️ Download JSON",
                data=json.dumps(report, indent=2),
                file_name=f"archguard_{run_id}.json",
                mime="application/json", use_container_width=True)
        with c2:
            st.download_button("📋 Download Report (MD)",
                data=report_md,
                file_name=f"archguard_{run_id}.md",
                mime="text/markdown", use_container_width=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer">
    Built with <strong>Google Agent Development Kit (ADK)</strong> ·
    <strong>Gemini 2.5 Flash</strong> ·
    <strong>MCP Policy Server</strong> ·
    <strong>Streamlit</strong><br>
    Human-in-the-loop guardrail active on every review. No design approved autonomously.
</div>
""", unsafe_allow_html=True)