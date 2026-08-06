"""Dependency-free local intake for extraction-backed content understanding."""

from __future__ import annotations

import argparse
import platform
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.content_understanding import (
    CONTENT_INSPECTION_PATHS,
    CONTENT_UNDERSTANDING_NOTICES,
    CONTENT_UNDERSTANDING_VERSION,
    ContentUnderstandingView,
    ReaderProvidedContext,
    _observations,
    _reflection_prompts,
    render_content_understanding_markdown,
)
from ctrt.creator_preflight_local import (
    ABSTENTION_CONTROL_TEXT,
    DEFAULT_CANDIDATE_REGISTRY,
    DEFAULT_METHOD_REGISTRY,
    DISAGREEMENT_CONTROL_TEXT,
    IDENTITY_CONFIGURATION_HASH,
    IDENTITY_METHOD_ID,
    IDENTITY_METHOD_REVISION,
    _analyzer_registry,
    _analyzers,
    _canonical_alias,
    _ExtractionGraph,
    _graph,
    _iso,
    _load_document,
    _stored_ref_document,
    _validate_run_token,
    _versioned_ref_document,
    _windows,
)
from ctrt.eligible_extraction_evidence import (
    build_eligible_extraction_evidence_view,
)
from ctrt.eligible_extraction_runner import (
    EligibleExtractionExperimentRunner,
    VerifiedEligibleExtractionExperimentReceipt,
)
from ctrt.evidence_view import StoredContentEvidenceView
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.extraction_manifest import persist_extracted_corpus
from ctrt.extraction_method_eligibility import (
    ExtractionMethodRegistrySnapshot,
    MethodBoundExtractionCorpusSnapshot,
)
from ctrt.serialization import canonical_sha256

LOCAL_CONTENT_UNDERSTANDING_VERSION = "ctrt-local-content-understanding@0.1.0"


class LocalContentUnderstandingError(ValueError):
    """Raised when local content cannot support exact synthetic inspection."""


@dataclass(frozen=True, slots=True)
class LocalContentUnderstandingRequest:
    """One submitted raw-text item and non-evidentiary reader context."""

    content_text: str
    context: ReaderProvidedContext
    workspace: Path
    run_token: str
    started_at: datetime
    candidate_registry_path: Path = DEFAULT_CANDIDATE_REGISTRY
    method_registry_path: Path = DEFAULT_METHOD_REGISTRY

    def __post_init__(self) -> None:
        if not self.content_text.strip():
            raise LocalContentUnderstandingError("content_text must not be empty")
        _validate_run_token(self.run_token)
        if self.started_at.tzinfo is None:
            raise LocalContentUnderstandingError("started_at must include a timezone")


@dataclass(frozen=True, slots=True)
class LocalContentUnderstandingResult:
    """Verified local execution and its noncanonical understanding view."""

    interface_version: str
    run_directory: Path
    artifact_directory: Path
    submitted_content_id: str
    receipt: VerifiedEligibleExtractionExperimentReceipt
    evidence_view: StoredContentEvidenceView
    understanding_view: ContentUnderstandingView
    markdown: str

    def __post_init__(self) -> None:
        if self.interface_version != LOCAL_CONTENT_UNDERSTANDING_VERSION:
            raise ValueError("unsupported local content understanding version")
        if self.submitted_content_id != self.understanding_view.content_id:
            raise ValueError("local result content identity must match understanding view")
        if self.receipt.experiment_run_id != self.understanding_view.experiment_run_id:
            raise ValueError("local result run identity must remain exact")


def _method_bound_corpus(
    *,
    run_token: str,
    graphs: tuple[_ExtractionGraph, ...],
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
                "content_artifact_ref": _stored_ref_document(
                    graph.content.reference()
                ),
            }
        )
    return MethodBoundExtractionCorpusSnapshot.from_document(
        {
            "corpus_id": f"corpus.local-content-understanding.{run_token}",
            "corpus_version": "0.1.0",
            "status": "frozen",
            "method_registry_ref": _versioned_ref_document(
                method_registry.reference()
            ),
            "contents": contents,
            "created_at": created_at,
        }
    )


def _plan(
    *,
    run_token: str,
    created_at: str,
    candidate_registry: CandidateRegistrySnapshot,
    corpus: MethodBoundExtractionCorpusSnapshot,
) -> ExperimentPlan:
    first, last = _analyzers()
    protocol = {
        "protocol": LOCAL_CONTENT_UNDERSTANDING_VERSION,
        "purpose": "content-directed inspection over authorized synthetic analyzers",
        "controls": ["material-disagreement", "no-signal-abstention"],
        "aggregation": "forbidden",
        "surveillance": "forbidden",
    }
    return ExperimentPlan(
        experiment_id=f"experiment.local-content-understanding.{run_token}",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question=(
            "Can exact synthetic measurements support content inspection without a "
            "meaning verdict, viewer profile, or restriction recommendation?"
        ),
        protocol_ref=VersionedArtifactRef(
            artifact_id="protocol.local-content-understanding",
            artifact_version="0.1.0",
            artifact_hash=canonical_sha256(protocol),
        ),
        candidate_registry_ref=candidate_registry.reference(),
        corpus_ref=corpus.reference(),
        content_ids=corpus.content_ids,
        dimension_ids=("sentiment_valence",),
        instrument_revisions=(
            InstrumentRevision(
                candidate_id="fixture.first-signal",
                analyzer_id=first.identity.analyzer_id,
                dimension_id=first.dimension_id,
                implementation_revision=first.implementation_revision,
                adapter_version=first.identity.adapter_version,
                configuration_hash=canonical_sha256(first.execution_configuration),
            ),
            InstrumentRevision(
                candidate_id="fixture.last-signal",
                analyzer_id=last.identity.analyzer_id,
                dimension_id=last.dimension_id,
                implementation_revision=last.implementation_revision,
                adapter_version=last.identity.adapter_version,
                configuration_hash=canonical_sha256(last.execution_configuration),
            ),
        ),
        metrics=(MetricDefinition("signed-valence-agreement", "0.1.0"),),
        exclusion_rules=(),
        stopping_rules=(
            "Stop after the submitted content and both synthetic controls complete.",
        ),
        created_at=created_at,
    )


def _environment(run_token: str) -> ExecutionEnvironment:
    runtime = {
        "interface_version": LOCAL_CONTENT_UNDERSTANDING_VERSION,
        "run_token": run_token,
        "method_id": IDENTITY_METHOD_ID,
        "method_revision": IDENTITY_METHOD_REVISION,
        "configuration_hash": IDENTITY_CONFIGURATION_HASH,
    }
    return ExecutionEnvironment(
        environment_id=f"environment.local-content-understanding.{run_token}",
        environment_version="0.1.0",
        python_version=platform.python_version(),
        operating_system=f"{platform.system()} {platform.release()}",
        architecture=platform.machine() or "unknown",
        dependency_lock_hash=canonical_sha256({"runtime_dependencies": []}),
        runtime_configuration_hash=canonical_sha256(runtime),
        hardware_profile="local dependency-free synthetic execution",
    )


def _understanding_from_evidence(
    *,
    evidence_view: StoredContentEvidenceView,
    submitted_content_id: str,
    context: ReaderProvidedContext,
) -> ContentUnderstandingView:
    matches = tuple(
        item for item in evidence_view.contents if item.content_id == submitted_content_id
    )
    if len(matches) != 1:
        raise LocalContentUnderstandingError(
            "submitted content ID must identify exactly one verified content item"
        )
    content = _canonical_alias(matches[0])
    return ContentUnderstandingView(
        understanding_version=CONTENT_UNDERSTANDING_VERSION,
        experiment_run_id=evidence_view.experiment_run_id,
        lifecycle_status=evidence_view.lifecycle_status,
        content_id=content.content_id,
        reader_context=context,
        evidence=content,
        observations=_observations(
            content=content,
            completion_refs=evidence_view.completion_refs,
        ),
        reflection_prompts=_reflection_prompts(context=context, content=content),
        completion_refs=evidence_view.completion_refs,
        inspection_paths=CONTENT_INSPECTION_PATHS,
        notices=CONTENT_UNDERSTANDING_NOTICES,
    )


def run_local_content_understanding(
    request: LocalContentUnderstandingRequest,
) -> LocalContentUnderstandingResult:
    """Execute authorized synthetic inspection over one local raw-text item."""

    created_at = _iso(request.started_at)
    submitted_content_id = f"submitted-content-{request.run_token}"
    graphs = (
        _graph(
            content_id=submitted_content_id,
            source_id=f"source.submitted-content.{request.run_token}",
            text=request.content_text,
            created_at=created_at,
        ),
        _graph(
            content_id=f"control-disagreement-{request.run_token}",
            source_id=f"source.control-disagreement.{request.run_token}",
            text=DISAGREEMENT_CONTROL_TEXT,
            created_at=created_at,
        ),
        _graph(
            content_id=f"control-abstention-{request.run_token}",
            source_id=f"source.control-abstention.{request.run_token}",
            text=ABSTENTION_CONTROL_TEXT,
            created_at=created_at,
        ),
    )
    candidate_registry = CandidateRegistrySnapshot.from_document(
        _load_document(request.candidate_registry_path, "candidate registry")
    )
    method_registry = ExtractionMethodRegistrySnapshot.from_document(
        _load_document(request.method_registry_path, "extraction method registry")
    )
    corpus = _method_bound_corpus(
        run_token=request.run_token,
        graphs=graphs,
        method_registry=method_registry,
        created_at=created_at,
    )
    analyzers = _analyzers()
    plan = _plan(
        run_token=request.run_token,
        created_at=created_at,
        candidate_registry=candidate_registry,
        corpus=corpus,
    )

    run_directory = request.workspace / request.run_token
    artifact_directory = run_directory / "artifacts"
    store = FileSystemArtifactStore(artifact_directory)
    persist_extracted_corpus(
        store,
        plan=plan,
        manifest=corpus.corpus,
        sources=tuple(item.source for item in graphs),
        extractions=tuple(item.extraction for item in graphs),
        contents=tuple(item.content for item in graphs),
    )
    receipt = EligibleExtractionExperimentRunner(
        analyzer_registry=_analyzer_registry(analyzers),
        artifact_store=store,
    ).run(
        plan=plan,
        candidate_registry=candidate_registry,
        method_registry=method_registry,
        corpus=corpus,
        environment=_environment(request.run_token),
        windows=_windows(content_ids=corpus.content_ids, started_at=request.started_at),
        experiment_run_id=f"local-content-understanding-{request.run_token}",
    )
    evidence_view = build_eligible_extraction_evidence_view(
        receipt=receipt,
        artifact_store=store,
    )
    understanding_view = _understanding_from_evidence(
        evidence_view=evidence_view,
        submitted_content_id=submitted_content_id,
        context=request.context,
    )
    markdown = render_content_understanding_markdown(understanding_view)
    return LocalContentUnderstandingResult(
        interface_version=LOCAL_CONTENT_UNDERSTANDING_VERSION,
        run_directory=run_directory,
        artifact_directory=artifact_directory,
        submitted_content_id=submitted_content_id,
        receipt=receipt,
        evidence_view=evidence_view,
        understanding_view=understanding_view,
        markdown=markdown,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.content_understanding_local",
        description=(
            "Run the authorized synthetic CTRT content-understanding demonstration over "
            "one local raw-text item."
        ),
    )
    parser.add_argument(
        "--content-file",
        required=True,
        help="UTF-8 content file, or '-' to read content from standard input.",
    )
    parser.add_argument(
        "--purpose",
        required=True,
        help="What you are trying to understand about the submitted content.",
    )
    parser.add_argument("--known-context", help="Optional context you already know.")
    parser.add_argument(
        "--question",
        action="append",
        default=[],
        help="Optional question ending in '?'; repeat for multiple questions.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".ctrt") / "content-understanding-runs",
        help="Directory containing one append-only artifact store per run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional Markdown output path. Without it, Markdown is printed.",
    )
    parser.add_argument(
        "--run-token",
        help="Optional reproducible lowercase run token; otherwise one is generated.",
    )
    parser.add_argument(
        "--candidate-registry",
        type=Path,
        default=DEFAULT_CANDIDATE_REGISTRY,
    )
    parser.add_argument(
        "--method-registry",
        type=Path,
        default=DEFAULT_METHOD_REGISTRY,
    )
    return parser


def _read_content(value: str) -> str:
    if value == "-":
        return sys.stdin.read()
    try:
        return Path(value).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LocalContentUnderstandingError(
            f"unable to read content file {value}"
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the bounded local synthetic demonstration."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    token = arguments.run_token or f"run-{uuid.uuid4().hex[:12]}"
    try:
        result = run_local_content_understanding(
            LocalContentUnderstandingRequest(
                content_text=_read_content(arguments.content_file),
                context=ReaderProvidedContext(
                    purpose=arguments.purpose,
                    known_context=arguments.known_context,
                    questions=tuple(arguments.question),
                ),
                workspace=arguments.workspace,
                run_token=token,
                started_at=datetime.now(UTC),
                candidate_registry_path=arguments.candidate_registry,
                method_registry_path=arguments.method_registry,
            )
        )
        if arguments.output is None:
            sys.stdout.write(result.markdown)
        else:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(result.markdown, encoding="utf-8")
            sys.stdout.write(f"Wrote content understanding to {arguments.output}\n")
        sys.stderr.write(f"Artifact store: {result.artifact_directory}\n")
    except (LocalContentUnderstandingError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"content understanding failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LOCAL_CONTENT_UNDERSTANDING_VERSION",
    "LocalContentUnderstandingError",
    "LocalContentUnderstandingRequest",
    "LocalContentUnderstandingResult",
    "main",
    "run_local_content_understanding",
]
