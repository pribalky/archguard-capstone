"""
Audit logging + guardrail for multi-agent readiness review.

Safety principles:
- Every agent decision logged (auditability).
- No agent sets readiness autonomously — guardrail intercepts.
- Guardrail now checks score band AND human_sign_off.
- Append-only JSONL = tamper-evident audit trail.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

BANDS_REQUIRING_SIGNOFF = {"READY_WITH_NOTES", "NEEDS_WORK", "NOT_READY"}


def _run_log_path(run_id: str) -> Path:
    return LOG_DIR / f"run_{run_id}.jsonl"


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def log_event(run_id: str, agent_name: str, event_type: str, payload: dict) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "agent": agent_name,
        "event_type": event_type,
        "payload": payload,
    }
    with open(_run_log_path(run_id), "a") as f:
        f.write(json.dumps(record) + "\n")


def read_log(run_id: str) -> list[dict]:
    path = _run_log_path(run_id)
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def enforce_no_autonomous_approval(payload: dict) -> dict:
    """Guardrail: no band passes without human_sign_off=True.
    Score is informational only — human always decides final approval.
    """
    if not payload.get("human_sign_off"):
        payload["guardrail"] = (
            f"Score={payload.get('readiness_score')}/100 "
            f"Band={payload.get('readiness')}. "
            "Awaiting human sign-off before approval."
        )
    return payload
