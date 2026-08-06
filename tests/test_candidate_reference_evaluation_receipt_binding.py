from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_candidate_reference_evaluation import _request, _synthesis

from ctrt.candidate_reference_evaluation import (
    CandidateReferenceEvaluationError,
    run_candidate_reference_evaluation,
)


def test_included_population_cannot_be_removed_to_bypass_fixture_gate(
    tmp_path: Path,
) -> None:
    human_workspace = tmp_path / "human"
    synthesis = _synthesis(human_workspace)
    drifted = replace(synthesis, included=())

    with pytest.raises(
        CandidateReferenceEvaluationError,
        match="included collection identities differ",
    ):
        run_candidate_reference_evaluation(
            _request(tmp_path, human_workspace),
            synthesis=drifted,
        )
