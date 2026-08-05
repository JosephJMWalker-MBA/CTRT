from __future__ import annotations

import ast
import importlib.util
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from ctrt.behavioral_probe_corpus import (
    BehavioralProbeCorpusError,
    ProbeExpectationBasis,
    ProbeExpectationKind,
    load_behavioral_probe_corpus,
    probe_content_hash,
)
from ctrt.candidate_eligibility import (
    CandidateDisposition,
    CandidateRegistrySnapshot,
)
from ctrt.contracts import ResultStatus
from ctrt.real_candidate_registry import real_candidate_binding
from ctrt.vader_adapter import (
    PRESERVED_OUTPUT_KEYS,
    VADER_ADAPTER_REVISION,
    VADER_ANALYZER_ID,
    VADER_CANDIDATE_ID,
    VADER_PINNED_VERSION,
    VaderDependencyError,
    vader_configuration_hash,
)
from ctrt.vader_characterization import (
    CHARACTERIZATION_NON_CLAIMS,
    CHARACTERIZATION_RECORD_TYPE,
    CHARACTERIZATION_VERSION,
    DEFAULT_PROBE_CORPUS,
    DEFAULT_REAL_REGISTRY,
    CharacterizationRequest,
    VaderCharacterizationError,
    VerifiedCharacterizationRun,
    main,
    run_vader_characterization,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

VADER_INSTALLED = importlib.util.find_spec("vaderSentiment") is not None
requires_vader = pytest.mark.skipif(
    not VADER_INSTALLED,
    reason="optional candidate dependency vaderSentiment==3.3.2 is not installed",
)
requires_no_vader = pytest.mark.skipif(
    VADER_INSTALLED,
    reason="requires an environment without the optional vaderSentiment dependency",
)


def _corpus_document() -> Mapping[str, object]:
    return cast(
        dict[str, Any],
        json.loads(DEFAULT_PROBE_CORPUS.read_text(encoding="utf-8")),
    )


def _request(tmp_path: Path, token: str = "chartest0001") -> CharacterizationRequest:
    return CharacterizationRequest(
        workspace=tmp_path / "runs",
        run_token=token,
        started_at=datetime(2026, 8, 5, 21, 0, tzinfo=UTC),
    )


@pytest.fixture(scope="module")
def characterization(tmp_path_factory: pytest.TempPathFactory) -> Any:
    if not VADER_INSTALLED:
        pytest.skip("vaderSentiment is not installed")
    workspace = tmp_path_factory.mktemp("characterization")
    return run_vader_characterization(
        CharacterizationRequest(
            workspace=workspace,
            run_token="chartest0001",
            started_at=datetime(2026, 8, 5, 21, 0, tzinfo=UTC),
        )
    )


# --------------------------------------------------------------------------
# Frozen probe corpus
# --------------------------------------------------------------------------


def test_probe_corpus_is_frozen_repository_authored_and_label_free() -> None:
    document = _corpus_document()
    corpus = load_behavioral_probe_corpus(document)

    assert document["status"] == "frozen"
    provenance = cast(dict[str, Any], document["provenance"])
    assert provenance["authorship"] == "repository_authored"
    assert provenance["external_dataset"] is False
    assert provenance["scraped_content"] is False
    assert provenance["network_retrieval"] is False

    ground_truth = cast(dict[str, Any], document["ground_truth"])
    assert ground_truth["human_labels_present"] is False

    # Every probe carries a design description flagged as not a label.
    for item in cast(list[dict[str, Any]], document["items"]):
        assert item["not_a_ground_truth_label"] is True
        assert item["probes"].strip()
        for banned in ("label", "gold", "ground truth", "correct answer"):
            assert banned not in item.get("probes", "").lower() or banned == "label"

    assert corpus.purpose == "research_only_behavioral_characterization"
    assert len(corpus.probes) == 24


def test_probe_corpus_ordering_and_hashes_are_deterministic() -> None:
    first = load_behavioral_probe_corpus(_corpus_document())
    second = load_behavioral_probe_corpus(_corpus_document())

    assert first.artifact_hash == second.artifact_hash
    assert first.probe_ids == second.probe_ids
    assert first.probe_ids == tuple(sorted(first.probe_ids))
    assert tuple(item.position for item in first.probes) == tuple(range(24))
    for probe in first.probes:
        assert probe.content_hash == probe_content_hash(probe.text)


def test_probe_corpus_covers_every_required_behavioral_category() -> None:
    corpus = load_behavioral_probe_corpus(_corpus_document())
    exercised = {category for probe in corpus.probes for category in probe.categories}

    for required in (
        "plainly_positive",
        "plainly_negative",
        "neutral",
        "mixed_polarity",
        "contrastive_conjunction",
        "negation",
        "degree_modifier",
        "capitalization_emphasis",
        "punctuation_emphasis",
        "emoticon_emoji",
        "informal_shortform",
        "context_dependent_risk",
    ):
        assert required in exercised, required


def test_expectations_declare_a_basis_and_never_claim_correctness() -> None:
    corpus = load_behavioral_probe_corpus(_corpus_document())
    assert corpus.expectations

    for expectation in corpus.expectations:
        assert expectation.basis in set(ProbeExpectationBasis)
        assert expectation.basis_detail.strip()
        assert expectation.statement.strip()
        lowered = expectation.statement.lower()
        for banned in (
            "truly",
            "correct",
            "accurate",
            "human judgment",
            "proves",
            "should match",
        ):
            assert banned not in lowered, expectation.expectation_id
        if expectation.kind is ProbeExpectationKind.METAMORPHIC:
            assert expectation.variant_probe_id is not None

    for raw in cast(list[dict[str, Any]], _corpus_document()["behavioral_expectations"]):
        assert raw["not_a_correctness_claim"] is True


def test_corpus_parser_rejects_labels_scraping_and_unfrozen_state() -> None:
    def _mutate(**changes: Any) -> dict[str, Any]:
        document = cast(dict[str, Any], _corpus_document())
        for path, value in changes.items():
            parts = path.split(".")
            target = document
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        return document

    with pytest.raises(BehavioralProbeCorpusError, match="frozen"):
        load_behavioral_probe_corpus(_mutate(status="draft"))
    with pytest.raises(BehavioralProbeCorpusError, match="human ground-truth"):
        load_behavioral_probe_corpus(
            _mutate(**{"ground_truth.human_labels_present": True})
        )
    with pytest.raises(BehavioralProbeCorpusError, match="scraped_content"):
        load_behavioral_probe_corpus(_mutate(**{"provenance.scraped_content": True}))
    with pytest.raises(BehavioralProbeCorpusError, match="repository authored"):
        load_behavioral_probe_corpus(_mutate(**{"provenance.authorship": "vendor"}))

    document = cast(dict[str, Any], _corpus_document())
    document["items"][0]["not_a_ground_truth_label"] = False
    with pytest.raises(BehavioralProbeCorpusError, match="not_a_ground_truth_label"):
        load_behavioral_probe_corpus(document)


def test_corpus_parser_rejects_text_that_does_not_match_its_hash() -> None:
    document = cast(dict[str, Any], _corpus_document())
    document["items"][0]["text"] = "Different text than the frozen probe."
    corpus = load_behavioral_probe_corpus(document)
    # The hash is recomputed from the exact text, so a changed probe changes the
    # corpus identity rather than silently passing under the old hash.
    assert corpus.artifact_hash != load_behavioral_probe_corpus(
        _corpus_document()
    ).artifact_hash


# --------------------------------------------------------------------------
# Candidate lifecycle and binding
# --------------------------------------------------------------------------


def test_candidate_lifecycle_is_unchanged_by_this_pr() -> None:
    snapshot = CandidateRegistrySnapshot.from_document(
        cast(dict[str, Any], json.loads(DEFAULT_REAL_REGISTRY.read_text(encoding="utf-8")))
    )
    record = snapshot.candidate(VADER_CANDIDATE_ID)
    assert record is not None
    assert record.status is CandidateDisposition.ELIGIBLE_FOR_EVALUATION
    assert record.status is not CandidateDisposition.EVALUATED
    assert record.status is not CandidateDisposition.SELECTED_FOR_DOMAIN


def test_registry_document_records_no_characterization_run() -> None:
    """The run record must stay separate from the lifecycle decision."""

    text = DEFAULT_REAL_REGISTRY.read_text(encoding="utf-8").lower()
    for banned in ("characterization", "probe corpus", "chartest"):
        assert banned not in text


@requires_vader
def test_run_binds_exact_registry_package_adapter_and_configuration(
    characterization: VerifiedCharacterizationRun,
) -> None:
    completion = characterization.completion
    binding = real_candidate_binding(
        cast(dict[str, Any], json.loads(DEFAULT_REAL_REGISTRY.read_text(encoding="utf-8"))),
        VADER_CANDIDATE_ID,
    )

    assert completion.candidate_id == VADER_CANDIDATE_ID
    assert completion.analyzer_id == VADER_ANALYZER_ID
    assert completion.package_distribution == binding.package.distribution
    assert completion.package_version == VADER_PINNED_VERSION
    assert completion.adapter_revision == VADER_ADAPTER_REVISION
    assert completion.configuration_hash == vader_configuration_hash()
    assert completion.configuration_hash == binding.configuration_hash
    assert completion.record_type == CHARACTERIZATION_RECORD_TYPE
    assert completion.characterization_version == CHARACTERIZATION_VERSION
    assert completion.candidate_lifecycle_status == "eligible_for_evaluation"


@requires_vader
def test_configuration_mismatch_fails_closed(tmp_path: Path) -> None:
    document = cast(
        dict[str, Any], json.loads(DEFAULT_REAL_REGISTRY.read_text(encoding="utf-8"))
    )
    document["candidates"][0]["configuration_hash"] = "sha256:" + ("0" * 64)
    changed = tmp_path / "changed-registry.json"
    changed.write_text(json.dumps(document), encoding="utf-8")

    request = CharacterizationRequest(
        workspace=tmp_path / "runs",
        run_token="mismatch0001",
        started_at=datetime(2026, 8, 5, 21, 0, tzinfo=UTC),
        real_registry_path=changed,
    )
    with pytest.raises(VaderCharacterizationError, match="configuration hash"):
        run_vader_characterization(request)


@requires_vader
def test_ineligible_candidate_status_fails_closed(tmp_path: Path) -> None:
    document = cast(
        dict[str, Any], json.loads(DEFAULT_REAL_REGISTRY.read_text(encoding="utf-8"))
    )
    document["candidates"][0]["status"] = "deferred"
    changed = tmp_path / "deferred-registry.json"
    changed.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(VaderCharacterizationError, match="not executable"):
        run_vader_characterization(
            CharacterizationRequest(
                workspace=tmp_path / "runs",
                run_token="deferred0001",
                started_at=datetime(2026, 8, 5, 21, 0, tzinfo=UTC),
                real_registry_path=changed,
            )
        )


# --------------------------------------------------------------------------
# Dependency states
# --------------------------------------------------------------------------


@requires_no_vader
def test_characterization_fails_closed_without_the_optional_dependency(
    tmp_path: Path,
) -> None:
    with pytest.raises(VaderDependencyError, match=r"ctrt-framework\[vader\]"):
        run_vader_characterization(_request(tmp_path))


@requires_no_vader
def test_cli_reports_the_missing_dependency_clearly(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--workspace", str(tmp_path / "runs"), "--run-token", "missingdep01"])
    assert excinfo.value.code == 2
    assert "is not installed" in capsys.readouterr().err


def test_module_never_imports_the_dependency_at_module_scope() -> None:
    source = (REPO_ROOT / "src" / "ctrt" / "vader_characterization.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    top_level = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        cast(str, node.module).split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "vaderSentiment" not in top_level


def test_no_network_or_external_dataset_dependency_in_the_research_path() -> None:
    for name in ("vader_characterization.py", "behavioral_probe_corpus.py"):
        source = (REPO_ROOT / "src" / "ctrt" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            cast(str, node.module).split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        for banned in ("requests", "urllib", "http", "socket", "ftplib"):
            assert banned not in imported, f"{name} imports {banned}"


# --------------------------------------------------------------------------
# Preserved outputs
# --------------------------------------------------------------------------


@requires_vader
def test_every_probe_preserves_identity_and_extraction_provenance(
    characterization: VerifiedCharacterizationRun,
) -> None:
    corpus = load_behavioral_probe_corpus(_corpus_document())
    assert len(characterization.observations) == len(corpus.probes)

    for observation, probe in zip(
        characterization.observations, corpus.probes, strict=True
    ):
        assert observation.probe_id == probe.probe_id
        assert observation.text == probe.text
        assert observation.content_hash == probe.content_hash
        assert observation.extraction_ref.startswith("extraction:")
        assert "content-item:" not in observation.extraction_ref
        assert observation.extraction_quality_evidence_ref == observation.extraction_ref
        assert observation.categories == probe.categories
        assert observation.probe_description == probe.probes


@requires_vader
def test_all_four_raw_outputs_are_preserved_separately(
    characterization: VerifiedCharacterizationRun,
) -> None:
    scored = [
        item
        for item in characterization.observations
        if item.result_status == ResultStatus.SUCCESS
    ]
    assert scored

    for observation in scored:
        assert set(observation.raw_output) == set(PRESERVED_OUTPUT_KEYS)
        keys = tuple(item.key for item in observation.normalized_outputs)
        assert keys == PRESERVED_OUTPUT_KEYS
        bounds = {item.key: (item.lower_bound, item.upper_bound) for item in
                  observation.normalized_outputs}
        assert bounds["neg"] == (0.0, 1.0)
        assert bounds["neu"] == (0.0, 1.0)
        assert bounds["pos"] == (0.0, 1.0)
        assert bounds["compound"] == (-1.0, 1.0)
        for item in observation.normalized_outputs:
            assert item.value == observation.raw_output[item.key]


@requires_vader
def test_evidence_remains_unavailable_with_zero_spans(
    characterization: VerifiedCharacterizationRun,
) -> None:
    for observation in characterization.observations:
        assert observation.evidence_support_status == "unavailable"
        assert observation.evidence_span_count == 0


@requires_vader
def test_calibration_and_applicability_stay_unclaimed(
    characterization: VerifiedCharacterizationRun,
) -> None:
    for observation in characterization.observations:
        assert observation.calibration_status == "unknown"
        assert observation.applicability_status != "in-domain"
        assert observation.applicability_reasons
        assert observation.preserved_uncertainties


@requires_vader
def test_no_vader_number_enters_any_confidence_field(
    characterization: VerifiedCharacterizationRun,
) -> None:
    """Preserved outputs must never appear as a confidence-bearing value."""

    for observation in characterization.observations:
        emitted = {float(value) for value in observation.raw_output.values()
                   if isinstance(value, (int, float))
                   and not isinstance(value, bool)}
        # Confidence is carried only as categorical status plus text.
        assert observation.calibration_status in {"unknown", "estimated", "validated"}
        assert isinstance(observation.applicability_status, str)
        for reason in observation.applicability_reasons:
            for value in emitted:
                assert f"{value}" not in reason
        assert not hasattr(observation, "confidence_value")
        assert not hasattr(observation, "instrument_probability")


@requires_vader
def test_unsupported_declared_language_abstains(
    characterization: VerifiedCharacterizationRun,
) -> None:
    abstained = [
        item
        for item in characterization.observations
        if item.result_status == ResultStatus.ABSTAINED
    ]
    assert len(abstained) == 1
    observation = abstained[0]

    assert observation.language == "fr"
    assert observation.abstention_triggered is True
    assert "out-of-domain" in observation.abstention_reasons
    assert observation.normalized_outputs == ()
    assert observation.evidence_span_count == 0


@requires_vader
def test_repeated_runs_produce_identical_measurements(tmp_path: Path) -> None:
    first = run_vader_characterization(_request(tmp_path, "determinism01"))
    second = run_vader_characterization(_request(tmp_path, "determinism02"))

    left = {item.probe_id: item.raw_output for item in first.observations}
    right = {item.probe_id: item.raw_output for item in second.observations}
    assert left == right

    left_outputs = {item.probe_id: item.normalized_outputs for item in first.observations}
    right_outputs = {
        item.probe_id: item.normalized_outputs for item in second.observations
    }
    assert left_outputs == right_outputs

    left_expect = {item.expectation_id: item.satisfied for item in first.expectation_outcomes}
    right_expect = {
        item.expectation_id: item.satisfied for item in second.expectation_outcomes
    }
    assert left_expect == right_expect


# --------------------------------------------------------------------------
# Expectations stay separate from results
# --------------------------------------------------------------------------


@requires_vader
def test_expectations_are_separate_artifacts_carrying_their_basis(
    characterization: VerifiedCharacterizationRun,
) -> None:
    corpus = load_behavioral_probe_corpus(_corpus_document())
    assert len(characterization.expectation_outcomes) == len(corpus.expectations)

    for outcome in characterization.expectation_outcomes:
        assert outcome.basis
        assert outcome.basis_detail.strip()
        assert "not a content verdict" in outcome.interpretation
        assert outcome.satisfied in {True, False, None}

    # No observation carries an expectation. They are stored side by side.
    for observation in characterization.observations:
        assert not hasattr(observation, "expectation_id")
        assert not hasattr(observation, "satisfied")
        assert not hasattr(observation, "expected_value")


@requires_vader
def test_documented_expectations_are_observed_on_the_frozen_corpus(
    characterization: VerifiedCharacterizationRun,
) -> None:
    outcomes = {
        item.expectation_id: item for item in characterization.expectation_outcomes
    }
    # These are narrow relations grounded in upstream-documented rules. Recording
    # them is a technical observation, not a claim that VADER is correct.
    for expectation_id in (
        "expectation-contrastive-conjunction",
        "expectation-negation",
        "expectation-degree-booster",
        "expectation-degree-dampener",
        "expectation-capitalization-emphasis",
        "expectation-punctuation-emphasis",
    ):
        assert outcomes[expectation_id].satisfied is True, expectation_id
        assert outcomes[expectation_id].observed_base is not None
        assert outcomes[expectation_id].observed_variant is not None


# --------------------------------------------------------------------------
# No aggregate scoring, no comparator
# --------------------------------------------------------------------------


@requires_vader
def test_no_aggregate_analytical_score_or_ranking_is_produced(
    characterization: VerifiedCharacterizationRun,
) -> None:
    completion = characterization.completion
    counts = completion.lifecycle_counts

    # Only lifecycle counts exist, and they are labeled as such.
    assert counts.completed + counts.abstained + counts.structurally_failed == len(
        characterization.observations
    )
    assert "not a pass rate" in counts.notes
    assert "analytical quality" in counts.notes

    for banned in (
        "overall_score",
        "mean_compound",
        "average",
        "ranking",
        "rank",
        "recommendation",
        "selected",
        "pass_rate",
        "accuracy",
    ):
        assert not hasattr(completion, banned), banned

    # The report legitimately *denies* several of these terms, so each pattern
    # below matches only an affirmative form that reports an actual value.
    report = characterization.markdown.lower()
    for banned in (
        r"overall score\s*[:=]\s*[-\d]",
        r"mean sentiment\s*[:=]\s*[-\d]",
        r"average compound\s*[:=]\s*[-\d]",
        r"pass rate\s*[:=]\s*[-\d]",
        r"\d+(\.\d+)?\s*%\s*(passed|pass)",
        r"accuracy\s*[:=]\s*[-\d]",
        r"candidate ranking\s*[:=]",
        r"we recommend",
        r"publish-ready",
        r"production-ready",
        r"\bverdict\s*[:=]\s*\w",
    ):
        assert re.search(banned, report) is None, banned

    # The denials themselves must be present.
    assert "not a pass rate" in report
    assert "no overall ctrt score" in report
    assert "no candidate ranking" in report


@requires_vader
def test_single_candidate_run_fabricates_no_comparator(
    characterization: VerifiedCharacterizationRun,
) -> None:
    completion = characterization.completion

    assert completion.analyzer_id == VADER_ANALYZER_ID
    assert not hasattr(completion, "comparison_ref")
    assert not hasattr(completion, "analyzer_ids")
    assert not hasattr(completion, "agreement_status")

    # No synthetic fixture identity appears anywhere in the run.
    report = characterization.markdown
    assert "synthetic.sentiment.first-signal" not in report
    assert "synthetic.sentiment.last-signal" not in report

    stored = b"\n".join(
        path.read_bytes()
        for path in characterization.artifact_directory.rglob("*")
        if path.is_file()
    )
    # No synthetic fixture identity and no second analyzer identity was stored.
    assert b"synthetic.sentiment." not in stored
    analyzer_ids = set(re.findall(rb'"analyzer_id":\s*"([^"]+)"', stored))
    assert analyzer_ids == {VADER_ANALYZER_ID.encode()}

    # No comparison artifact was written. (The phrase "comparison record" appears
    # in the adapter's own confidence note, which is why this checks structure.)
    assert not [
        path
        for path in characterization.artifact_directory.rglob("*")
        if path.is_file() and "comparison" in path.name
    ]
    assert b'"agreement_status"' not in stored
    assert b'"result_ids"' not in stored


@requires_vader
def test_inherited_comparison_invariants_are_not_weakened() -> None:
    """The comparison chain must still refuse a single analyzer."""

    from ctrt.contracts import ContentItem, SourceType
    from ctrt.vader_adapter import load_vader_sentiment_adapter
    from ctrt.workbench import AnalyzerRegistry, ContentAnalysisWorkbench

    adapter = load_vader_sentiment_adapter()
    registry = AnalyzerRegistry()
    registry.register(adapter)
    workbench = ContentAnalysisWorkbench(registry)
    content = ContentItem(
        content_id="single-analyzer-check",
        text="This release is good.",
        source_type=SourceType.RAW_TEXT,
        content_hash="sha256:" + ("a" * 64),
        language="en",
        extraction_ref="extraction:single-analyzer-check",
    )

    with pytest.raises(ValueError, match="at least two analyzers"):
        workbench.run_content_item(
            run_id="single",
            content=content,
            analyzer_ids=(VADER_ANALYZER_ID,),
        )


# --------------------------------------------------------------------------
# Storage verification
# --------------------------------------------------------------------------


@requires_vader
def test_read_time_tampering_fails_before_a_report_can_be_rendered(
    tmp_path: Path,
) -> None:
    run = run_vader_characterization(_request(tmp_path, "tampering0001"))
    reference = run.observations[0].source_artifact_ref
    digest = reference.artifact_hash.removeprefix("sha256:")
    blob = run.artifact_directory / "blobs" / "sha256" / digest
    assert blob.is_file()
    blob.write_bytes(b"{}")

    store = FileSystemArtifactStore(run.artifact_directory)
    with pytest.raises(ArtifactIntegrityError, match="failed SHA-256"):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)


@requires_vader
def test_completion_and_result_artifacts_are_all_stored(
    characterization: VerifiedCharacterizationRun,
) -> None:
    store = FileSystemArtifactStore(characterization.artifact_directory)
    completion = characterization.completion

    assert len(completion.result_refs) == len(characterization.observations)
    for reference in (
        characterization.completion_ref,
        completion.corpus_manifest_ref,
        completion.method_eligibility_ref,
        completion.eligibility_ref,
        *completion.result_refs,
    ):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)


@requires_vader
def test_report_contains_every_required_section(
    characterization: VerifiedCharacterizationRun,
) -> None:
    report = characterization.markdown

    for section in (
        "## 1. Run and candidate identity",
        "## 2. Corpus and provenance",
        "## 3. Per-probe observations",
        "## 4. Narrow behavioral expectations",
        "## 5. Abstentions and structural failures",
        "## 6. Immutable artifact references",
        "## 7. Interpretation boundary and non-claims",
    ):
        assert section in report, section

    assert "does not establish that the outputs are correct" in report
    assert "eligible_for_evaluation" in report
    for notice in CHARACTERIZATION_NON_CLAIMS:
        assert notice in report
    # Every probe's exact text is shown.
    for observation in characterization.observations:
        assert observation.text in report
        assert observation.result_artifact_ref.artifact_id in report


@requires_vader
def test_report_is_deterministic_for_the_same_frozen_inputs(tmp_path: Path) -> None:
    """Two runs over the same frozen corpus differ only by run identity."""

    first = run_vader_characterization(_request(tmp_path / "a", "reportdet001"))
    second = run_vader_characterization(_request(tmp_path / "b", "reportdet002"))

    # Artifact identities are run-scoped by design, so compare the parts that the
    # frozen corpus and pinned package fully determine: the measurement tables,
    # the probe text, and every expectation outcome.
    def _measurement_rows(markdown: str) -> list[str]:
        return [
            line
            for line in markdown.splitlines()
            if re.match(r"^\| `(neg|neu|pos|compound)` \|", line)
        ]

    def _expectation_lines(markdown: str) -> list[str]:
        return [
            line
            for line in markdown.splitlines()
            if line.startswith("- Observed outcome:")
            or line.startswith("- Statement:")
        ]

    assert _measurement_rows(first.markdown) == _measurement_rows(second.markdown)
    assert _measurement_rows(first.markdown)
    assert _expectation_lines(first.markdown) == _expectation_lines(second.markdown)
    assert [item.text for item in first.observations] == [
        item.text for item in second.observations
    ]


@requires_vader
def test_reusing_a_run_token_cannot_overwrite_stored_evidence(
    tmp_path: Path,
) -> None:
    """The append-only store refuses a second run into the same workspace."""

    from ctrt.artifact_store import ArtifactConflictError

    run_vader_characterization(_request(tmp_path, "appendonly001"))
    with pytest.raises(ArtifactConflictError, match="append-only"):
        run_vader_characterization(_request(tmp_path, "appendonly001"))


@requires_vader
def test_cli_writes_a_research_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "characterization.md"
    status = main(
        [
            "--workspace",
            str(tmp_path / "cli-runs"),
            "--run-token",
            "clitest00001",
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()

    assert status == 0
    assert f"Wrote characterization report to {output}" in captured.out
    assert "Artifact store:" in captured.err
    assert "Research only" in captured.err
    assert "eligible_for_evaluation" in captured.err
    report = output.read_text(encoding="utf-8")
    assert report.startswith("# VADER behavioral characterization (research only)")


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------


def test_creator_facing_modules_remain_disconnected_from_characterization() -> None:
    for name in (
        "creator_preflight.py",
        "creator_preflight_local.py",
        "creator_preflight_web.py",
        "synthetic.py",
        "workbench.py",
        "__init__.py",
        "_public_api_base.py",
    ):
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
        assert not any("characterization" in item.lower() for item in imported), name
        assert "vaderSentiment" not in source, name


def test_characterization_does_not_import_creator_facing_modules() -> None:
    source = (REPO_ROOT / "src" / "ctrt" / "vader_characterization.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = {
        cast(str, node.module)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    for banned in (
        "ctrt.creator_preflight",
        "ctrt.creator_preflight_local",
        "ctrt.creator_preflight_web",
        "ctrt.synthetic",
    ):
        assert banned not in imported, banned


def test_public_exports_remain_bounded() -> None:
    import ctrt
    import ctrt.behavioral_probe_corpus as corpus_module
    import ctrt.vader_characterization as characterization_module

    assert corpus_module.__all__ == [
        "BehavioralExpectation",
        "BehavioralProbe",
        "BehavioralProbeCorpus",
        "BehavioralProbeCorpusError",
        "ProbeExpectationBasis",
        "ProbeExpectationKind",
        "ProbeExpectationRelation",
        "load_behavioral_probe_corpus",
        "probe_categories",
        "probe_content_hash",
    ]
    assert characterization_module.__all__ == [
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
    assert not [
        name
        for name in ctrt.__all__
        if "vader" in name.lower() or "characterization" in name.lower()
    ]


def test_extracted_eligibility_helpers_preserve_the_shared_rules() -> None:
    """The single-candidate path uses the same gate as the comparison path."""

    from ctrt.candidate_eligibility import candidate_authorization_reasons

    snapshot = CandidateRegistrySnapshot.from_document(
        cast(dict[str, Any], json.loads(DEFAULT_REAL_REGISTRY.read_text(encoding="utf-8")))
    )
    record = snapshot.candidate(VADER_CANDIDATE_ID)
    assert record is not None

    assert candidate_authorization_reasons(
        record,
        analyzer_id=VADER_ANALYZER_ID,
        dimension_id="sentiment_valence",
        implementation_revision=VADER_ADAPTER_REVISION,
    ) == ()

    wrong_revision = candidate_authorization_reasons(
        record,
        analyzer_id=VADER_ANALYZER_ID,
        dimension_id="sentiment_valence",
        implementation_revision="ctrt-vader-adapter@9.9.9",
    )
    assert any("differs from the registry pin" in item for item in wrong_revision)

    wrong_analyzer = candidate_authorization_reasons(
        record,
        analyzer_id="some.other.analyzer",
        dimension_id="sentiment_valence",
        implementation_revision=VADER_ADAPTER_REVISION,
    )
    assert any("not explicitly authorized" in item for item in wrong_analyzer)
