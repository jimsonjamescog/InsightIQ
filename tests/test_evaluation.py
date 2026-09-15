from insightiq.evaluation.runner import evaluate


def test_evaluation_has_no_unsupported_evidence():
    metrics = evaluate()
    assert metrics["passed_evidence_gate"] is True
    assert metrics["hypothesis_rejection_accuracy"] == 1.0
    assert metrics["evidence_traceability_rate"] == 1.0
    assert metrics["unsupported_evidence_rate"] == 0.0
