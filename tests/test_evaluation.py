from __future__ import annotations

from day37_bank_qa.evaluation import EVALUATION_CASES, run_offline_evaluation


def test_offline_evaluation_harness_meets_every_hard_gate() -> None:
    report = run_offline_evaluation()

    assert len(EVALUATION_CASES) == 4
    assert report["total"] == 4
    assert report["passed"] == 4
    assert report["score"] == 1.0
    assert all(result["passed"] for result in report["results"])
