from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from ctrt.creator_preflight import CreatorProvidedContext
from ctrt.creator_preflight_local import (
    ABSTENTION_CONTROL_TEXT,
    DEFAULT_CANDIDATE_REGISTRY,
    DEFAULT_METHOD_REGISTRY,
    DISAGREEMENT_CONTROL_TEXT,
    LocalCreatorPreflightError,
    LocalCreatorPreflightRequest,
    main,
    run_local_creator_preflight,
)
from ctrt.eligible_extraction_evidence import (
    build_eligible_extraction_evidence_view,
)
from ctrt.eligible_extraction_runner import EligibleExtractionExperimentError


def _request(
    tmp_path: Path,
    *,
    draft: str = "This plan is good, but the delay feels bad.",
    token: str = "localtest01",
    method_registry_path: Path = DEFAULT_METHOD_REGISTRY,
) -> LocalCreatorPreflightRequest:
    return LocalCreatorPreflightRequest(
        draft_text=draft,
        context=CreatorProvidedContext(
            intent="Explain both the promise and the concern.",
            intended_audience="Project collaborators",
            concerns=("The contrast may be stronger than intended.",),
        ),
        workspace=tmp_path / "runs",
        run_token=token,
        started_at=datetime(2026, 8, 5, 16, 0, tzinfo=UTC),
        candidate_registry_path=DEFAULT_CANDIDATE_REGISTRY,
        method_registry_path=method_registry_path,
    )


def test_local_interface_runs_authorized_extraction_and_renders_only_draft(
    tmp_path: Path,
) -> None:
    result = run_local_creator_preflight(_request(tmp_path))

    assert result.receipt.content_ids == (
        result.draft_content_id,
        "control-disagreement-localtest01",
        "control-abstention-localtest01",
    )
    assert result.preflight_view.evidence.text == (
        "This plan is good, but the delay feels bad."
    )
    assert result.preflight_view.evidence.extraction_ref.startswith("extraction:")
    assert "content-item:" not in result.preflight_view.evidence.extraction_ref

    roles = tuple(item.role for item in result.preflight_view.evidence.artifact_refs)
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
        item.prompt_id for item in result.preflight_view.reflection_prompts
    )
    assert "material-disagreement" in prompt_ids
    assert "comparison-abstention" in prompt_ids
    assert "calibration-boundary" in prompt_ids

    assert result.markdown.startswith("# Check before I publish\n")
    assert "This plan is good, but the delay feels bad." in result.markdown
    assert "Explain both the promise and the concern." in result.markdown
    assert "Creator-provided context is not verified evidence." in result.markdown
    assert DISAGREEMENT_CONTROL_TEXT not in result.markdown
    assert ABSTENTION_CONTROL_TEXT not in result.markdown
    assert "Publish recommendation:" not in result.markdown
    assert "Overall score:" not in result.markdown
    assert "Safe / unsafe:" not in result.markdown

    stored_bytes = b"\n".join(
        path.read_bytes()
        for path in result.artifact_directory.rglob("*")
        if path.is_file()
    )
    assert b"content-item:" not in stored_bytes


def test_local_interface_preserves_no_signal_abstention(tmp_path: Path) -> None:
    result = run_local_creator_preflight(
        _request(
            tmp_path,
            draft="A draft without the fixture vocabulary.",
            token="localtest02",
        )
    )

    assert tuple(
        item.status for item in result.preflight_view.evidence.measurements
    ) == ("abstained", "abstained")
    prompt_ids = tuple(
        item.prompt_id for item in result.preflight_view.reflection_prompts
    )
    assert "instrument-abstention" in prompt_ids
    assert "comparison-abstention" in prompt_ids
    assert "No overall CTRT score" in result.markdown


def test_local_interface_fails_closed_on_unauthorized_method_configuration(
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
        run_local_creator_preflight(
            _request(
                tmp_path,
                token="localtest03",
                method_registry_path=changed_path,
            )
        )


def test_extraction_evidence_reader_rehashes_source_before_presentation(
    tmp_path: Path,
) -> None:
    result = run_local_creator_preflight(
        _request(tmp_path, token="localtest04")
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


def test_cli_accepts_one_file_and_writes_markdown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    draft = tmp_path / "draft.txt"
    draft.write_text("The opening is good and the ending is good.", encoding="utf-8")
    output = tmp_path / "preflight.md"

    status = main(
        [
            "--draft-file",
            str(draft),
            "--intent",
            "Share an encouraging update.",
            "--audience",
            "The project team",
            "--concern",
            "Avoid overstating certainty.",
            "--workspace",
            str(tmp_path / "cli-runs"),
            "--output",
            str(output),
            "--run-token",
            "localtest05",
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert f"Wrote creator preflight to {output}" in captured.out
    assert "Artifact store:" in captured.err
    markdown = output.read_text(encoding="utf-8")
    assert "The opening is good and the ending is good." in markdown
    assert "Share an encouraging update." in markdown
    assert "instrument-agreement" not in markdown
    assert "The instruments agreed on this measured dimension" in markdown
    assert "CTRT does not decide whether this draft should be published." in markdown


def test_local_request_rejects_empty_draft_and_unsafe_run_token(
    tmp_path: Path,
) -> None:
    with pytest.raises(LocalCreatorPreflightError, match="draft_text"):
        _request(tmp_path, draft="   ")
    with pytest.raises(LocalCreatorPreflightError, match="run_token"):
        _request(tmp_path, token="../escape")


def test_modules_export_only_the_bounded_local_surfaces() -> None:
    import ctrt.creator_preflight_local as local_module
    import ctrt.eligible_extraction_evidence as evidence_module

    assert evidence_module.__all__ == ["build_eligible_extraction_evidence_view"]
    assert local_module.__all__ == [
        "ABSTENTION_CONTROL_TEXT",
        "DEFAULT_CANDIDATE_REGISTRY",
        "DEFAULT_METHOD_REGISTRY",
        "DISAGREEMENT_CONTROL_TEXT",
        "IDENTITY_CONFIGURATION_HASH",
        "IDENTITY_METHOD_ID",
        "IDENTITY_METHOD_REVISION",
        "LOCAL_PREFLIGHT_VERSION",
        "LocalCreatorPreflightError",
        "LocalCreatorPreflightRequest",
        "LocalCreatorPreflightResult",
        "main",
        "run_local_creator_preflight",
    ]
