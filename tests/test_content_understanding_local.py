from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from ctrt.content_understanding import ReaderProvidedContext
from ctrt.content_understanding_local import (
    LOCAL_CONTENT_UNDERSTANDING_VERSION,
    LocalContentUnderstandingError,
    LocalContentUnderstandingRequest,
    main,
    run_local_content_understanding,
)
from ctrt.creator_preflight_local import (
    ABSTENTION_CONTROL_TEXT,
    DEFAULT_CANDIDATE_REGISTRY,
    DEFAULT_METHOD_REGISTRY,
    DISAGREEMENT_CONTROL_TEXT,
)
from ctrt.eligible_extraction_evidence import (
    build_eligible_extraction_evidence_view,
)
from ctrt.eligible_extraction_runner import EligibleExtractionExperimentError


def _request(
    tmp_path: Path,
    *,
    content: str = "This plan is good, but the delay feels bad.",
    token: str = "understand01",
    method_registry_path: Path = DEFAULT_METHOD_REGISTRY,
) -> LocalContentUnderstandingRequest:
    return LocalContentUnderstandingRequest(
        content_text=content,
        context=ReaderProvidedContext(
            purpose="Understand the contrast without deciding what anyone should do.",
            known_context="This was shared during a project discussion.",
            questions=("What context should be checked before interpreting it?",),
        ),
        workspace=tmp_path / "runs",
        run_token=token,
        started_at=datetime(2026, 8, 5, 21, 5, tzinfo=UTC),
        candidate_registry_path=DEFAULT_CANDIDATE_REGISTRY,
        method_registry_path=method_registry_path,
    )


def test_local_understanding_runs_authorized_extraction_and_renders_only_submission(
    tmp_path: Path,
) -> None:
    result = run_local_content_understanding(_request(tmp_path))

    assert result.interface_version == LOCAL_CONTENT_UNDERSTANDING_VERSION
    assert result.receipt.content_ids == (
        result.submitted_content_id,
        "control-disagreement-understand01",
        "control-abstention-understand01",
    )
    assert result.understanding_view.evidence.text == (
        "This plan is good, but the delay feels bad."
    )
    assert result.understanding_view.evidence.extraction_ref.startswith("extraction:")
    assert "content-item:" not in result.understanding_view.evidence.extraction_ref

    roles = tuple(item.role for item in result.understanding_view.evidence.artifact_refs)
    assert "source-artifact" in roles
    assert "extraction-manifest" in roles
    assert "extracted-content" in roles
    assert "canonical-content" in roles
    assert "session-receipt" in roles
    assert tuple(item.role for item in result.evidence_view.completion_refs) == (
        "eligible-extraction-completion",
        "extraction-bound-completion",
        "experiment-completion",
        "extraction-method-registry",
        "extraction-method-eligibility",
    )

    prompt_ids = tuple(
        item.prompt_id for item in result.understanding_view.reflection_prompts
    )
    assert "material-disagreement" in prompt_ids
    assert "comparison-abstention" in prompt_ids
    assert "calibration-boundary" in prompt_ids
    assert "source-context" in prompt_ids
    assert "discussion-without-presumption" in prompt_ids

    assert result.markdown.startswith("# Understand this content\n")
    assert "This plan is good, but the delay feels bad." in result.markdown
    assert "Reader-provided purpose, context, and questions are not verified evidence." in (
        result.markdown
    )
    assert DISAGREEMENT_CONTROL_TEXT not in result.markdown
    assert ABSTENTION_CONTROL_TEXT not in result.markdown
    assert "Safety classification:" not in result.markdown
    assert "Restriction recommendation:" not in result.markdown
    assert "Viewer profile:" not in result.markdown
    assert "Overall score:" not in result.markdown

    stored_bytes = b"\n".join(
        path.read_bytes()
        for path in result.artifact_directory.rglob("*")
        if path.is_file()
    )
    assert b"content-item:" not in stored_bytes


def test_local_understanding_preserves_agreement_and_abstention(tmp_path: Path) -> None:
    agreement = run_local_content_understanding(
        _request(
            tmp_path,
            content="The opening is good and the ending is good.",
            token="understand02",
        )
    )
    agreement_prompts = tuple(
        item.prompt_id for item in agreement.understanding_view.reflection_prompts
    )
    assert agreement.understanding_view.evidence.comparison.agreement_status == "agreement"
    assert "instrument-agreement" in agreement_prompts
    assert "material-disagreement" not in agreement_prompts

    no_signal = run_local_content_understanding(
        _request(
            tmp_path,
            content="A passage without the fixture vocabulary.",
            token="understand03",
        )
    )
    assert tuple(
        item.status for item in no_signal.understanding_view.evidence.measurements
    ) == ("abstained", "abstained")
    abstention_prompts = tuple(
        item.prompt_id for item in no_signal.understanding_view.reflection_prompts
    )
    assert "instrument-abstention" in abstention_prompts
    assert "comparison-abstention" in abstention_prompts
    assert "No overall CTRT score" in no_signal.markdown


def test_local_understanding_fails_closed_on_unauthorized_method_configuration(
    tmp_path: Path,
) -> None:
    document = cast(
        dict[str, Any],
        json.loads(DEFAULT_METHOD_REGISTRY.read_text(encoding="utf-8")),
    )
    methods = cast(list[dict[str, Any]], document["methods"])
    methods[0]["authorized_configuration_hashes"] = ["sha256:" + ("0" * 64)]
    changed_path = tmp_path / "unauthorized-method-registry.json"
    changed_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        EligibleExtractionExperimentError,
        match="configuration hash is not authorized",
    ):
        run_local_content_understanding(
            _request(
                tmp_path,
                token="understand04",
                method_registry_path=changed_path,
            )
        )


def test_local_understanding_rehashes_source_before_presentation(
    tmp_path: Path,
) -> None:
    result = run_local_content_understanding(
        _request(tmp_path, token="understand05")
    )
    reference = result.receipt.extraction_bound_receipt.source_artifact_refs[0]
    digest = reference.artifact_hash.removeprefix("sha256:")
    blob = result.artifact_directory / "blobs" / "sha256" / digest
    blob.write_bytes(b"{}")

    with pytest.raises(ArtifactIntegrityError, match="failed SHA-256"):
        build_eligible_extraction_evidence_view(
            receipt=result.receipt,
            artifact_store=FileSystemArtifactStore(result.artifact_directory),
        )


def test_local_understanding_cli_accepts_file_and_writes_markdown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = tmp_path / "content.txt"
    content.write_text(
        "The opening is good and the ending is good.",
        encoding="utf-8",
    )
    output = tmp_path / "understanding.md"

    status = main(
        [
            "--content-file",
            str(content),
            "--purpose",
            "Understand the wording before discussing it.",
            "--known-context",
            "It was shared in a project channel.",
            "--question",
            "What source context should be checked?",
            "--workspace",
            str(tmp_path / "cli-runs"),
            "--output",
            str(output),
            "--run-token",
            "understand06",
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert f"Wrote content understanding to {output}" in captured.out
    assert "Artifact store:" in captured.err
    markdown = output.read_text(encoding="utf-8")
    assert "The opening is good and the ending is good." in markdown
    assert "Understand the wording before discussing it." in markdown
    assert "The instruments agreed on this measured dimension" in markdown
    assert "CTRT helps you inspect the submitted content." in markdown
    assert "CTRT does not rank or select among these inspection paths:" in markdown


def test_local_understanding_rejects_invalid_input(tmp_path: Path) -> None:
    with pytest.raises(LocalContentUnderstandingError, match="content_text"):
        _request(tmp_path, content="   ")
    with pytest.raises(ValueError, match="run_token"):
        _request(tmp_path, token="../escape")
    with pytest.raises(ValueError, match="reader questions"):
        LocalContentUnderstandingRequest(
            content_text="Exact content.",
            context=ReaderProvidedContext(
                purpose="Understand it.",
                questions=("Not a question",),
            ),
            workspace=tmp_path,
            run_token="understand07",
            started_at=datetime(2026, 8, 5, 21, 5, tzinfo=UTC),
        )


def test_local_understanding_exports_only_bounded_surface() -> None:
    import ctrt.content_understanding_local as module

    assert module.__all__ == [
        "LOCAL_CONTENT_UNDERSTANDING_VERSION",
        "LocalContentUnderstandingError",
        "LocalContentUnderstandingRequest",
        "LocalContentUnderstandingResult",
        "main",
        "run_local_content_understanding",
    ]
