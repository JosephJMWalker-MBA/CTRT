"""Research-only behavioral characterization of the admitted VADER candidate.

Behavioral characterization records what the admitted implementation does on
frozen probes. It does not establish that the outputs are correct, calibrated,
fair, or suitable for creator-facing use.

Characterization is a different experiment type from inter-instrument
comparison. Comparison asks whether independent instruments agree, and every
inherited comparison contract therefore requires at least two analyzers.
Characterization asks what one admitted implementation does on frozen inputs,
and answering it with a fabricated second analyzer would be a lie about the
evidence. This module therefore uses a separate single-candidate record built
from the same canonical serialization, artifact-storage, provenance, result,
and verification primitives, and it does not weaken or reuse the comparison
invariants.

Nothing here is imported by creator preflight, the browser surface, or the
creator-facing local CLI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.behavioral_probe_corpus import (
    BehavioralExpectation,
    BehavioralProbe,
    BehavioralProbeCorpus,
    BehavioralProbeCorpusError,
    load_behavioral_probe_corpus,
    probe_categories,
)
from ctrt.candidate_eligibility import (
    CandidateRegistrySnapshot,
    RegistryLifecycle,
    candidate_authorization_reasons,
)
from ctrt.contracts import ModelResult, ResultStatus, SourceType
from ctrt.experiments import VersionedArtifactRef
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionManifestSnapshot,
    SourceArtifactSnapshot,
    extracted_content_artifact_id,
    extraction_artifact_id,
    load_extracted_corpus,
    source_artifact_id,
)
from ctrt.extraction_method_eligibility import (
    ExtractionMethodRegistrySnapshot,
    MethodBoundExtractionCorpusSnapshot,
    authorize_extraction_methods,
)
from ctrt.real_candidate_registry import RealCandidateBinding, real_candidate_binding
from ctrt.serialization import canonical_sha256, serialize_artifact
from ctrt.vader_adapter import (
    VADER_ANALYZER_ID,
    VADER_CANDIDATE_ID,
    VaderSentimentAdapter,
    load_vader_sentiment_adapter,
)

CHARACTERIZATION_VERSION = "ctrt-vader-behavioral-characterization@0.1.0"
CHARACTERIZATION_RECORD_TYPE = "behavioral_characterization"
IDENTITY_METHOD_ID = "synthetic.identity-text"
IDENTITY_METHOD_REVISION = "ctrt-synthetic-identity-text@0.1.0"
IDENTITY_CONFIGURATION_HASH = (
    "sha256:bc8e485583a873ac9269382749b2ff803b649939b3ec829ec8bf140db6e350c8"
)
_RUN_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")

CHARACTERIZATION_NON_CLAIMS = (
    "Behavioral characterization records what the admitted implementation does on "
    "frozen probes. It does not establish that the outputs are correct, calibrated, "
    "fair, or suitable for creator-facing use.",
    "This run produces no overall CTRT score, no mean sentiment value, no overall "
    "positive, negative, or neutral classification, and no scalar confidence.",
    "This run produces no candidate ranking, selection recommendation, or "
    "creator-facing output.",
    "A probe description states what an item was designed to exercise. It is not a "
    "human annotation and not a correct-answer label.",
    "A behavioral expectation is a narrow relation with a declared basis. A "
    "satisfied or unsatisfied expectation describes that exact probe only. It is "
    "never a content verdict and never a candidate score.",
    "Lifecycle counts describe execution outcomes only. They are not a measure of "
    "analytical quality and must not be read as a pass rate.",
    "The candidate lifecycle status is unchanged by this run and remains "
    "eligible_for_evaluation.",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_REAL_REGISTRY = (
    _repo_root() / "docs" / "candidates" / "real-registry.v0.1.0.json"
)
DEFAULT_METHOD_REGISTRY = (
    _repo_root()
    / "docs"
    / "candidates"
    / "synthetic-extraction-method-registry.v0.1.0.json"
)
DEFAULT_PROBE_CORPUS = (
    _repo_root() / "docs" / "corpora" / "vader-behavioral-probes.v0.1.0.json"
)


class VaderCharacterizationError(ValueError):
    """Raised when a research characterization run cannot proceed exactly."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise VaderCharacterizationError(f"{field_name} must be a JSON object")
    if any(not isinstance(key, str) for key in value):
        raise VaderCharacterizationError(f"{field_name} keys must be strings")
    return value


def _load_document(path: Path, field_name: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VaderCharacterizationError(
            f"unable to read {field_name} from {path}"
        ) from exc
    return _mapping(value, field_name)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise VaderCharacterizationError("started_at must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stored_ref_document(reference: StoredArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def _versioned_ref_document(reference: VersionedArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_version": reference.artifact_version,
        "artifact_hash": reference.artifact_hash,
    }


@dataclass(frozen=True, slots=True)
class CharacterizationPlan:
    """A frozen research-only plan naming exactly one admitted candidate.

    This carries the inverse of the comparison invariant on purpose. A frozen
    :class:`~ctrt.experiments.ExperimentPlan` requires at least two instrument
    revisions because comparison is meaningless with one. Characterization is
    meaningful with exactly one and dishonest with a fabricated second, so this
    record requires exactly one.
    """

    characterization_id: str
    characterization_version: str
    record_type: str
    research_question: str
    candidate_registry_ref: VersionedArtifactRef
    probe_corpus_ref: VersionedArtifactRef
    corpus_ref: VersionedArtifactRef
    content_ids: tuple[str, ...]
    candidate_id: str
    analyzer_id: str
    dimension_id: str
    implementation_revision: str
    configuration_hash: str
    non_claims: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        if self.record_type != CHARACTERIZATION_RECORD_TYPE:
            raise VaderCharacterizationError(
                "characterization plan must declare the characterization record type"
            )
        if self.characterization_version != CHARACTERIZATION_VERSION:
            raise VaderCharacterizationError("unsupported characterization version")
        if not self.content_ids:
            raise VaderCharacterizationError("characterization requires content")
        if len(self.content_ids) != len(set(self.content_ids)):
            raise VaderCharacterizationError("content IDs must be unique")
        if self.non_claims != CHARACTERIZATION_NON_CLAIMS:
            raise VaderCharacterizationError(
                "characterization plan must preserve the declared non-claims"
            )


@dataclass(frozen=True, slots=True)
class CharacterizationEligibility:
    """Evidence that the single admitted candidate passed the registry gate."""

    candidate_registry_ref: VersionedArtifactRef
    candidate_id: str
    analyzer_id: str
    dimension_id: str
    implementation_revision: str
    package_distribution: str
    package_version: str
    configuration_hash: str
    lifecycle_status: str
    license_review_status: str
    user_facing_execution_permitted: bool

    def __post_init__(self) -> None:
        if self.user_facing_execution_permitted:
            raise VaderCharacterizationError(
                "characterization may not run a candidate permitting user-facing use"
            )
        if self.lifecycle_status != "eligible_for_evaluation":
            raise VaderCharacterizationError(
                "characterization requires a candidate eligible for evaluation"
            )


@dataclass(frozen=True, slots=True)
class ObservedOutput:
    """One preserved analyzer output with its own key and declared bounds."""

    key: str
    value: float
    lower_bound: float
    upper_bound: float


@dataclass(frozen=True, slots=True)
class ExpectationOutcome:
    """One narrow expectation and what was observed, kept beside the results."""

    expectation_id: str
    kind: str
    basis: str
    basis_detail: str
    statement: str
    output_key: str
    relation: str
    base_probe_id: str
    variant_probe_id: str | None
    observed_base: float | None
    observed_variant: float | None
    satisfied: bool | None
    interpretation: str

    def __post_init__(self) -> None:
        if not self.interpretation.strip():
            raise VaderCharacterizationError("expectation outcome requires interpretation")


EXPECTATION_INTERPRETATION = (
    "This outcome describes only whether the observed implementation satisfied this "
    "exact narrow probe. It is not a content verdict, not an accuracy measure, and "
    "not a candidate score."
)


@dataclass(frozen=True, slots=True)
class ProbeObservation:
    """Everything preserved for one probe item."""

    position: int
    probe_id: str
    content_id: str
    content_hash: str
    extraction_ref: str
    language: str
    text: str
    categories: tuple[str, ...]
    probe_description: str
    result_id: str
    result_status: str
    raw_output: Mapping[str, object]
    normalized_outputs: tuple[ObservedOutput, ...]
    evidence_support_status: str
    evidence_span_count: int
    calibration_status: str
    applicability_status: str
    applicability_reasons: tuple[str, ...]
    extraction_quality_status: str
    extraction_quality_evidence_ref: str
    abstention_triggered: bool
    abstention_reasons: tuple[str, ...]
    preserved_uncertainties: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    source_artifact_ref: StoredArtifactRef
    extraction_artifact_ref: StoredArtifactRef
    content_artifact_ref: StoredArtifactRef
    result_artifact_ref: StoredArtifactRef

    def __post_init__(self) -> None:
        if self.evidence_span_count != 0:
            raise VaderCharacterizationError(
                "this candidate cannot localize evidence; spans must remain absent"
            )
        if self.extraction_quality_evidence_ref != self.extraction_ref:
            raise VaderCharacterizationError(
                "extraction-quality evidence must reference the exact extraction identity"
            )


@dataclass(frozen=True, slots=True)
class LifecycleCounts:
    """Execution outcomes only. Never a measure of analytical quality."""

    completed: int
    abstained: int
    structurally_failed: int
    notes: str = (
        "Lifecycle information only. These counts describe execution outcomes and "
        "are not a pass rate, an accuracy measure, or any statement of analytical "
        "quality."
    )

    def __post_init__(self) -> None:
        values = (self.completed, self.abstained, self.structurally_failed)
        if any(value < 0 for value in values):
            raise VaderCharacterizationError("lifecycle counts must be non-negative")


@dataclass(frozen=True, slots=True)
class CharacterizationCompletion:
    """Canonical completion record for one research characterization run."""

    completion_id: str
    characterization_id: str
    characterization_version: str
    record_type: str
    status: str
    candidate_registry_ref: VersionedArtifactRef
    probe_corpus_ref: VersionedArtifactRef
    corpus_manifest_ref: StoredArtifactRef
    method_eligibility_ref: StoredArtifactRef
    eligibility_ref: StoredArtifactRef
    candidate_id: str
    analyzer_id: str
    package_distribution: str
    package_version: str
    adapter_revision: str
    configuration_hash: str
    taxonomy_id: str
    taxonomy_version: str
    dimension_id: str
    dimension_version: str
    content_ids: tuple[str, ...]
    result_refs: tuple[StoredArtifactRef, ...]
    lifecycle_counts: LifecycleCounts
    candidate_lifecycle_status: str
    non_claims: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.record_type != CHARACTERIZATION_RECORD_TYPE:
            raise VaderCharacterizationError("unsupported completion record type")
        if self.candidate_lifecycle_status != "eligible_for_evaluation":
            raise VaderCharacterizationError(
                "a characterization run may not advance the candidate lifecycle"
            )
        if len(self.result_refs) != len(self.content_ids):
            raise VaderCharacterizationError(
                "one result reference is required per content item"
            )
        if self.non_claims != CHARACTERIZATION_NON_CLAIMS:
            raise VaderCharacterizationError(
                "completion must preserve the declared non-claims"
            )


@dataclass(frozen=True, slots=True)
class VerifiedCharacterizationRun:
    """A characterization run whose stored artifacts all re-verified."""

    characterization_version: str
    run_directory: Path
    artifact_directory: Path
    plan: CharacterizationPlan
    eligibility: CharacterizationEligibility
    completion: CharacterizationCompletion
    completion_ref: StoredArtifactRef
    observations: tuple[ProbeObservation, ...]
    expectation_outcomes: tuple[ExpectationOutcome, ...]
    markdown: str

    def __post_init__(self) -> None:
        if self.characterization_version != CHARACTERIZATION_VERSION:
            raise VaderCharacterizationError("unsupported characterization version")


@dataclass(frozen=True, slots=True)
class CharacterizationRequest:
    """Inputs for one research-only characterization run."""

    workspace: Path
    run_token: str
    started_at: datetime
    probe_corpus_path: Path = DEFAULT_PROBE_CORPUS
    real_registry_path: Path = DEFAULT_REAL_REGISTRY
    method_registry_path: Path = DEFAULT_METHOD_REGISTRY

    def __post_init__(self) -> None:
        if _RUN_TOKEN_PATTERN.fullmatch(self.run_token) is None:
            raise VaderCharacterizationError(
                "run_token must contain 8-64 lowercase letters, digits, or hyphens"
            )
        if self.started_at.tzinfo is None:
            raise VaderCharacterizationError("started_at must include a timezone")


@dataclass(frozen=True, slots=True)
class _ProbeGraph:
    probe: BehavioralProbe
    source: SourceArtifactSnapshot
    extraction: ExtractionManifestSnapshot
    content: ExtractedContentSnapshot


def _probe_graph(
    *,
    probe: BehavioralProbe,
    run_token: str,
    created_at: str,
) -> _ProbeGraph:
    content_id = f"probe-{run_token}-{probe.probe_id}"
    source_id = f"source.{content_id}"
    source = SourceArtifactSnapshot.from_document(
        {
            "artifact_id": source_artifact_id(source_id, probe.content_hash),
            "source_id": source_id,
            "text": probe.text,
            "source_hash": probe.content_hash,
            "source_type": SourceType.RAW_TEXT.value,
            "source_uri": None,
        }
    )
    identity = extraction_artifact_id(
        content_id=content_id,
        source_artifact_ref=source.reference(),
        method_id=IDENTITY_METHOD_ID,
        method_revision=IDENTITY_METHOD_REVISION,
        configuration_hash=IDENTITY_CONFIGURATION_HASH,
        canonical_content_hash=probe.content_hash,
    )
    content = ExtractedContentSnapshot.from_document(
        {
            "artifact_id": extracted_content_artifact_id(
                content_id,
                probe.content_hash,
                identity,
            ),
            "content_id": content_id,
            "text": probe.text,
            "content_hash": probe.content_hash,
            "language": probe.language,
            "source_type": SourceType.RAW_TEXT.value,
            "source_uri": None,
            "extraction_ref": identity,
        }
    )
    extraction = ExtractionManifestSnapshot.from_document(
        {
            "artifact_id": identity,
            "content_id": content_id,
            "source_artifact_ref": _stored_ref_document(source.reference()),
            "method_id": IDENTITY_METHOD_ID,
            "method_revision": IDENTITY_METHOD_REVISION,
            "configuration_hash": IDENTITY_CONFIGURATION_HASH,
            "canonical_content_hash": probe.content_hash,
            "content_artifact_ref": _stored_ref_document(content.reference()),
            "coordinate_map": [
                {
                    "source_start": 0,
                    "source_end": len(probe.text),
                    "canonical_start": 0,
                    "canonical_end": len(probe.text),
                    "kind": "exact",
                }
            ],
            "created_at": created_at,
        }
    )
    extraction.verify(source, content)
    return _ProbeGraph(
        probe=probe,
        source=source,
        extraction=extraction,
        content=content,
    )


def _method_bound_corpus(
    *,
    run_token: str,
    graphs: tuple[_ProbeGraph, ...],
    method_registry: ExtractionMethodRegistrySnapshot,
    created_at: str,
) -> MethodBoundExtractionCorpusSnapshot:
    contents: list[dict[str, object]] = []
    for position, graph in enumerate(graphs):
        contents.append(
            {
                "position": position,
                "content_id": graph.content.content_id,
                "content_hash": graph.content.content_hash,
                "language": graph.content.language,
                "source_type": graph.content.source_type.value,
                "source_uri": graph.content.source_uri,
                "source_artifact_ref": _stored_ref_document(graph.source.reference()),
                "extraction_artifact_ref": _stored_ref_document(
                    graph.extraction.reference()
                ),
                "content_artifact_ref": _stored_ref_document(graph.content.reference()),
            }
        )
    return MethodBoundExtractionCorpusSnapshot.from_document(
        {
            "corpus_id": f"corpus.vader-characterization.{run_token}",
            "corpus_version": "0.1.0",
            "status": "frozen",
            "method_registry_ref": _versioned_ref_document(method_registry.reference()),
            "contents": contents,
            "created_at": created_at,
        }
    )


def _authorize_candidate(
    *,
    registry: CandidateRegistrySnapshot,
    binding: RealCandidateBinding,
    adapter: VaderSentimentAdapter,
) -> CharacterizationEligibility:
    """Apply the same registry gate the comparison path uses, for one candidate."""

    if registry.status is not RegistryLifecycle.ACCEPTED:
        raise VaderCharacterizationError(
            "candidate registry must be accepted before execution"
        )
    record = registry.candidate(VADER_CANDIDATE_ID)
    if record is None:
        raise VaderCharacterizationError(
            f"candidate {VADER_CANDIDATE_ID!r} is absent from the registry"
        )
    reasons = candidate_authorization_reasons(
        record,
        analyzer_id=VADER_ANALYZER_ID,
        dimension_id=adapter.dimension_id,
        implementation_revision=adapter.implementation_revision,
    )
    if reasons:
        raise VaderCharacterizationError(
            "candidate eligibility failed: " + "; ".join(reasons)
        )
    if binding.package.version != adapter.package_version:
        raise VaderCharacterizationError(
            "installed package version differs from the registry binding"
        )
    observed_hash = canonical_sha256(adapter.execution_configuration)
    if observed_hash != binding.configuration_hash:
        raise VaderCharacterizationError(
            "adapter configuration hash differs from the registry binding"
        )
    return CharacterizationEligibility(
        candidate_registry_ref=registry.reference(),
        candidate_id=record.candidate_id,
        analyzer_id=VADER_ANALYZER_ID,
        dimension_id=adapter.dimension_id,
        implementation_revision=adapter.implementation_revision,
        package_distribution=binding.package.distribution,
        package_version=binding.package.version,
        configuration_hash=binding.configuration_hash,
        lifecycle_status=record.status.value,
        license_review_status=record.license_status.value,
        user_facing_execution_permitted=(
            binding.execution_boundary.user_facing_execution_permitted
        ),
    )


def _persist_probe_graphs(
    store: FileSystemArtifactStore,
    *,
    corpus: MethodBoundExtractionCorpusSnapshot,
    graphs: tuple[_ProbeGraph, ...],
) -> StoredArtifactRef:
    """Persist source and output graphs first, then publish the corpus last."""

    for entry, graph in zip(corpus.corpus.contents, graphs, strict=True):
        entry.verify(graph.source, graph.extraction, graph.content)
        if store.append(graph.source.artifact()) != graph.source.reference():
            raise ArtifactIntegrityError("stored source reference differs")
        if store.append(graph.content.artifact()) != graph.content.reference():
            raise ArtifactIntegrityError("stored content reference differs")
        if store.append(graph.extraction.artifact()) != graph.extraction.reference():
            raise ArtifactIntegrityError("stored extraction reference differs")
    stored = store.append(corpus.corpus.artifact())
    if stored.artifact_hash != corpus.corpus.artifact_hash:
        raise ArtifactIntegrityError("stored extraction corpus reference differs")
    return stored


def _observation(
    *,
    probe: BehavioralProbe,
    graph: _ProbeGraph,
    result: ModelResult,
    result_ref: StoredArtifactRef,
) -> ProbeObservation:
    confidence = result.confidence
    return ProbeObservation(
        position=probe.position,
        probe_id=probe.probe_id,
        content_id=graph.content.content_id,
        content_hash=graph.content.content_hash,
        extraction_ref=result.analysis_target.extraction_ref,
        language=graph.content.language,
        text=graph.content.text,
        categories=probe.categories,
        probe_description=probe.probes,
        result_id=result.result_id,
        result_status=result.status.value,
        raw_output=dict(result.raw_output),
        normalized_outputs=tuple(
            ObservedOutput(
                key=item.key,
                value=item.value,
                lower_bound=item.lower_bound,
                upper_bound=item.upper_bound,
            )
            for item in result.normalized_scores
        ),
        evidence_support_status=result.evidence_support.status.value,
        evidence_span_count=len(result.evidence_spans),
        calibration_status=confidence.calibration.status.value,
        applicability_status=confidence.applicability.status.value,
        applicability_reasons=confidence.applicability.reasons,
        extraction_quality_status=confidence.extraction_quality.status.value,
        extraction_quality_evidence_ref=(
            confidence.extraction_quality.evidence_ref or ""
        ),
        abstention_triggered=confidence.system_abstention.triggered,
        abstention_reasons=confidence.system_abstention.reasons,
        preserved_uncertainties=confidence.ambiguity_budget.preserved_uncertainties,
        warnings=result.warnings,
        errors=result.errors,
        source_artifact_ref=graph.source.reference(),
        extraction_artifact_ref=graph.extraction.reference(),
        content_artifact_ref=graph.content.reference(),
        result_artifact_ref=result_ref,
    )


def _expectation_outcome(
    expectation: BehavioralExpectation,
    observations: Mapping[str, ProbeObservation],
) -> ExpectationOutcome:
    def _value(probe_id: str | None) -> float | None:
        if probe_id is None:
            return None
        observation = observations[probe_id]
        for item in observation.normalized_outputs:
            if item.key == expectation.output_key:
                return item.value
        return None

    observed_base = _value(expectation.base_probe_id)
    observed_variant = _value(expectation.variant_probe_id)
    needed = (
        (observed_base,)
        if expectation.variant_probe_id is None
        else (observed_base, observed_variant)
    )
    satisfied: bool | None = None
    if all(item is not None for item in needed):
        values: dict[str, float] = {expectation.base_probe_id: cast(float, observed_base)}
        if expectation.variant_probe_id is not None:
            values[expectation.variant_probe_id] = cast(float, observed_variant)
        satisfied = expectation.evaluate(values)
    return ExpectationOutcome(
        expectation_id=expectation.expectation_id,
        kind=expectation.kind.value,
        basis=expectation.basis.value,
        basis_detail=expectation.basis_detail,
        statement=expectation.statement,
        output_key=expectation.output_key,
        relation=expectation.relation.value,
        base_probe_id=expectation.base_probe_id,
        variant_probe_id=expectation.variant_probe_id,
        observed_base=observed_base,
        observed_variant=observed_variant,
        satisfied=satisfied,
        interpretation=EXPECTATION_INTERPRETATION,
    )


def run_vader_characterization(
    request: CharacterizationRequest,
) -> VerifiedCharacterizationRun:
    """Execute one research-only characterization and reverify every artifact."""

    created_at = _iso(request.started_at)
    corpus_document = _load_document(request.probe_corpus_path, "probe corpus")
    try:
        probe_corpus = load_behavioral_probe_corpus(corpus_document)
    except BehavioralProbeCorpusError as exc:
        raise VaderCharacterizationError(str(exc)) from exc

    candidate_registry = CandidateRegistrySnapshot.from_document(
        _load_document(request.real_registry_path, "real candidate registry")
    )
    binding = real_candidate_binding(
        _load_document(request.real_registry_path, "real candidate registry"),
        VADER_CANDIDATE_ID,
    )
    method_registry = ExtractionMethodRegistrySnapshot.from_document(
        _load_document(request.method_registry_path, "extraction method registry")
    )

    adapter = load_vader_sentiment_adapter()
    eligibility = _authorize_candidate(
        registry=candidate_registry,
        binding=binding,
        adapter=adapter,
    )

    graphs = tuple(
        _probe_graph(probe=probe, run_token=request.run_token, created_at=created_at)
        for probe in probe_corpus.probes
    )
    corpus = _method_bound_corpus(
        run_token=request.run_token,
        graphs=graphs,
        method_registry=method_registry,
        created_at=created_at,
    )
    method_report = authorize_extraction_methods(
        experiment_id=f"characterization.vader.{request.run_token}",
        experiment_version="0.1.0",
        corpus=corpus,
        registry=method_registry,
        extractions=tuple(item.extraction for item in graphs),
    )

    probe_corpus_ref = VersionedArtifactRef(
        artifact_id=probe_corpus.corpus_id,
        artifact_version=probe_corpus.corpus_version,
        artifact_hash=probe_corpus.artifact_hash,
    )
    plan = CharacterizationPlan(
        characterization_id=f"characterization.vader.{request.run_token}",
        characterization_version=CHARACTERIZATION_VERSION,
        record_type=CHARACTERIZATION_RECORD_TYPE,
        research_question=(
            "What does the exact admitted VADER implementation do on a frozen, "
            "provenance-preserving behavioral probe corpus?"
        ),
        candidate_registry_ref=candidate_registry.reference(),
        probe_corpus_ref=probe_corpus_ref,
        corpus_ref=corpus.reference(),
        content_ids=corpus.content_ids,
        candidate_id=eligibility.candidate_id,
        analyzer_id=eligibility.analyzer_id,
        dimension_id=eligibility.dimension_id,
        implementation_revision=eligibility.implementation_revision,
        configuration_hash=eligibility.configuration_hash,
        non_claims=CHARACTERIZATION_NON_CLAIMS,
        created_at=created_at,
    )

    run_directory = request.workspace / request.run_token
    artifact_directory = run_directory / "artifacts"
    store = FileSystemArtifactStore(artifact_directory)

    store.append(serialize_artifact(plan.characterization_id, plan))
    corpus_manifest_ref = _persist_probe_graphs(store, corpus=corpus, graphs=graphs)
    method_eligibility_ref = store.append(method_report.artifact())
    eligibility_ref = store.append(
        serialize_artifact(
            f"{plan.characterization_id}:candidate-eligibility",
            eligibility,
        )
    )

    # Reconstruct exact analyzer inputs from storage, rehashing on read.
    loaded = load_extracted_corpus(store, corpus.corpus)
    if tuple(item.content_id for item in loaded.contents) != corpus.content_ids:
        raise VaderCharacterizationError(
            "stored extraction corpus order differs from the frozen corpus"
        )

    observations: list[ProbeObservation] = []
    result_refs: list[StoredArtifactRef] = []
    for probe, graph, content in zip(
        probe_corpus.probes, graphs, loaded.contents, strict=True
    ):
        result = adapter.analyze(content)
        result_ref = store.append(serialize_artifact(result.result_id, result))
        result_refs.append(result_ref)
        observations.append(
            _observation(
                probe=probe,
                graph=graph,
                result=result,
                result_ref=result_ref,
            )
        )
        store.append(
            serialize_artifact(
                f"{plan.characterization_id}:{probe.probe_id}:observation",
                observations[-1],
            )
        )

    by_probe = {item.probe_id: item for item in observations}
    expectation_outcomes = tuple(
        _expectation_outcome(item, by_probe) for item in probe_corpus.expectations
    )
    for outcome in expectation_outcomes:
        store.append(
            serialize_artifact(
                f"{plan.characterization_id}:{outcome.expectation_id}:outcome",
                outcome,
            )
        )

    completion = CharacterizationCompletion(
        completion_id=f"{plan.characterization_id}:completion",
        characterization_id=plan.characterization_id,
        characterization_version=CHARACTERIZATION_VERSION,
        record_type=CHARACTERIZATION_RECORD_TYPE,
        status="verified",
        candidate_registry_ref=candidate_registry.reference(),
        probe_corpus_ref=probe_corpus_ref,
        corpus_manifest_ref=corpus_manifest_ref,
        method_eligibility_ref=method_eligibility_ref,
        eligibility_ref=eligibility_ref,
        candidate_id=eligibility.candidate_id,
        analyzer_id=eligibility.analyzer_id,
        package_distribution=eligibility.package_distribution,
        package_version=eligibility.package_version,
        adapter_revision=adapter.implementation_revision,
        configuration_hash=eligibility.configuration_hash,
        taxonomy_id=adapter.identity.taxonomy_id,
        taxonomy_version=adapter.identity.taxonomy_version,
        dimension_id=adapter.dimension_id,
        dimension_version=adapter.dimension_version,
        content_ids=corpus.content_ids,
        result_refs=tuple(result_refs),
        lifecycle_counts=LifecycleCounts(
            completed=sum(
                1 for item in observations if item.result_status == ResultStatus.SUCCESS
            ),
            abstained=sum(
                1
                for item in observations
                if item.result_status == ResultStatus.ABSTAINED
            ),
            structurally_failed=sum(
                1 for item in observations if item.result_status == ResultStatus.FAILED
            ),
        ),
        candidate_lifecycle_status=eligibility.lifecycle_status,
        non_claims=CHARACTERIZATION_NON_CLAIMS,
        completed_at=_iso(datetime.now(UTC)),
    )
    completion_artifact = serialize_artifact(completion.completion_id, completion)
    completion_ref = store.append(completion_artifact)

    _verify_stored_run(
        store=store,
        completion=completion,
        completion_ref=completion_ref,
        corpus=corpus,
        observations=tuple(observations),
    )

    markdown = render_characterization_report_markdown(
        plan=plan,
        eligibility=eligibility,
        completion=completion,
        completion_ref=completion_ref,
        probe_corpus=probe_corpus,
        observations=tuple(observations),
        expectation_outcomes=expectation_outcomes,
    )
    return VerifiedCharacterizationRun(
        characterization_version=CHARACTERIZATION_VERSION,
        run_directory=run_directory,
        artifact_directory=artifact_directory,
        plan=plan,
        eligibility=eligibility,
        completion=completion,
        completion_ref=completion_ref,
        observations=tuple(observations),
        expectation_outcomes=expectation_outcomes,
        markdown=markdown,
    )


def _verify_stored_run(
    *,
    store: FileSystemArtifactStore,
    completion: CharacterizationCompletion,
    completion_ref: StoredArtifactRef,
    corpus: MethodBoundExtractionCorpusSnapshot,
    observations: tuple[ProbeObservation, ...],
) -> None:
    """Re-read and rehash every stored artifact before anything is rendered."""

    expected = serialize_artifact(completion.completion_id, completion)
    stored = store.get(
        completion_ref.artifact_id,
        expected_hash=completion_ref.artifact_hash,
    )
    if stored.payload != expected.payload:
        raise ArtifactIntegrityError(
            "stored characterization completion differs from the expected manifest"
        )
    for reference in (
        completion.corpus_manifest_ref,
        completion.method_eligibility_ref,
        completion.eligibility_ref,
        *completion.result_refs,
    ):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
    for observation in observations:
        for reference in (
            observation.source_artifact_ref,
            observation.extraction_artifact_ref,
            observation.content_artifact_ref,
            observation.result_artifact_ref,
        ):
            store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
    # Rehash the whole extraction graph a second time, after execution.
    load_extracted_corpus(store, corpus.corpus)


def _format_number(value: float) -> str:
    return f"{value:.4f}"


def _optional_number(value: float | None) -> str:
    return "not observed" if value is None else _format_number(value)


def _satisfied_text(value: bool | None) -> str:
    if value is None:
        return "not evaluable (no measurement was emitted)"
    return "satisfied" if value else "not satisfied"


def render_characterization_report_markdown(
    *,
    plan: CharacterizationPlan,
    eligibility: CharacterizationEligibility,
    completion: CharacterizationCompletion,
    completion_ref: StoredArtifactRef,
    probe_corpus: BehavioralProbeCorpus,
    observations: tuple[ProbeObservation, ...],
    expectation_outcomes: tuple[ExpectationOutcome, ...],
) -> str:
    """Render one deterministic research report from reverified stored evidence."""

    lines: list[str] = [
        "# VADER behavioral characterization (research only)",
        "",
        "Behavioral characterization records what the admitted implementation does "
        "on frozen probes. It does not establish that the outputs are correct, "
        "calibrated, fair, or suitable for creator-facing use.",
        "",
        "## 1. Run and candidate identity",
        "",
        f"- Characterization contract: `{plan.characterization_version}`",
        f"- Record type: `{plan.record_type}`",
        f"- Characterization ID: `{plan.characterization_id}`",
        f"- Research question: {plan.research_question}",
        f"- Candidate: `{eligibility.candidate_id}`",
        f"- Analyzer: `{eligibility.analyzer_id}`",
        f"- Distribution: `{eligibility.package_distribution}=="
        f"{eligibility.package_version}`",
        f"- Adapter revision: `{completion.adapter_revision}`",
        f"- Configuration hash: `{eligibility.configuration_hash}`",
        f"- Taxonomy: `{completion.taxonomy_id}` @ `{completion.taxonomy_version}`",
        f"- Dimension: `{completion.dimension_id}` @ `{completion.dimension_version}`",
        f"- Candidate lifecycle status: `{completion.candidate_lifecycle_status}` "
        "(unchanged by this run)",
        f"- License review: `{eligibility.license_review_status}`",
        "- User-facing execution permitted: no",
        "",
        "This is a single-candidate characterization record. It is not an "
        "inter-instrument comparison, and no second analyzer was registered, "
        "duplicated, or fabricated.",
        "",
        "## 2. Corpus and provenance",
        "",
        f"- Probe corpus: `{probe_corpus.corpus_id}` @ `{probe_corpus.corpus_version}`",
        f"- Probe corpus hash: `{probe_corpus.artifact_hash}`",
        f"- Purpose: `{probe_corpus.purpose}`",
        f"- Probe count: {len(probe_corpus.probes)}",
        "- Authorship: repository authored specifically for CTRT",
        "- External dataset: none. Scraped content: none. Network retrieval: none.",
        "- Human ground-truth labels: none.",
        "",
        "Categories exercised: "
        + ", ".join(f"`{item}`" for item in probe_categories(probe_corpus.probes)),
        "",
        "## 3. Per-probe observations",
        "",
    ]

    for observation in observations:
        lines.extend(
            [
                f"### {observation.probe_id} (position {observation.position})",
                "",
                f"- Content ID: `{observation.content_id}`",
                f"- Content hash: `{observation.content_hash}`",
                f"- Extraction identity: `{observation.extraction_ref}`",
                f"- Declared language: `{observation.language}`",
                "- Categories: "
                + ", ".join(f"`{item}`" for item in observation.categories),
                f"- Probes: {observation.probe_description}",
                "- This description states what the item exercises. It is not a "
                "correct-answer label.",
                "",
                "Exact text:",
                "",
                f"> {observation.text}",
                "",
                f"Result status: `{observation.result_status}`",
                "",
            ]
        )
        if observation.normalized_outputs:
            lines.extend(
                [
                    "| Output | Value | Lower bound | Upper bound |",
                    "| --- | --- | --- | --- |",
                ]
            )
            lines.extend(
                f"| `{item.key}` | {_format_number(item.value)} | "
                f"{_format_number(item.lower_bound)} | "
                f"{_format_number(item.upper_bound)} |"
                for item in observation.normalized_outputs
            )
            lines.append("")
            lines.append(
                "Each output is preserved separately with its own bounds. They are "
                "not combined, and `compound` is not a confidence value."
            )
            lines.append("")
        else:
            lines.extend(
                [
                    "No measurement was emitted for this probe.",
                    "",
                ]
            )
        lines.extend(
            [
                f"- Evidence support: `{observation.evidence_support_status}` "
                f"with {observation.evidence_span_count} evidence spans",
                f"- Calibration: `{observation.calibration_status}`",
                f"- Applicability: `{observation.applicability_status}`",
            ]
        )
        lines.extend(
            f"  - {item}" for item in observation.applicability_reasons
        )
        lines.append(
            f"- Extraction quality: `{observation.extraction_quality_status}` "
            f"referencing `{observation.extraction_quality_evidence_ref}`"
        )
        if observation.abstention_triggered:
            lines.append(
                "- Abstention triggered: "
                + ", ".join(f"`{item}`" for item in observation.abstention_reasons)
            )
        if observation.errors:
            lines.extend(f"- Structural error: {item}" for item in observation.errors)
        lines.extend(["- Preserved uncertainty:", ""])
        lines.extend(f"  - {item}" for item in observation.preserved_uncertainties)
        lines.append("")

    lines.extend(
        [
            "## 4. Narrow behavioral expectations",
            "",
            "Each expectation is a narrow relation with a declared basis. An "
            "expectation outcome describes only that exact probe. It is never a "
            "content verdict, an accuracy measure, or a candidate score. No overall "
            "expectation rate is computed.",
            "",
        ]
    )
    for outcome in expectation_outcomes:
        lines.extend(
            [
                f"### {outcome.expectation_id}",
                "",
                f"- Kind: `{outcome.kind}`",
                f"- Basis: `{outcome.basis}`",
                f"- Basis detail: {outcome.basis_detail}",
                f"- Statement: {outcome.statement}",
                f"- Observed output key: `{outcome.output_key}`",
                f"- Relation: `{outcome.relation}`",
                f"- Base probe `{outcome.base_probe_id}` observed: "
                f"{_optional_number(outcome.observed_base)}",
            ]
        )
        if outcome.variant_probe_id is not None:
            lines.append(
                f"- Variant probe `{outcome.variant_probe_id}` observed: "
                f"{_optional_number(outcome.observed_variant)}"
            )
        lines.extend(
            [
                f"- Observed outcome: **{_satisfied_text(outcome.satisfied)}**",
                f"- {outcome.interpretation}",
                "",
            ]
        )

    counts = completion.lifecycle_counts
    lines.extend(
        [
            "## 5. Abstentions and structural failures",
            "",
            f"- Completed: {counts.completed}",
            f"- Abstained: {counts.abstained}",
            f"- Structurally failed: {counts.structurally_failed}",
            "",
            counts.notes,
            "",
            "## 6. Immutable artifact references",
            "",
            f"- `characterization-completion` → `{completion_ref.artifact_id}` "
            f"(`{completion_ref.artifact_hash}`)",
            f"- `extraction-corpus` → `{completion.corpus_manifest_ref.artifact_id}` "
            f"(`{completion.corpus_manifest_ref.artifact_hash}`)",
            f"- `extraction-method-eligibility` → "
            f"`{completion.method_eligibility_ref.artifact_id}` "
            f"(`{completion.method_eligibility_ref.artifact_hash}`)",
            f"- `candidate-eligibility` → `{completion.eligibility_ref.artifact_id}` "
            f"(`{completion.eligibility_ref.artifact_hash}`)",
            "",
        ]
    )
    for observation in observations:
        lines.append(
            f"- `result:{observation.probe_id}` → "
            f"`{observation.result_artifact_ref.artifact_id}` "
            f"(`{observation.result_artifact_ref.artifact_hash}`)"
        )
    lines.extend(
        [
            "",
            "## 7. Interpretation boundary and non-claims",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in completion.non_claims)
    lines.extend(
        [
            "",
            "This report is a research artifact. It is not a creator-preflight "
            "screen and was not produced by any creator-facing surface.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.vader_characterization",
        description=(
            "RESEARCH ONLY. Execute the admitted VADER candidate over the frozen "
            "behavioral probe corpus and preserve what it does. This does not "
            "establish analytical validity and is not creator-facing."
        ),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".ctrt") / "vader-characterization",
        help="Directory that will contain one append-only artifact store per run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional Markdown output path. Without it, the report is printed.",
    )
    parser.add_argument(
        "--run-token",
        help="Optional reproducible lowercase run token; otherwise one is generated.",
    )
    parser.add_argument("--probe-corpus", type=Path, default=DEFAULT_PROBE_CORPUS)
    parser.add_argument("--real-registry", type=Path, default=DEFAULT_REAL_REGISTRY)
    parser.add_argument("--method-registry", type=Path, default=DEFAULT_METHOD_REGISTRY)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the research-only characterization run."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    token = arguments.run_token or f"char-{uuid.uuid4().hex[:12]}"
    try:
        run = run_vader_characterization(
            CharacterizationRequest(
                workspace=arguments.workspace,
                run_token=token,
                started_at=datetime.now(UTC),
                probe_corpus_path=arguments.probe_corpus,
                real_registry_path=arguments.real_registry,
                method_registry_path=arguments.method_registry,
            )
        )
    except (VaderCharacterizationError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"vader characterization failed: {exc}\n")
        return 2
    if arguments.output is None:
        sys.stdout.write(run.markdown)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(run.markdown, encoding="utf-8")
        sys.stdout.write(f"Wrote characterization report to {arguments.output}\n")
    sys.stderr.write(f"Artifact store: {run.artifact_directory}\n")
    sys.stderr.write(
        "Research only. Candidate lifecycle remains "
        f"{run.completion.candidate_lifecycle_status}.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHARACTERIZATION_NON_CLAIMS",
    "CHARACTERIZATION_RECORD_TYPE",
    "CHARACTERIZATION_VERSION",
    "DEFAULT_METHOD_REGISTRY",
    "DEFAULT_PROBE_CORPUS",
    "DEFAULT_REAL_REGISTRY",
    "CharacterizationCompletion",
    "CharacterizationEligibility",
    "CharacterizationPlan",
    "CharacterizationRequest",
    "ExpectationOutcome",
    "LifecycleCounts",
    "ObservedOutput",
    "ProbeObservation",
    "VaderCharacterizationError",
    "VerifiedCharacterizationRun",
    "main",
    "render_characterization_report_markdown",
    "run_vader_characterization",
]
