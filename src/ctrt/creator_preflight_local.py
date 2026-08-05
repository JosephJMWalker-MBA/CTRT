"""Dependency-free local interface for extraction-backed creator preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from ctrt.artifact_store import FileSystemArtifactStore, StoredArtifactRef
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.contracts import SourceType
from ctrt.creator_preflight import (
    CREATOR_CONTROLLED_ACTIONS,
    CREATOR_PREFLIGHT_NOTICES,
    CREATOR_PREFLIGHT_VERSION,
    CreatorPreflightView,
    CreatorProvidedContext,
    _observations,
    _reflection_prompts,
    render_creator_preflight_markdown,
)
from ctrt.eligible_extraction_evidence import (
    build_eligible_extraction_evidence_view,
)
from ctrt.eligible_extraction_runner import (
    EligibleExtractionExperimentRunner,
    VerifiedEligibleExtractionExperimentReceipt,
)
from ctrt.evidence_view import (
    ContentEvidenceView,
    EvidenceArtifactReference,
    StoredContentEvidenceView,
)
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionManifestSnapshot,
    SourceArtifactSnapshot,
    extracted_content_artifact_id,
    extraction_artifact_id,
    persist_extracted_corpus,
    source_artifact_id,
)
from ctrt.extraction_method_eligibility import (
    ExtractionMethodRegistrySnapshot,
    MethodBoundExtractionCorpusSnapshot,
)
from ctrt.serialization import canonical_sha256
from ctrt.synthetic import (
    PositionalSentimentFixture,
    first_signal_fixture,
    last_signal_fixture,
)
from ctrt.workbench import AnalyzerRegistry

LOCAL_PREFLIGHT_VERSION = "ctrt-local-creator-preflight@0.1.0"
IDENTITY_METHOD_ID = "synthetic.identity-text"
IDENTITY_METHOD_REVISION = "ctrt-synthetic-identity-text@0.1.0"
IDENTITY_CONFIGURATION_HASH = (
    "sha256:bc8e485583a873ac9269382749b2ff803b649939b3ec829ec8bf140db6e350c8"
)
DISAGREEMENT_CONTROL_TEXT = "The launch was good, but the support was bad."
ABSTENTION_CONTROL_TEXT = "The report contains no fixture vocabulary."
_RUN_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_CANDIDATE_REGISTRY = (
    _repo_root() / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
)
DEFAULT_METHOD_REGISTRY = (
    _repo_root()
    / "docs"
    / "candidates"
    / "synthetic-extraction-method-registry.v0.1.0.json"
)


class LocalCreatorPreflightError(ValueError):
    """Raised when local creator preflight input cannot support exact execution."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LocalCreatorPreflightError(f"{field_name} must be a JSON object")
    if any(not isinstance(key, str) for key in value):
        raise LocalCreatorPreflightError(f"{field_name} keys must be strings")
    return cast(Mapping[str, object], value)


def _load_document(path: Path, field_name: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalCreatorPreflightError(
            f"unable to read {field_name} from {path}"
        ) from exc
    return _mapping(value, field_name)


def _text_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


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


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise LocalCreatorPreflightError("started_at must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_run_token(value: str) -> None:
    if _RUN_TOKEN_PATTERN.fullmatch(value) is None:
        raise LocalCreatorPreflightError(
            "run_token must contain 8-64 lowercase letters, digits, or hyphens"
        )


@dataclass(frozen=True, slots=True)
class LocalCreatorPreflightRequest:
    """One local draft and its non-evidentiary creator context."""

    draft_text: str
    context: CreatorProvidedContext
    workspace: Path
    run_token: str
    started_at: datetime
    candidate_registry_path: Path = DEFAULT_CANDIDATE_REGISTRY
    method_registry_path: Path = DEFAULT_METHOD_REGISTRY

    def __post_init__(self) -> None:
        if not self.draft_text.strip():
            raise LocalCreatorPreflightError("draft_text must not be empty")
        _validate_run_token(self.run_token)
        if self.started_at.tzinfo is None:
            raise LocalCreatorPreflightError("started_at must include a timezone")


@dataclass(frozen=True, slots=True)
class _ExtractionGraph:
    source: SourceArtifactSnapshot
    extraction: ExtractionManifestSnapshot
    content: ExtractedContentSnapshot


@dataclass(frozen=True, slots=True)
class LocalCreatorPreflightResult:
    """Verified local synthetic execution and its noncanonical creator view."""

    interface_version: str
    run_directory: Path
    artifact_directory: Path
    draft_content_id: str
    receipt: VerifiedEligibleExtractionExperimentReceipt
    evidence_view: StoredContentEvidenceView
    preflight_view: CreatorPreflightView
    markdown: str

    def __post_init__(self) -> None:
        if self.interface_version != LOCAL_PREFLIGHT_VERSION:
            raise ValueError("unsupported local creator preflight version")
        if self.draft_content_id != self.preflight_view.content_id:
            raise ValueError("local result draft identity must match preflight")
        if self.receipt.experiment_run_id != self.preflight_view.experiment_run_id:
            raise ValueError("local result run identity must remain exact")


def _graph(
    *,
    content_id: str,
    source_id: str,
    text: str,
    created_at: str,
) -> _ExtractionGraph:
    content_hash = _text_hash(text)
    source = SourceArtifactSnapshot.from_document(
        {
            "artifact_id": source_artifact_id(source_id, content_hash),
            "source_id": source_id,
            "text": text,
            "source_hash": content_hash,
            "source_type": SourceType.RAW_TEXT.value,
            "source_uri": None,
        }
    )
    extraction_id = extraction_artifact_id(
        content_id=content_id,
        source_artifact_ref=source.reference(),
        method_id=IDENTITY_METHOD_ID,
        method_revision=IDENTITY_METHOD_REVISION,
        configuration_hash=IDENTITY_CONFIGURATION_HASH,
        canonical_content_hash=content_hash,
    )
    content = ExtractedContentSnapshot.from_document(
        {
            "artifact_id": extracted_content_artifact_id(
                content_id,
                content_hash,
                extraction_id,
            ),
            "content_id": content_id,
            "text": text,
            "content_hash": content_hash,
            "language": "en",
            "source_type": SourceType.RAW_TEXT.value,
            "source_uri": None,
            "extraction_ref": extraction_id,
        }
    )
    extraction = ExtractionManifestSnapshot.from_document(
        {
            "artifact_id": extraction_id,
            "content_id": content_id,
            "source_artifact_ref": _stored_ref_document(source.reference()),
            "method_id": IDENTITY_METHOD_ID,
            "method_revision": IDENTITY_METHOD_REVISION,
            "configuration_hash": IDENTITY_CONFIGURATION_HASH,
            "canonical_content_hash": content_hash,
            "content_artifact_ref": _stored_ref_document(content.reference()),
            "coordinate_map": [
                {
                    "source_start": 0,
                    "source_end": len(text),
                    "canonical_start": 0,
                    "canonical_end": len(text),
                    "kind": "exact",
                }
            ],
            "created_at": created_at,
        }
    )
    extraction.verify(source, content)
    return _ExtractionGraph(source=source, extraction=extraction, content=content)


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
            "corpus_id": f"corpus.local-creator-preflight.{run_token}",
            "corpus_version": "0.1.0",
            "status": "frozen",
            "method_registry_ref": _versioned_ref_document(
                method_registry.reference()
            ),
            "contents": contents,
            "created_at": created_at,
        }
    )


def _analyzers() -> tuple[PositionalSentimentFixture, PositionalSentimentFixture]:
    return first_signal_fixture(), last_signal_fixture()


def _analyzer_registry(
    analyzers: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for analyzer in analyzers:
        registry.register(analyzer)
    return registry


def _plan(
    *,
    run_token: str,
    created_at: str,
    candidate_registry: CandidateRegistrySnapshot,
    corpus: MethodBoundExtractionCorpusSnapshot,
    analyzers: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = analyzers
    protocol = {
        "protocol": LOCAL_PREFLIGHT_VERSION,
        "purpose": "creator reflection over authorized synthetic analyzers",
        "controls": ["material-disagreement", "no-signal-abstention"],
        "aggregation": "forbidden",
    }
    return ExperimentPlan(
        experiment_id=f"experiment.local-creator-preflight.{run_token}",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question=(
            "Can exact synthetic measurements support creator reflection without a "
            "publish recommendation?"
        ),
        protocol_ref=VersionedArtifactRef(
            artifact_id="protocol.local-creator-preflight",
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
            "Stop after the submitted draft and both synthetic controls complete.",
        ),
        created_at=created_at,
    )


def _environment(run_token: str) -> ExecutionEnvironment:
    runtime = {
        "interface_version": LOCAL_PREFLIGHT_VERSION,
        "run_token": run_token,
        "method_id": IDENTITY_METHOD_ID,
        "method_revision": IDENTITY_METHOD_REVISION,
        "configuration_hash": IDENTITY_CONFIGURATION_HASH,
    }
    return ExecutionEnvironment(
        environment_id=f"environment.local-creator-preflight.{run_token}",
        environment_version="0.1.0",
        python_version=platform.python_version(),
        operating_system=f"{platform.system()} {platform.release()}",
        architecture=platform.machine() or "unknown",
        dependency_lock_hash=canonical_sha256({"runtime_dependencies": []}),
        runtime_configuration_hash=canonical_sha256(runtime),
        hardware_profile="local dependency-free synthetic execution",
    )


def _windows(
    *,
    content_ids: tuple[str, ...],
    started_at: datetime,
) -> tuple[ExtractionExecutionWindow, ...]:
    windows: list[ExtractionExecutionWindow] = []
    for index, content_id in enumerate(content_ids):
        start = started_at + timedelta(seconds=(index * 2) + 1)
        completed = start + timedelta(seconds=1)
        windows.append(
            ExtractionExecutionWindow(
                content_id=content_id,
                started_at=_iso(start),
                completed_at=_iso(completed),
            )
        )
    return tuple(windows)


def _canonical_alias(content: ContentEvidenceView) -> ContentEvidenceView:
    extracted = tuple(
        item for item in content.artifact_refs if item.role == "extracted-content"
    )
    if len(extracted) != 1:
        raise LocalCreatorPreflightError(
            "creator draft must have exactly one extracted-content reference"
        )
    alias = EvidenceArtifactReference(
        role="canonical-content",
        artifact_id=extracted[0].artifact_id,
        artifact_hash=extracted[0].artifact_hash,
    )
    return replace(content, artifact_refs=(*content.artifact_refs, alias))


def _preflight_from_evidence(
    *,
    evidence_view: StoredContentEvidenceView,
    draft_content_id: str,
    context: CreatorProvidedContext,
) -> CreatorPreflightView:
    matches = tuple(
        item for item in evidence_view.contents if item.content_id == draft_content_id
    )
    if len(matches) != 1:
        raise LocalCreatorPreflightError(
            "draft content ID must identify exactly one verified content item"
        )
    content = _canonical_alias(matches[0])
    return CreatorPreflightView(
        preflight_version=CREATOR_PREFLIGHT_VERSION,
        experiment_run_id=evidence_view.experiment_run_id,
        lifecycle_status=evidence_view.lifecycle_status,
        content_id=content.content_id,
        creator_context=context,
        evidence=content,
        observations=_observations(
            content=content,
            completion_refs=evidence_view.completion_refs,
        ),
        reflection_prompts=_reflection_prompts(context=context, content=content),
        completion_refs=evidence_view.completion_refs,
        creator_controlled_actions=CREATOR_CONTROLLED_ACTIONS,
        notices=CREATOR_PREFLIGHT_NOTICES,
    )


def run_local_creator_preflight(
    request: LocalCreatorPreflightRequest,
) -> LocalCreatorPreflightResult:
    """Execute one authorized local synthetic preflight and render its evidence."""

    created_at = _iso(request.started_at)
    draft_content_id = f"creator-draft-{request.run_token}"
    graphs = (
        _graph(
            content_id=draft_content_id,
            source_id=f"source.creator-draft.{request.run_token}",
            text=request.draft_text,
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
        analyzers=analyzers,
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
    runner = EligibleExtractionExperimentRunner(
        analyzer_registry=_analyzer_registry(analyzers),
        artifact_store=store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate_registry,
        method_registry=method_registry,
        corpus=corpus,
        environment=_environment(request.run_token),
        windows=_windows(content_ids=corpus.content_ids, started_at=request.started_at),
        experiment_run_id=f"local-creator-preflight-{request.run_token}",
    )
    evidence_view = build_eligible_extraction_evidence_view(
        receipt=receipt,
        artifact_store=store,
    )
    preflight_view = _preflight_from_evidence(
        evidence_view=evidence_view,
        draft_content_id=draft_content_id,
        context=request.context,
    )
    markdown = render_creator_preflight_markdown(preflight_view)
    return LocalCreatorPreflightResult(
        interface_version=LOCAL_PREFLIGHT_VERSION,
        run_directory=run_directory,
        artifact_directory=artifact_directory,
        draft_content_id=draft_content_id,
        receipt=receipt,
        evidence_view=evidence_view,
        preflight_view=preflight_view,
        markdown=markdown,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.creator_preflight_local",
        description=(
            "Run the authorized synthetic CTRT creator-preflight demonstration over "
            "one local raw-text draft."
        ),
    )
    parser.add_argument(
        "--draft-file",
        required=True,
        help="UTF-8 draft file, or '-' to read the draft from standard input.",
    )
    parser.add_argument("--intent", required=True, help="What you intend to communicate.")
    parser.add_argument("--audience", help="Optional intended audience.")
    parser.add_argument(
        "--concern",
        action="append",
        default=[],
        help="Optional concern; repeat this option for multiple concerns.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".ctrt") / "creator-preflight-runs",
        help="Directory that will contain one append-only artifact store per run.",
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


def _read_draft(value: str) -> str:
    if value == "-":
        return sys.stdin.read()
    try:
        return Path(value).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LocalCreatorPreflightError(f"unable to read draft file {value}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the bounded local synthetic demonstration."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    token = arguments.run_token or f"run-{uuid.uuid4().hex[:12]}"
    try:
        result = run_local_creator_preflight(
            LocalCreatorPreflightRequest(
                draft_text=_read_draft(arguments.draft_file),
                context=CreatorProvidedContext(
                    intent=arguments.intent,
                    intended_audience=arguments.audience,
                    concerns=tuple(arguments.concern),
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
            sys.stdout.write(f"Wrote creator preflight to {arguments.output}\n")
        sys.stderr.write(f"Artifact store: {result.artifact_directory}\n")
    except (LocalCreatorPreflightError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"creator preflight failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
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
