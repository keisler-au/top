"""Versioned, server-computed taxonomy release-gate policy.

The gate deliberately accepts aggregate facts only. It has no request model
and no operator-supplied release signals: those would make a release decision
non-reproducible and bypass the durable candidate record.
"""

from triage_processor.taxonomy_stage_quality import (
    THRESHOLDS,
    THRESHOLD_VERSION,
    attestation_input_sha256,
    evaluate_computed_gate,
)

__all__ = [
    "THRESHOLDS",
    "THRESHOLD_VERSION",
    "attestation_input_sha256",
    "evaluate_computed_gate",
]
