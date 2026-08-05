"""Provider-neutral adapter admitting VADER as an evaluation candidate.

Admission authorizes evaluation. It does not establish analytical validity and
does not authorize creator-facing execution. Nothing in this module is imported
by the creator-preflight, browser, or synthetic execution paths.

The optional ``vaderSentiment`` distribution is loaded lazily so the
dependency-free synthetic path keeps working when it is not installed.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, cast

from ctrt.confidence import (
    AgreementStatus,
    AmbiguityBudget,
    AmbiguityBudgetStatus,
    Applicability,
    ApplicabilityStatus,
    Calibration,
    CalibrationStatus,
    ConfidenceVector,
    ExtractionQuality,
    ExtractionQualityStatus,
    InstrumentProbability,
    InterInstrumentAgreement,
    SystemAbstention,
)
from ctrt.contracts import (
    AnalyzerIdentity,
    ContentItem,
    ModelResult,
    NormalizedScore,
    ResultStatus,
)
from ctrt.measurement import AnalysisTarget, EvidenceSupport, EvidenceSupportStatus
from ctrt.serialization import canonical_sha256

VADER_DISTRIBUTION = "vaderSentiment"
VADER_PINNED_VERSION = "3.3.2"
VADER_MODULE = "vaderSentiment.vaderSentiment"
VADER_ENTRY_POINT = f"{VADER_MODULE}:SentimentIntensityAnalyzer.polarity_scores"

VADER_CANDIDATE_ID = "vader.sentiment"
VADER_ANALYZER_ID = "vader.sentiment.polarity"
VADER_ADAPTER_REVISION = "ctrt-vader-adapter@0.1.0"
VADER_ADAPTER_VERSION = "0.1.0"
VADER_TAXONOMY_ID = "sentiment.vader.polarity-scores"

SUPPORTED_LANGUAGES = ("en",)
MAX_CONTENT_CHARACTERS = 10_000
PRESERVED_OUTPUT_KEYS = ("neg", "neu", "pos", "compound")

#: Declared bounds for each preserved VADER output. Each is kept separately and
#: is never combined into a CTRT score.
OUTPUT_BOUNDS: Mapping[str, tuple[float, float]] = MappingProxyType(
    {
        "neg": (0.0, 1.0),
        "neu": (0.0, 1.0),
        "pos": (0.0, 1.0),
        "compound": (-1.0, 1.0),
    }
)

DECLARED_DOMAIN = (
    "English short-form, social-media-like text, per the upstream project's own "
    "stated purpose."
)
EVIDENCE_LOCALIZATION_NOTE = (
    "VADER returns document-level polarity scores only. It does not identify which "
    "passage produced any value, so no evidence span is emitted."
)
PRESERVED_UNCERTAINTIES = (
    "VADER has not been evaluated against a CTRT corpus, protocol, or human "
    "annotation set.",
    EVIDENCE_LOCALIZATION_NOTE,
    "The compound value is a lexicon-and-rule output, not a probability, a "
    "calibrated score, or a confidence value.",
    "Lexicon-and-rule scoring is known to be affected by irony, sarcasm, quotation, "
    "negation scope, and target-dependent sentiment.",
)


class VaderAdapterError(ValueError):
    """Raised when VADER cannot be admitted under its exact pinned identity."""


class VaderDependencyError(VaderAdapterError):
    """Raised when the optional vaderSentiment distribution is not installed."""


def vader_execution_configuration(package_version: str) -> Mapping[str, object]:
    """Return the complete execution configuration for one exact package version."""

    return {
        "adapter_revision": VADER_ADAPTER_REVISION,
        "distribution": VADER_DISTRIBUTION,
        "distribution_version": package_version,
        "entry_point": VADER_ENTRY_POINT,
        "evidence_localization": "unavailable",
        "max_content_characters": MAX_CONTENT_CHARACTERS,
        "network_access": False,
        "preserved_output_keys": list(PRESERVED_OUTPUT_KEYS),
        "runtime_lexicon_download": False,
        "supported_languages": list(SUPPORTED_LANGUAGES),
    }


def vader_configuration_hash(package_version: str = VADER_PINNED_VERSION) -> str:
    """Return the canonical configuration hash bound by the candidate registry."""

    return canonical_sha256(vader_execution_configuration(package_version))


def installed_vader_version() -> str:
    """Return the exact installed distribution version, or fail closed."""

    try:
        return importlib.metadata.version(VADER_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError as exc:
        raise VaderDependencyError(
            f"optional candidate dependency {VADER_DISTRIBUTION}=="
            f"{VADER_PINNED_VERSION} is not installed; install it with "
            f'`pip install "ctrt-framework[vader]"`'
        ) from exc


def _load_polarity_scorer() -> tuple[Any, str]:
    """Import the pinned distribution lazily and return its scorer and version."""

    version = installed_vader_version()
    if version != VADER_PINNED_VERSION:
        raise VaderAdapterError(
            f"{VADER_DISTRIBUTION} must be pinned to {VADER_PINNED_VERSION}, "
            f"but {version} is installed"
        )
    try:
        module = importlib.import_module(VADER_MODULE)
    except ImportError as exc:  # pragma: no cover - metadata present but import broken
        raise VaderDependencyError(
            f"{VADER_DISTRIBUTION} metadata is present but {VADER_MODULE} "
            "could not be imported"
        ) from exc
    analyzer_class = cast(Any, getattr(module, "SentimentIntensityAnalyzer", None))
    if analyzer_class is None:
        raise VaderAdapterError(
            f"{VADER_MODULE} does not expose SentimentIntensityAnalyzer"
        )
    return analyzer_class(), version


@dataclass(frozen=True, slots=True)
class VaderSentimentAdapter:
    """Measure sentiment valence with the exact pinned VADER distribution.

    The adapter preserves ``neg``, ``neu``, ``pos``, and ``compound`` separately.
    It never combines them, never relabels one as confidence, and never emits an
    evidence span, because VADER does not localize its outputs.
    """

    package_version: str
    dimension_id: str = "sentiment_valence"
    dimension_version: str = "0.1.0"
    _scorer: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.package_version != VADER_PINNED_VERSION:
            raise VaderAdapterError(
                f"adapter requires {VADER_DISTRIBUTION}=={VADER_PINNED_VERSION}, "
                f"not {self.package_version}"
            )
        if self._scorer is None:
            raise VaderAdapterError("adapter requires a loaded polarity scorer")

    @property
    def implementation_revision(self) -> str:
        """Return the immutable adapter revision, kept separate from the package."""

        return VADER_ADAPTER_REVISION

    @property
    def execution_configuration(self) -> Mapping[str, object]:
        """Return the complete configuration hashed by the frozen experiment plan."""

        return vader_execution_configuration(self.package_version)

    @property
    def identity(self) -> AnalyzerIdentity:
        """Return the complete analyzer, package, adapter, and taxonomy identity."""

        return AnalyzerIdentity(
            analyzer_id=VADER_ANALYZER_ID,
            provider="cjhutto.vaderSentiment",
            model_id="vader-lexicon-rule-based",
            model_version=self.package_version,
            adapter_version=VADER_ADAPTER_VERSION,
            taxonomy_id=VADER_TAXONOMY_ID,
            taxonomy_version=self.package_version,
        )

    def analyze(self, content: ContentItem) -> ModelResult:
        """Measure one canonical item, abstaining outside the declared domain."""

        target = AnalysisTarget.for_content_item(
            content_id=content.content_id,
            content_length=len(content.text),
            extraction_ref=content.canonical_extraction_ref,
        )
        boundary = self._domain_boundary(content)
        if boundary is not None:
            reason, detail = boundary
            return self._abstained_result(
                content=content,
                target=target,
                reason=reason,
                applicability=Applicability(
                    status=ApplicabilityStatus.OUT_OF_DOMAIN,
                    reasons=(detail,),
                    evidence_ref=f"candidate-registry:{VADER_CANDIDATE_ID}",
                ),
                raw_output={
                    "scored": False,
                    "declared_language": content.language,
                    "content_characters": len(content.text),
                },
            )

        raw = cast(Mapping[str, Any], self._scorer.polarity_scores(content.text))
        invalid = _invalid_output_reasons(raw)
        if invalid:
            return self._failed_result(
                content=content,
                target=target,
                errors=invalid,
                raw_output=dict(raw),
            )
        return ModelResult(
            result_id=f"{content.content_id}:{VADER_ANALYZER_ID}:{VADER_ADAPTER_VERSION}",
            content_id=content.content_id,
            dimension_id=self.dimension_id,
            dimension_version=self.dimension_version,
            status=ResultStatus.SUCCESS,
            analyzer=self.identity,
            analysis_target=target,
            evidence_support=EvidenceSupport(
                status=EvidenceSupportStatus.UNAVAILABLE,
                notes=EVIDENCE_LOCALIZATION_NOTE,
            ),
            confidence=self._confidence(
                target=target,
                applicability=Applicability(
                    status=ApplicabilityStatus.UNKNOWN,
                    reasons=(
                        f"Declared candidate domain: {DECLARED_DOMAIN}",
                        "No CTRT evaluation has established that this item falls "
                        "within that domain.",
                    ),
                    evidence_ref=f"candidate-registry:{VADER_CANDIDATE_ID}",
                ),
                abstention=SystemAbstention(triggered=False),
            ),
            raw_output=dict(raw),
            normalized_scores=tuple(
                NormalizedScore(
                    key=key,
                    value=float(raw[key]),
                    lower_bound=OUTPUT_BOUNDS[key][0],
                    upper_bound=OUTPUT_BOUNDS[key][1],
                )
                for key in PRESERVED_OUTPUT_KEYS
            ),
            warnings=(
                "VADER outputs are preserved separately and are not combined into a "
                "CTRT score.",
                "The compound value is not a confidence, probability, or calibrated "
                "score.",
            ),
            configuration=self.execution_configuration,
        )

    @staticmethod
    def _domain_boundary(content: ContentItem) -> tuple[str, str] | None:
        """Return an abstention reason when declared metadata leaves the domain."""

        if content.language is None:
            return (
                "out-of-domain",
                "Content declares no language. The candidate domain is declared only "
                "for English, and language is never inferred from the text.",
            )
        if content.language not in SUPPORTED_LANGUAGES:
            return (
                "out-of-domain",
                f"Content declares language {content.language!r}. The candidate "
                f"domain is declared only for {', '.join(SUPPORTED_LANGUAGES)}.",
            )
        if len(content.text) > MAX_CONTENT_CHARACTERS:
            return (
                "out-of-domain",
                f"Content is {len(content.text)} characters, beyond the deliberate "
                f"{MAX_CONTENT_CHARACTERS}-character short-form adapter limit.",
            )
        return None

    def _abstained_result(
        self,
        *,
        content: ContentItem,
        target: AnalysisTarget,
        reason: str,
        applicability: Applicability,
        raw_output: dict[str, object],
    ) -> ModelResult:
        return ModelResult(
            result_id=f"{content.content_id}:{VADER_ANALYZER_ID}:{VADER_ADAPTER_VERSION}",
            content_id=content.content_id,
            dimension_id=self.dimension_id,
            dimension_version=self.dimension_version,
            status=ResultStatus.ABSTAINED,
            analyzer=self.identity,
            analysis_target=target,
            evidence_support=EvidenceSupport(
                status=EvidenceSupportStatus.UNAVAILABLE,
                notes="No measurement was emitted, so no evidence exists.",
            ),
            confidence=self._confidence(
                target=target,
                applicability=applicability,
                abstention=SystemAbstention(triggered=True, reasons=(reason,)),
            ),
            raw_output=raw_output,
            warnings=("The adapter abstained rather than inventing a measurement.",),
            configuration=self.execution_configuration,
        )

    def _failed_result(
        self,
        *,
        content: ContentItem,
        target: AnalysisTarget,
        errors: tuple[str, ...],
        raw_output: dict[str, object],
    ) -> ModelResult:
        return ModelResult(
            result_id=f"{content.content_id}:{VADER_ANALYZER_ID}:{VADER_ADAPTER_VERSION}",
            content_id=content.content_id,
            dimension_id=self.dimension_id,
            dimension_version=self.dimension_version,
            status=ResultStatus.FAILED,
            analyzer=self.identity,
            analysis_target=target,
            evidence_support=EvidenceSupport(
                status=EvidenceSupportStatus.UNAVAILABLE,
                notes="No measurement was emitted, so no evidence exists.",
            ),
            confidence=self._confidence(
                target=target,
                applicability=Applicability(
                    status=ApplicabilityStatus.UNKNOWN,
                    reasons=("The pinned package returned an out-of-contract output.",),
                    evidence_ref=f"candidate-registry:{VADER_CANDIDATE_ID}",
                ),
                abstention=SystemAbstention(triggered=False),
            ),
            raw_output=raw_output,
            errors=errors,
            configuration=self.execution_configuration,
        )

    @staticmethod
    def _confidence(
        *,
        target: AnalysisTarget,
        applicability: Applicability,
        abstention: SystemAbstention,
    ) -> ConfidenceVector:
        return ConfidenceVector(
            instrument_probability=InstrumentProbability(
                value=None,
                source=None,
                notes=(
                    "VADER emits no probability. Its compound value is a "
                    "lexicon-and-rule output and is never mapped into instrument "
                    "probability or any scalar confidence."
                ),
            ),
            calibration=Calibration(status=CalibrationStatus.UNKNOWN),
            applicability=applicability,
            extraction_quality=ExtractionQuality(
                status=ExtractionQualityStatus.CLEAN,
                evidence_ref=target.extraction_ref,
            ),
            inter_instrument_agreement=InterInstrumentAgreement(
                status=AgreementStatus.SINGLE_INSTRUMENT,
                participants=(VADER_ANALYZER_ID,),
                notes="Agreement is recorded only in a separate comparison record.",
            ),
            system_abstention=abstention,
            ambiguity_budget=AmbiguityBudget(
                status=AmbiguityBudgetStatus.PRESERVED,
                preserved_uncertainties=PRESERVED_UNCERTAINTIES,
                notes=(
                    "Candidate admission authorizes evaluation only. It establishes "
                    "no analytical validity."
                ),
            ),
        )


def _invalid_output_reasons(raw: Mapping[str, Any]) -> tuple[str, ...]:
    """Return contract violations in the pinned package's returned mapping."""

    reasons: list[str] = []
    for key in PRESERVED_OUTPUT_KEYS:
        if key not in raw:
            reasons.append(f"pinned package omitted required output key {key!r}")
            continue
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            reasons.append(f"output {key!r} is not a real number")
            continue
        numeric = float(value)
        if not math.isfinite(numeric):
            reasons.append(f"output {key!r} is not finite")
            continue
        lower, upper = OUTPUT_BOUNDS[key]
        if not lower <= numeric <= upper:
            reasons.append(
                f"output {key!r} value {numeric!r} falls outside its declared "
                f"bounds [{lower}, {upper}]"
            )
    return tuple(reasons)


def load_vader_sentiment_adapter() -> VaderSentimentAdapter:
    """Load the pinned optional distribution and return one admitted adapter.

    Raises :class:`VaderDependencyError` when the optional dependency is absent,
    and :class:`VaderAdapterError` when the installed version is not the pin.
    """

    scorer, version = _load_polarity_scorer()
    return VaderSentimentAdapter(package_version=version, _scorer=scorer)


__all__ = [
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
