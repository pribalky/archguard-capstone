# ArchGuard — Architecture Readiness Review — Multi-Agent System

A multi-agent system that reviews a proposed solution/architecture design doc
and produces a structured **readiness report** — flagging risk, compliance,
and information gaps, grouped by governance domain, before a design goes to
governance sign-off.

Built for: Google **"5-Day AI Agents: Intensive Vibe Coding Course"** —
**Agents for Business** track, Capstone submission.

> 🔗 **Live demo:** _add your Streamlit Community Cloud URL here_
> 🎥 **Video walkthrough:** _add your video link here_

## Why this project

This encodes a real workflow: architecture governance review in a regulated
(banking) environment. Instead of one human manually checking a design
against multiple checklists, specialist agents each own one lens, and an
orchestrator compiles their findings into a single auditable report. The
system is designed to **assist**, never **auto-approve** — every readiness
verdict requires explicit human sign-off.

## The 3 concepts demonstrated

1. **Multi-agent system (Google ADK)** — an orchestrator agent (`SequentialAgent`)
   routes a design doc to three specialist sub-agents (Risk, Compliance,
   Clarification) and merges their outputs into one report. See `agents/`.
2. **MCP server integration** — a policy/checklist repository is exposed as an
   MCP server (`mcp_server/policy_server.py`). The Compliance Agent calls it
   live over stdio as a tool instead of having checklist criteria hardcoded
   into a prompt — so the rules can be updated independently of the agent
   logic.
3. **Security / safety features** — guardrails preventing autonomous
   approval, full audit logging of every agent decision + rationale, and a
   required human-sign-off field before any design can be marked "ready."
   See `security/audit.py` and the orchestrator's guardrail logic.

## What makes this more than a checklist bot

- **6-domain governance taxonomy** (Security, Data, Integration, Ops,
  Compliance, Architecture) tags every finding — from the MCP checklist
  criteria, through the Risk Agent's own assessment, all the way to the UI.
  See `agents/domain_utils.py`.
- **Risk heatmap** — a domain × severity matrix (Plotly) gives reviewers an
  at-a-glance view of where the real exposure is concentrated.
- **Green Path** — the report doesn't only list what's wrong; it surfaces
  what the design already got right (`MET` criteria, `LOW`-risk findings),
  so governance reviews aren't purely a wall of red.
- **Rule-based next actions** — every blocker gets a concrete suggested next
  step ("Book security design review," "Escalate to data governance," etc.)
  derived from a deterministic, auditable rule table — not another LLM call.
- **Single source of truth for scoring** — one weighted-scoring function
  (`agents/orchestrator_agent.compute_score`) is shared by both the CLI and
  the Streamlit UI, so they can never silently disagree on a verdict.

## Architecture

```
                 ┌──────────────────────┐
   design doc -> │  Orchestrator Agent  │ -> Readiness Report (JSON + summary)
                 └──────────┬───────────┘
                             │ routes to
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
    ┌─────────────┐  ┌────────────────┐  ┌─────────────────────┐
    │ Risk Agent  │  │ Compliance     │  │ Clarification        │
    │             │  │ Agent          │  │ Agent                 │
    │ security,   │  │ calls MCP      │  │ flags missing         │
    │ integration,│  │ policy_server  │  │ info, asks targeted   │
    │ ops, data   │  │ for checklist  │  │ follow-up questions   │
    │ risk        │  │ ({text,domain})│  │                       │
    └─────────────┘  └────────────────┘  └─────────────────────┘
                             │
                     every step logged ->  security/audit.py
                     (no auto-approval; human_sign_off required)
                             │
                             ▼
                  agents/domain_utils.py
          (domain grouping, heatmap matrix, next-action
                 rules, green-path extraction)
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
              main.py (CLI)          app.py (Streamlit UI)
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add your GEMINI_API_KEY
```

## Run — CLI

```bash
python main.py --input examples/sample_good.md
python main.py --input examples/sample_bad.md
```

## Run — Streamlit UI

```bash
streamlit run app.py
```

Includes: score ring + band, blocker/advisory metrics, a domain × severity
risk heatmap, a "Green Path" of positive signals, "What to Fix First" with
suggested next actions, domain-grouped Blockers/Advisory sections, and
JSON/Markdown report downloads.

## Testing

```bash
# Fast, pure-Python unit tests (no API calls, <1s)
python -m pytest tests/test_domain_utils.py -v

# Full pipeline regression check (needs a live GEMINI_API_KEY)
python evaluation/eval_harness.py
```

## Output

A structured JSON report + a human-readable summary, e.g.:

```json
{
  "design": "Customer Risk Scoring Service v2",
  "risk_findings": [ { "area": "...", "domain": "Security", "severity": "HIGH", "...": "..." } ],
  "compliance_findings": [ { "checklist": "...", "domain": "Compliance", "status": "NOT_MET", "...": "..." } ],
  "clarifications_needed": [ "..." ],
  "readiness": "NOT_READY",
  "human_sign_off_required": true,
  "audit_log_ref": "logs/run_2026-07-04T18-00-00.jsonl"
}
```

## Project structure

```
agents/
  orchestrator_agent.py   # SequentialAgent pipeline + compute_score (single source of truth)
  risk_agent.py            # security/integration/ops/data risk assessment
  compliance_agent.py      # checks live MCP checklists, attaches domain
  clarification_agent.py   # flags information gaps
  domain_utils.py           # pure-Python: grouping, heatmap, next actions, green path
mcp_server/
  policy_server.py          # governance checklists served over MCP (stdio)
policies/
  *.md                      # human-readable checklist source of truth (domain-tagged)
security/
  audit.py                  # guardrail + append-only audit logging
tests/
  test_domain_utils.py       # unit tests for domain_utils.py
evaluation/
  eval_harness.py            # labelled-case regression tests against the live pipeline
main.py                      # CLI entrypoint
app.py                        # Streamlit UI
```

## What I'd improve with more time

- Add ADK session/memory support so a reviewer's prior clarifications persist
  across a design doc's revision history (Day 3 "Agent Skills" territory —
  not yet demonstrated in this build).
- Parse the `policies/*.md` files directly instead of maintaining their
  domain tags in parallel with `mcp_server/policy_server.py`'s `CHECKLISTS`
  dict — right now the `.md` files are documentation-only.
- Click-to-filter interactivity on the Streamlit risk heatmap (shipped
  visual-only for now, pending a Streamlit `on_select` version check).
- Replace the mock MCP policy server with a real connection to a live
  governance doc repository (Drive/Confluence via MCP).

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

Built as a capstone project for Google & Kaggle's **5-Day AI Agents:
Intensive Vibe Coding Course** (Agents for Business track).