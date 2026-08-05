from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.candidate_eligibility import (
    CandidateCapability,
    CandidateDisposition,
    CandidateRegistrySnapshot,
    LicenseReviewStatus,
    RegistryLifecycle,
)
from ctrt.confidence import (
    AgreementStatus,
    ApplicabilityStatus,
    CalibrationStatus,
    ExtractionQualityStatus,
)
from ctrt.contracts import Analyzer, ContentItem, ResultStatus, SourceType
from ctrt.measurement import AnalysisTarget, EvidenceSupportStatus
from ctrt.real_candidate_registry import (
    EvidenceLocalization,
    RealCandidateRegistryError,
    real_candidate_binding,
)
from ctrt.vader_adapter import (
    MAX_CONTENT_CHARACTERS,
    OUTPUT_BOUNDS,
    PRESERVED_OUTPUT_KEYS,
    VADER_ADAPTER_REVISION,
    VADER_ANALYZER_ID,
    VADER_CANDIDATE_ID,
    VADER_DISTRIBUTION,
    VADER_PINNED_VERSION,
    VADER_TAXONOMY_ID,
    VaderAdapterError,
    VaderDependencyError,
    VaderSentimentAdapter,
    installed_vader_version,
    load_vader_sentiment_adapter,
    vader_configuration_hash,
    vader_execution_configuration,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_REGISTRY_PATH = REPO_ROOT / "docs" / "candidates" / "real-registry.v0.1.0.json"
SYNTHETIC_REGISTRY_PATH = REPO_ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"

VADER_INSTALLED = importlib.util.find_spec("vaderSentiment") is not None
requires_vader = pytest.mark.skipif(
    not VADER_INSTALLED,
    reason="optional candidate dependency vaderSentiment==3.3.2 is not installed",
)
requires_no_vader = pytest.mark.skipif(
    VADER_INSTALLED,
    reason="requires an environment without the optional vaderSentiment dependency",
)


def _registry_document() -> Mapping[str, object]:
    return cast(
        dict[str, Any],
        json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8")),
    )


def _content(
    *,
    text: str = "This plan is good, but the delay feels bad.",
    language: str | None = "en",
    extraction_ref: str | None = "extraction:vader-test-0001",
) -> ContentItem:
    return ContentItem(
        content_id="vader-test-content",
        text=text,
        source_type=SourceType.RAW_TEXT,
        content_hash="sha256:" + ("a" * 64),
        language=language,
        extraction_ref=extraction_ref,
    )


@pytest.fixture
def adapter() -> VaderSentimentAdapter:
    return load_vader_sentiment_adapter()


# --------------------------------------------------------------------------
# Registry admission state
# --------------------------------------------------------------------------


def test_real_registry_admits_vader_as_eligible_for_evaluation_only() -> None:
    snapshot = CandidateRegistrySnapshot.from_document(_registry_document())

    assert snapshot.registry_id == "registry.real-candidates"
    assert snapshot.status is RegistryLifecycle.ACCEPTED
    assert len(snapshot.candidates) == 1, "this PR admits exactly one real candidate"

    record = snapshot.candidate(VADER_CANDIDATE_ID)
    assert record is not None
    assert record.capability_type is CandidateCapability.ANALYZER
    assert record.status is CandidateDisposition.ELIGIBLE_FOR_EVALUATION
    assert record.status is not CandidateDisposition.EVALUATED
    assert record.status is not CandidateDisposition.SELECTED_FOR_DOMAIN
    assert record.dimensions == ("sentiment_valence",)
    assert record.authorized_analyzer_ids == (VADER_ANALYZER_ID,)
    assert record.pin_required is True
    assert record.pinned_revision == VADER_ADAPTER_REVISION


def test_license_review_is_provisional_with_recorded_evidence() -> None:
    snapshot = CandidateRegistrySnapshot.from_document(_registry_document())
    record = snapshot.candidate(VADER_CANDIDATE_ID)
    assert record is not None

    # Provisional, not verified: bundled-lexicon terms and a declared transitive
    # dependency remain unresolved even though the MIT text itself was read.
    assert record.license_status is LicenseReviewStatus.PROVISIONALLY_VERIFIED
    assert record.license_status is not LicenseReviewStatus.VERIFIED

    candidate = cast(
        list[dict[str, Any]], _registry_document()["candidates"]
    )[0]
    review = cast(dict[str, Any], candidate["license_review"])
    notes = cast(str, review["notes"])
    assert review["declared_license"] == "MIT License"
    assert "74cfe41cdbf7f6925aeb4c18c148ec8db042540edb6739fd81069aa4e3c8b118" in notes
    assert "vader_lexicon.txt" in notes
    assert "requests" in notes


def test_real_candidate_binding_records_every_required_fact() -> None:
    binding = real_candidate_binding(_registry_document(), VADER_CANDIDATE_ID)

    assert binding.package.distribution == VADER_DISTRIBUTION
    assert binding.package.version == VADER_PINNED_VERSION
    assert binding.package.requirement == "vaderSentiment==3.3.2"
    assert binding.package.dependency_extra == "vader"
    assert binding.taxonomy_id == VADER_TAXONOMY_ID
    assert binding.taxonomy_version == VADER_PINNED_VERSION
    assert binding.configuration_hash == vader_configuration_hash()
    assert binding.evidence_localization is EvidenceLocalization.UNAVAILABLE
    assert binding.execution_boundary.user_facing_execution_permitted is False
    assert binding.execution_boundary.requires_selection_record is True


def test_binding_rejects_a_record_permitting_user_facing_execution() -> None:
    document = cast(dict[str, Any], _registry_document())
    candidate = cast(list[dict[str, Any]], document["candidates"])[0]
    candidate["execution_boundary"]["user_facing_execution_permitted"] = True

    with pytest.raises(RealCandidateRegistryError, match="user-facing execution"):
        real_candidate_binding(document, VADER_CANDIDATE_ID)


def test_binding_rejects_a_missing_candidate_and_missing_facts() -> None:
    with pytest.raises(RealCandidateRegistryError, match="absent from the registry"):
        real_candidate_binding(_registry_document(), "not.a.candidate")

    document = cast(dict[str, Any], _registry_document())
    candidate = cast(list[dict[str, Any]], document["candidates"])[0]
    del candidate["package_binding"]
    with pytest.raises(RealCandidateRegistryError, match="package_binding"):
        real_candidate_binding(document, VADER_CANDIDATE_ID)


def test_synthetic_registry_is_untouched_and_holds_no_real_candidate() -> None:
    document = cast(
        dict[str, Any],
        json.loads(SYNTHETIC_REGISTRY_PATH.read_text(encoding="utf-8")),
    )
    snapshot = CandidateRegistrySnapshot.from_document(document)

    assert snapshot.registry_id == "registry.synthetic-fixtures"
    assert tuple(item.candidate_id for item in snapshot.candidates) == (
        "fixture.first-signal",
        "fixture.last-signal",
    )
    assert VADER_CANDIDATE_ID not in {item.candidate_id for item in snapshot.candidates}
    assert "vader" not in SYNTHETIC_REGISTRY_PATH.read_text(encoding="utf-8").lower()


# --------------------------------------------------------------------------
# Dependency boundary
# --------------------------------------------------------------------------


def test_core_synthetic_path_imports_without_the_optional_dependency() -> None:
    """The dependency-free default path must never import vaderSentiment."""

    for module_name in (
        "ctrt",
        "ctrt.synthetic",
        "ctrt.workbench",
        "ctrt.creator_preflight",
        "ctrt.creator_preflight_local",
        "ctrt.creator_preflight_web",
    ):
        importlib.import_module(module_name)
    assert "vaderSentiment" not in sys.modules


def test_synthetic_analyzers_still_execute_without_vader() -> None:
    from ctrt.synthetic import first_signal_fixture, last_signal_fixture

    content = _content()
    for fixture in (first_signal_fixture(), last_signal_fixture()):
        result = fixture.analyze(content)
        assert result.status is ResultStatus.SUCCESS
    assert "vaderSentiment" not in sys.modules


def test_importing_the_adapter_module_does_not_import_the_dependency() -> None:
    module = importlib.import_module("ctrt.vader_adapter")

    assert module.VADER_PINNED_VERSION == "3.3.2"
    # Loading the adapter module is safe; only load_vader_sentiment_adapter()
    # touches the optional distribution.
    tree = ast.parse(Path(cast(str, module.__file__)).read_text(encoding="utf-8"))
    top_level_imports = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        cast(str, node.module).split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "vaderSentiment" not in top_level_imports


@requires_no_vader
def test_adapter_fails_closed_when_the_optional_dependency_is_absent() -> None:
    with pytest.raises(VaderDependencyError, match="is not installed"):
        installed_vader_version()
    with pytest.raises(VaderDependencyError, match=r"ctrt-framework\[vader\]"):
        load_vader_sentiment_adapter()


def test_adapter_rejects_an_unpinned_package_version() -> None:
    with pytest.raises(VaderAdapterError, match="3.3.2"):
        VaderSentimentAdapter(package_version="3.3.1", _scorer=object())


def test_adapter_requires_a_loaded_scorer() -> None:
    with pytest.raises(VaderAdapterError, match="loaded polarity scorer"):
        VaderSentimentAdapter(package_version=VADER_PINNED_VERSION)


def test_configuration_hash_changes_with_the_package_version() -> None:
    assert vader_configuration_hash("3.3.2") != vader_configuration_hash("3.3.1")
    assert vader_configuration_hash() == vader_configuration_hash("3.3.2")


def test_declared_configuration_is_complete_and_reproducible() -> None:
    configuration = vader_execution_configuration(VADER_PINNED_VERSION)

    assert configuration["distribution"] == VADER_DISTRIBUTION
    assert configuration["distribution_version"] == VADER_PINNED_VERSION
    assert configuration["adapter_revision"] == VADER_ADAPTER_REVISION
    assert configuration["network_access"] is False
    assert configuration["runtime_lexicon_download"] is False
    assert configuration["supported_languages"] == ["en"]
    assert configuration["preserved_output_keys"] == list(PRESERVED_OUTPUT_KEYS)
    assert vader_configuration_hash() == vader_configuration_hash()


# --------------------------------------------------------------------------
# Adapter behavior (requires the optional dependency)
# --------------------------------------------------------------------------


@requires_vader
def test_adapter_records_the_exact_installed_distribution_and_revisions(
    adapter: VaderSentimentAdapter,
) -> None:
    assert installed_vader_version() == VADER_PINNED_VERSION
    assert adapter.package_version == VADER_PINNED_VERSION
    # Package revision and adapter revision are preserved separately.
    assert adapter.implementation_revision == VADER_ADAPTER_REVISION
    assert adapter.identity.adapter_version == "0.1.0"
    assert adapter.identity.model_version == VADER_PINNED_VERSION
    assert adapter.identity.analyzer_id == VADER_ANALYZER_ID
    assert adapter.identity.taxonomy_id == VADER_TAXONOMY_ID
    assert adapter.dimension_id == "sentiment_valence"
    assert isinstance(adapter, Analyzer)


@requires_vader
def test_adapter_configuration_matches_the_registry_hash(
    adapter: VaderSentimentAdapter,
) -> None:
    from ctrt.serialization import canonical_sha256

    binding = real_candidate_binding(_registry_document(), VADER_CANDIDATE_ID)
    assert canonical_sha256(adapter.execution_configuration) == binding.configuration_hash


@requires_vader
def test_repeated_execution_is_deterministic(adapter: VaderSentimentAdapter) -> None:
    content = _content()
    first = adapter.analyze(content)
    second = adapter.analyze(content)

    assert first.raw_output == second.raw_output
    assert first.normalized_scores == second.normalized_scores
    assert first.result_id == second.result_id
    assert first.configuration == second.configuration


@requires_vader
def test_raw_vader_outputs_are_preserved_exactly(
    adapter: VaderSentimentAdapter,
) -> None:
    content = _content()
    result = adapter.analyze(content)

    assert result.status is ResultStatus.SUCCESS
    assert set(result.raw_output) == set(PRESERVED_OUTPUT_KEYS)

    # The preserved raw output equals what the pinned package itself returned.
    module = importlib.import_module("vaderSentiment.vaderSentiment")
    upstream = module.SentimentIntensityAnalyzer().polarity_scores(content.text)
    assert result.raw_output == upstream


@requires_vader
def test_each_output_retains_its_own_key_and_declared_bounds(
    adapter: VaderSentimentAdapter,
) -> None:
    result = adapter.analyze(_content())

    scores = {item.key: item for item in result.normalized_scores}
    assert tuple(item.key for item in result.normalized_scores) == PRESERVED_OUTPUT_KEYS
    for key, (lower, upper) in OUTPUT_BOUNDS.items():
        assert scores[key].lower_bound == lower
        assert scores[key].upper_bound == upper
        assert scores[key].value == result.raw_output[key]
    # compound keeps its own [-1, 1] bounds rather than the proportion bounds.
    assert scores["compound"].lower_bound == -1.0
    assert scores["neg"].lower_bound == 0.0


@requires_vader
def test_no_aggregate_score_or_confidence_relabeling_occurs(
    adapter: VaderSentimentAdapter,
) -> None:
    result = adapter.analyze(_content())

    # Exactly the four preserved outputs; no fifth combined value.
    assert len(result.normalized_scores) == len(PRESERVED_OUTPUT_KEYS)
    for forbidden in ("overall", "score", "ctrt", "verdict", "confidence", "valence"):
        assert forbidden not in {item.key for item in result.normalized_scores}

    # No VADER number may reach any confidence-bearing numeric field.
    confidence = result.confidence
    assert confidence.instrument_probability.value is None
    assert confidence.instrument_probability.source is None
    assert confidence.inter_instrument_agreement.value is None
    assert confidence.inter_instrument_agreement.metric is None
    assert confidence.calibration.evidence_ref is None

    emitted = {float(result.raw_output[key]) for key in PRESERVED_OUTPUT_KEYS}
    numeric_confidence_fields = {
        confidence.instrument_probability.value,
        confidence.inter_instrument_agreement.value,
    }
    assert numeric_confidence_fields == {None}
    assert not emitted & {
        value for value in numeric_confidence_fields if value is not None
    }
    # compound in particular is preserved only as its own bounded measurement.
    compound = next(
        item for item in result.normalized_scores if item.key == "compound"
    )
    assert compound.value == result.raw_output["compound"]
    assert result.status is ResultStatus.SUCCESS


@requires_vader
def test_evidence_support_is_unavailable_with_no_fabricated_spans(
    adapter: VaderSentimentAdapter,
) -> None:
    result = adapter.analyze(_content())

    assert result.evidence_support.status is EvidenceSupportStatus.UNAVAILABLE
    assert result.evidence_support.method_id is None
    assert result.evidence_spans == ()
    assert "does not identify which passage" in result.evidence_support.notes
    assert any(
        "does not identify which passage" in item
        for item in result.confidence.ambiguity_budget.preserved_uncertainties
    )


@requires_vader
def test_confidence_dimensions_remain_separate_and_unclaimed(
    adapter: VaderSentimentAdapter,
) -> None:
    confidence = adapter.analyze(_content()).confidence

    assert confidence.calibration.status is CalibrationStatus.UNKNOWN
    assert confidence.calibration.method is None
    assert confidence.calibration.domain is None
    assert confidence.applicability.status is ApplicabilityStatus.UNKNOWN
    assert any(
        "No CTRT evaluation" in reason for reason in confidence.applicability.reasons
    )
    assert confidence.inter_instrument_agreement.status is (
        AgreementStatus.SINGLE_INSTRUMENT
    )
    assert confidence.inter_instrument_agreement.participants == (VADER_ANALYZER_ID,)
    assert confidence.inter_instrument_agreement.value is None
    assert confidence.ambiguity_budget.preserved_uncertainties
    assert confidence.system_abstention.triggered is False


@requires_vader
def test_extraction_quality_references_the_exact_canonical_extraction_identity(
    adapter: VaderSentimentAdapter,
) -> None:
    content = _content(extraction_ref="extraction:exact-identity-42")
    result = adapter.analyze(content)

    assert result.analysis_target.extraction_ref == "extraction:exact-identity-42"
    assert result.confidence.extraction_quality.evidence_ref == (
        content.canonical_extraction_ref
    )
    assert result.confidence.extraction_quality.status is ExtractionQualityStatus.CLEAN


@requires_vader
def test_results_pass_existing_workbench_target_validation(
    adapter: VaderSentimentAdapter,
) -> None:
    content = _content()
    result = adapter.analyze(content)

    expected_target = AnalysisTarget.for_content_item(
        content_id=content.content_id,
        content_length=len(content.text),
        extraction_ref=content.canonical_extraction_ref,
    )
    assert result.analysis_target == expected_target
    assert result.content_id == content.content_id
    assert result.dimension_id == adapter.dimension_id
    assert result.analyzer == adapter.identity
    assert result.configuration == adapter.execution_configuration


@requires_vader
@pytest.mark.parametrize("language", ["fr", "de", "es", "zh"])
def test_unsupported_declared_language_triggers_abstention(
    adapter: VaderSentimentAdapter,
    language: str,
) -> None:
    result = adapter.analyze(_content(language=language))

    assert result.status is ResultStatus.ABSTAINED
    assert result.normalized_scores == ()
    assert result.evidence_spans == ()
    assert result.confidence.system_abstention.triggered is True
    assert "out-of-domain" in result.confidence.system_abstention.reasons
    assert result.confidence.applicability.status is ApplicabilityStatus.OUT_OF_DOMAIN
    assert result.raw_output["scored"] is False


@requires_vader
def test_undeclared_language_abstains_without_inferring_from_text(
    adapter: VaderSentimentAdapter,
) -> None:
    result = adapter.analyze(_content(language=None))

    assert result.status is ResultStatus.ABSTAINED
    assert "never inferred" in " ".join(result.confidence.applicability.reasons)


@requires_vader
def test_content_beyond_the_declared_adapter_limit_abstains(
    adapter: VaderSentimentAdapter,
) -> None:
    oversized = _content(text="good " * (MAX_CONTENT_CHARACTERS // 2))
    assert len(oversized.text) > MAX_CONTENT_CHARACTERS

    result = adapter.analyze(oversized)
    assert result.status is ResultStatus.ABSTAINED
    assert result.normalized_scores == ()
    assert "short-form adapter limit" in " ".join(
        result.confidence.applicability.reasons
    )


@requires_vader
def test_out_of_contract_package_output_fails_closed_without_measuring() -> None:
    class BrokenScorer:
        @staticmethod
        def polarity_scores(text: str) -> dict[str, float]:
            return {"neg": 0.0, "neu": 0.0, "pos": 0.0, "compound": 7.5}

    adapter = VaderSentimentAdapter(
        package_version=VADER_PINNED_VERSION,
        _scorer=BrokenScorer(),
    )
    result = adapter.analyze(_content())

    assert result.status is ResultStatus.FAILED
    assert result.normalized_scores == ()
    assert result.evidence_spans == ()
    assert any("outside its declared bounds" in item for item in result.errors)


@requires_vader
def test_missing_package_output_key_fails_closed() -> None:
    class PartialScorer:
        @staticmethod
        def polarity_scores(text: str) -> dict[str, float]:
            return {"neg": 0.0, "neu": 1.0, "pos": 0.0}

    adapter = VaderSentimentAdapter(
        package_version=VADER_PINNED_VERSION,
        _scorer=PartialScorer(),
    )
    result = adapter.analyze(_content())

    assert result.status is ResultStatus.FAILED
    assert any("omitted required output key 'compound'" in item for item in result.errors)


@requires_vader
def test_analysis_performs_no_network_access(
    adapter: VaderSentimentAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scoring path must not open a socket or import the requests library."""

    import socket

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("analysis attempted network access")

    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    sys.modules.pop("requests", None)

    result = adapter.analyze(_content())
    assert result.status is ResultStatus.SUCCESS
    assert "requests" not in sys.modules


# --------------------------------------------------------------------------
# Boundaries against user-facing execution
# --------------------------------------------------------------------------


def _iter_source_modules() -> Iterator[Path]:
    yield from (REPO_ROOT / "src" / "ctrt").glob("*.py")


def test_no_user_facing_module_imports_or_registers_vader() -> None:
    """Creator preflight, the local CLI, and the browser must not reach VADER."""

    user_facing = (
        "creator_preflight.py",
        "creator_preflight_local.py",
        "creator_preflight_web.py",
        "synthetic.py",
        "workbench.py",
        "__init__.py",
        "_public_api_base.py",
    )
    for name in user_facing:
        source = (REPO_ROOT / "src" / "ctrt" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            cast(str, node.module)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any("vader" in item.lower() for item in imported), name
        assert "vaderSentiment" not in source, name


def test_creator_preflight_run_registers_only_synthetic_analyzers(
    tmp_path: Path,
) -> None:
    """Behavioral proof that admission did not wire VADER into user-facing runs."""

    from datetime import UTC, datetime

    from ctrt.creator_preflight import CreatorProvidedContext
    from ctrt.creator_preflight_local import (
        LocalCreatorPreflightRequest,
        run_local_creator_preflight,
    )

    result = run_local_creator_preflight(
        LocalCreatorPreflightRequest(
            draft_text="This plan is good, but the delay feels bad.",
            context=CreatorProvidedContext(intent="Explain both sides."),
            workspace=tmp_path / "runs",
            run_token="boundarytest01",
            started_at=datetime(2026, 8, 5, 16, 0, tzinfo=UTC),
        )
    )

    analyzer_ids = {
        item.analyzer_id for item in result.preflight_view.evidence.measurements
    }
    assert analyzer_ids == {
        "synthetic.sentiment.first-signal",
        "synthetic.sentiment.last-signal",
    }
    assert VADER_ANALYZER_ID not in analyzer_ids
    assert "vader" not in result.markdown.lower()

    stored = b"\n".join(
        path.read_bytes()
        for path in result.artifact_directory.rglob("*")
        if path.is_file()
    )
    assert b"vader" not in stored.lower()


def test_public_exports_remain_bounded() -> None:
    import ctrt
    import ctrt.real_candidate_registry as registry_module
    import ctrt.vader_adapter as adapter_module

    assert adapter_module.__all__ == [
        "DECLARED_DOMAIN",
        "MAX_CONTENT_CHARACTERS",
        "OUTPUT_BOUNDS",
        "PRESERVED_OUTPUT_KEYS",
        "SUPPORTED_LANGUAGES",
        "VADER_ADAPTER_REVISION",
        "VADER_ANALYZER_ID",
        "VADER_CANDIDATE_ID",
        "VADER_DISTRIBUTION",
        "VADER_PINNED_VERSION",
        "VADER_TAXONOMY_ID",
        "VaderAdapterError",
        "VaderDependencyError",
        "VaderSentimentAdapter",
        "installed_vader_version",
        "load_vader_sentiment_adapter",
        "vader_configuration_hash",
        "vader_execution_configuration",
    ]
    assert registry_module.__all__ == [
        "EvidenceLocalization",
        "ExecutionBoundary",
        "PackageBinding",
        "RealCandidateBinding",
        "RealCandidateRegistryError",
        "parse_real_candidate_binding",
        "real_candidate_binding",
    ]
    # The real candidate stays out of the top-level contract package.
    assert not [name for name in ctrt.__all__ if "vader" in name.lower()]
