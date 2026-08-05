"""Human evidence views over registry-authorized extraction execution."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.eligible_extraction_runner import (
    EligibleExtractionRunnerStatus,
    VerifiedEligibleExtractionExperimentReceipt,
)
from ctrt.evidence_view import (
    PRESENTATION_NOTICES,
    PRESENTATION_VERSION,
    ContentEvidenceView,
    EvidenceArtifactReference,
    EvidenceViewError,
    StoredContentEvidenceView,
    _content_view,
)
from ctrt.extraction_bound_runner import ExtractionBoundRunnerStatus
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionManifestSnapshot,
    SourceArtifactSnapshot,
)


def _reference(
    role: str,
    value: StoredArtifactRef,
) -> EvidenceArtifactReference:
    return EvidenceArtifactReference.from_stored(role=role, reference=value)


def _load_source(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> SourceArtifactSnapshot:
    source = SourceArtifactSnapshot.from_artifact(
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
    )
    if source.reference() != reference:
        raise ArtifactIntegrityError("stored source reference differs after reconstruction")
    return source


def _load_extraction(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> ExtractionManifestSnapshot:
    extraction = ExtractionManifestSnapshot.from_artifact(
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
    )
    if extraction.reference() != reference:
        raise ArtifactIntegrityError(
            "stored extraction reference differs after reconstruction"
        )
    return extraction


def _load_content(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> ExtractedContentSnapshot:
    content = ExtractedContentSnapshot.from_artifact(
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
    )
    if content.reference() != reference:
        raise ArtifactIntegrityError(
            "stored extracted-content reference differs after reconstruction"
        )
    return content


def _replace_content_references(
    *,
    view: ContentEvidenceView,
    source_ref: StoredArtifactRef,
    extraction_ref: StoredArtifactRef,
    content_ref: StoredArtifactRef,
) -> ContentEvidenceView:
    inherited = tuple(
        item for item in view.artifact_refs if item.role != "canonical-content"
    )
    return replace(
        view,
        artifact_refs=(
            _reference("source-artifact", source_ref),
            _reference("extraction-manifest", extraction_ref),
            _reference("extracted-content", content_ref),
            *inherited,
        ),
    )


def build_eligible_extraction_evidence_view(
    *,
    receipt: VerifiedEligibleExtractionExperimentReceipt,
    artifact_store: FileSystemArtifactStore,
) -> StoredContentEvidenceView:
    """Reverify an authorized extraction graph and derive a noncanonical view."""

    if receipt.status is not EligibleExtractionRunnerStatus.VERIFIED:
        raise EvidenceViewError(
            "eligible extraction evidence requires a verified outer receipt"
        )
    extraction_receipt = receipt.extraction_bound_receipt
    if extraction_receipt.status is not ExtractionBoundRunnerStatus.VERIFIED:
        raise EvidenceViewError(
            "eligible extraction evidence requires a verified extraction receipt"
        )
    experiment = extraction_receipt.experiment_receipt
    if experiment.content_ids != receipt.content_ids:
        raise EvidenceViewError(
            "experiment content order differs from eligible extraction receipt"
        )
    populations = (
        len(extraction_receipt.source_artifact_refs),
        len(extraction_receipt.extraction_artifact_refs),
        len(extraction_receipt.content_artifact_refs),
        len(experiment.session_receipts),
        len(experiment.session_receipt_refs),
    )
    if any(value != len(receipt.content_ids) for value in populations):
        raise EvidenceViewError(
            "eligible extraction evidence populations do not match content IDs"
        )

    completion_refs = (
        _reference("eligible-extraction-completion", receipt.completion_manifest_ref),
        _reference(
            "extraction-bound-completion",
            extraction_receipt.completion_manifest_ref,
        ),
        _reference("experiment-completion", experiment.completion_manifest_ref),
        _reference("extraction-method-registry", receipt.method_registry_ref),
        _reference("extraction-method-eligibility", receipt.eligibility_report_ref),
    )
    for item in completion_refs:
        artifact_store.get(item.artifact_id, expected_hash=item.artifact_hash)

    content_views: list[ContentEvidenceView] = []
    population = zip(
        receipt.content_ids,
        extraction_receipt.source_artifact_refs,
        extraction_receipt.extraction_artifact_refs,
        extraction_receipt.content_artifact_refs,
        experiment.session_receipts,
        experiment.session_receipt_refs,
        strict=True,
    )
    for position, (
        content_id,
        source_ref,
        extraction_ref,
        content_ref,
        session_receipt,
        session_receipt_ref,
    ) in enumerate(population):
        source = _load_source(artifact_store, source_ref)
        extraction = _load_extraction(artifact_store, extraction_ref)
        content = _load_content(artifact_store, content_ref)
        extraction.verify(source, content)
        if content.content_id != content_id:
            raise EvidenceViewError(
                "extracted content order differs from eligible extraction receipt"
            )
        if extraction.content_id != content_id:
            raise EvidenceViewError(
                "extraction identity differs from eligible extraction content order"
            )
        derived = _content_view(
            position=position,
            content=cast(Any, content),
            receipt=session_receipt,
            receipt_ref=session_receipt_ref,
            store=artifact_store,
        )
        content_views.append(
            _replace_content_references(
                view=derived,
                source_ref=source_ref,
                extraction_ref=extraction_ref,
                content_ref=content_ref,
            )
        )

    return StoredContentEvidenceView(
        presentation_version=PRESENTATION_VERSION,
        experiment_run_id=receipt.experiment_run_id,
        lifecycle_status=receipt.status.value,
        experiment_id=receipt.experiment_id,
        experiment_version=receipt.experiment_version,
        contents=tuple(content_views),
        completion_refs=completion_refs,
        notices=PRESENTATION_NOTICES,
    )


__all__ = ["build_eligible_extraction_evidence_view"]
