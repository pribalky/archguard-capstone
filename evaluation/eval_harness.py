"""
Eval harness — runs agent pipeline against labelled test cases,
scores output vs expected, prints pass/fail per test.

Run:
    python evaluation/eval_harness.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import run_pipeline
from security.audit import new_run_id

LABELLED_DIR = Path(__file__).parent / "labelled"


def score(report: dict, expected: dict) -> dict:
    results = {}

    # 1. Readiness verdict match
    results["readiness_match"] = (
        report.get("readiness") == expected.get("expected_readiness")
    )

    # 2. HIGH risk areas surfaced
    expected_high = set(expected.get("expected_high_risk_areas", []))
    actual_high = {
        f["area"]
        for f in report.get("risk_findings", [])
        if f.get("severity") == "HIGH"
    }
    results["high_risk_areas_hit"] = expected_high.issubset(actual_high)
    results["missing_high_risk"] = list(expected_high - actual_high)

    # 3. NOT_MET criteria surfaced
    expected_not_met = set(expected.get("expected_not_met_criteria", []))
    actual_not_met = {
        f["criterion"]
        for f in report.get("compliance_findings", [])
        if f.get("status") == "NOT_MET"
    }
    results["not_met_criteria_hit"] = expected_not_met.issubset(actual_not_met)
    results["missing_not_met"] = list(expected_not_met - actual_not_met)

    # Overall pass
    results["passed"] = all([
        results["readiness_match"],
        results["high_risk_areas_hit"],
        results["not_met_criteria_hit"],
    ])
    return results


async def run_test(test_path: Path) -> dict:
    expected = json.loads(test_path.read_text())
    run_id = new_run_id()
    report = await run_pipeline(expected["design_doc"], run_id)
    scored = score(report, expected)
    return {
        "test_id": expected["id"],
        "description": expected["description"],
        "score": scored,
    }


async def main():
    test_files = sorted(LABELLED_DIR.glob("*.json"))
    if not test_files:
        print("No labelled test cases found in evaluation/labelled/")
        return

    results = []
    for tf in test_files:
        print(f"Running {tf.name}...")
        result = await run_test(tf)
        results.append(result)
        status = "PASS ✅" if result["score"]["passed"] else "FAIL ❌"
        print(f"  {status} — {result['description']}")
        if not result["score"]["passed"]:
            print(f"  missing_high_risk: {result['score']['missing_high_risk']}")
            print(f"  missing_not_met:   {result['score']['missing_not_met']}")

    total = len(results)
    passed = sum(1 for r in results if r["score"]["passed"])
    print(f"\n{passed}/{total} tests passed")


if __name__ == "__main__":
    asyncio.run(main())
