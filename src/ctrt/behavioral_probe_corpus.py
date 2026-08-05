"""Frozen repository-authored behavioral probe corpus for research characterization.

A probe describes what an item is designed to exercise. It is never a
human-annotated correct answer, and this module refuses to parse a corpus that
claims otherwise.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from ctrt.serialization import canonical_json_bytes


class ProbeExpectationKind(StrEnum):
    """Whether an expectation relates two probes or describes one probe."""

    METAMORPHIC = "metamorphic"
    IMPLEMENTATION = "implementation"


class ProbeExpectationRelation(StrEnum):
    """The narrow directional relation an expectation asserts."""

    VARIANT_LESS_THAN_BASE = "variant_less_than_base"
    VARIANT_NOT_GREATER_THAN_BASE = "variant_not_greater_than_base"
    VARIANT_NOT_LESS_THAN_BASE = "variant_not_less_than_base"
    NONZERO = "nonzero"


class ProbeExpectationBasis(StrEnum):
    """Where an expectation's authority comes from."""

    UPSTREAM_DOCUMENTED_RULE = "upstream_documented_rule"
    SHIPPED_LEXICON_CONTENTS = "shipped_lexicon_contents"
    REPOSITORY_AUTHORED_DESIGN = "repository_authored_design"


class BehavioralProbeCorpusError(ValueError):
    """Raised when a probe corpus is not frozen, authored, or label-free."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BehavioralProbeCorpusError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise BehavioralProbeCorpusError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BehavioralProbeCorpusError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise BehavioralProbeCorpusError(f"{field_name} must be a boolean")
    return value


def _int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BehavioralProbeCorpusError(f"{field_name} must be an integer")
    return value


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise BehavioralProbeCorpusError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise BehavioralProbeCorpusError(f"{field_name} must not contain duplicates")
    return result


def probe_content_hash(text: str) -> str:
    """Return the canonical hash of the exact UTF-8 probe bytes."""

    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class BehavioralProbe:
    """One exact repository-authored probe item."""

    position: int
    probe_id: str
    text: str
    content_hash: str
    language: str
    categories: tuple[str, ...]
    probes: str

    def __post_init__(self) -> None:
        if self.position < 0:
            raise BehavioralProbeCorpusError("probe position must be non-negative")
        if not self.text.strip():
            raise BehavioralProbeCorpusError("probe text must not be empty")
        if not self.categories:
            raise BehavioralProbeCorpusError("probe requires at least one category")
        if self.content_hash != probe_content_hash(self.text):
            raise BehavioralProbeCorpusError(
                f"probe {self.probe_id} content hash does not match its exact text"
            )


@dataclass(frozen=True, slots=True)
class BehavioralExpectation:
    """One narrow expectation with a declared basis, separate from any result."""

    expectation_id: str
    kind: ProbeExpectationKind
    base_probe_id: str
    variant_probe_id: str | None
    output_key: str
    relation: ProbeExpectationRelation
    basis: ProbeExpectationBasis
    basis_detail: str
    statement: str

    def __post_init__(self) -> None:
        if not self.basis_detail.strip() or not self.statement.strip():
            raise BehavioralProbeCorpusError(
                "expectation requires a basis detail and a statement"
            )
        if self.kind is ProbeExpectationKind.METAMORPHIC:
            if self.variant_probe_id is None:
                raise BehavioralProbeCorpusError(
                    "a metamorphic expectation requires a variant probe"
                )
            if self.variant_probe_id == self.base_probe_id:
                raise BehavioralProbeCorpusError(
                    "a metamorphic expectation requires two distinct probes"
                )
            if self.relation is ProbeExpectationRelation.NONZERO:
                raise BehavioralProbeCorpusError(
                    "a metamorphic expectation requires a comparative relation"
                )
            return
        if self.variant_probe_id is not None:
            raise BehavioralProbeCorpusError(
                "an implementation expectation may not name a variant probe"
            )
        if self.relation is not ProbeExpectationRelation.NONZERO:
            raise BehavioralProbeCorpusError(
                "an implementation expectation requires a single-probe relation"
            )

    def evaluate(self, values: Mapping[str, float]) -> bool:
        """Return whether observed outputs satisfy this exact narrow relation."""

        base = values[self.base_probe_id]
        if self.relation is ProbeExpectationRelation.NONZERO:
            return base != 0.0
        if self.variant_probe_id is None:  # pragma: no cover - blocked by __post_init__
            raise BehavioralProbeCorpusError("comparative relation requires a variant")
        variant = values[self.variant_probe_id]
        if self.relation is ProbeExpectationRelation.VARIANT_LESS_THAN_BASE:
            return variant < base
        if self.relation is ProbeExpectationRelation.VARIANT_NOT_GREATER_THAN_BASE:
            return variant <= base
        return variant >= base


@dataclass(frozen=True, slots=True)
class BehavioralProbeCorpus:
    """A frozen, repository-authored, label-free probe corpus."""

    corpus_id: str
    corpus_version: str
    purpose: str
    probes: tuple[BehavioralProbe, ...]
    expectations: tuple[BehavioralExpectation, ...]
    categories: tuple[str, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.probes:
            raise BehavioralProbeCorpusError("probe corpus must not be empty")
        positions = tuple(item.position for item in self.probes)
        if positions != tuple(range(len(self.probes))):
            raise BehavioralProbeCorpusError(
                "probe positions must be contiguous, ordered, and zero-based"
            )
        probe_ids = tuple(item.probe_id for item in self.probes)
        if len(probe_ids) != len(set(probe_ids)):
            raise BehavioralProbeCorpusError("probe IDs must be unique")
        expectation_ids = tuple(item.expectation_id for item in self.expectations)
        if len(expectation_ids) != len(set(expectation_ids)):
            raise BehavioralProbeCorpusError("expectation IDs must be unique")
        known = set(probe_ids)
        for expectation in self.expectations:
            referenced = {expectation.base_probe_id, expectation.variant_probe_id} - {None}
            missing = referenced - known
            if missing:
                raise BehavioralProbeCorpusError(
                    f"expectation {expectation.expectation_id} references unknown probes: "
                    + ", ".join(sorted(str(item) for item in missing))
                )
        declared = set(self.categories)
        for probe in self.probes:
            undeclared = set(probe.categories) - declared
            if undeclared:
                raise BehavioralProbeCorpusError(
                    f"probe {probe.probe_id} uses undeclared categories: "
                    + ", ".join(sorted(undeclared))
                )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise BehavioralProbeCorpusError(
                "probe corpus artifact hash must match its canonical payload"
            )

    def probe(self, probe_id: str) -> BehavioralProbe:
        """Return one probe by stable ID."""

        for item in self.probes:
            if item.probe_id == probe_id:
                return item
        raise BehavioralProbeCorpusError(f"probe {probe_id!r} is absent from the corpus")

    def expectations_for(self, probe_id: str) -> tuple[BehavioralExpectation, ...]:
        """Return expectations naming this probe as base or variant."""

        return tuple(
            item
            for item in self.expectations
            if probe_id in {item.base_probe_id, item.variant_probe_id}
        )

    @property
    def probe_ids(self) -> tuple[str, ...]:
        """Return probe identities in exact frozen order."""

        return tuple(item.probe_id for item in self.probes)

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> BehavioralProbeCorpus:
        """Parse and canonically identify a frozen probe-corpus document."""

        if _string(document.get("status"), "status") != "frozen":
            raise BehavioralProbeCorpusError("probe corpus must be frozen")

        provenance = _mapping(document.get("provenance"), "provenance")
        if _string(provenance.get("authorship"), "provenance.authorship") != (
            "repository_authored"
        ):
            raise BehavioralProbeCorpusError(
                "probe corpus must be repository authored"
            )
        for flag in ("external_dataset", "scraped_content", "network_retrieval"):
            if _bool(provenance.get(flag), f"provenance.{flag}"):
                raise BehavioralProbeCorpusError(
                    f"probe corpus must not declare provenance.{flag}"
                )

        ground_truth = _mapping(document.get("ground_truth"), "ground_truth")
        if _bool(ground_truth.get("human_labels_present"), "human_labels_present"):
            raise BehavioralProbeCorpusError(
                "probe corpus must not contain human ground-truth labels"
            )

        items = document.get("items")
        if not isinstance(items, list):
            raise BehavioralProbeCorpusError("items must be an array")
        probes = tuple(_probe_from_document(_mapping(item, "item")) for item in items)

        raw_expectations = document.get("behavioral_expectations", [])
        if not isinstance(raw_expectations, list):
            raise BehavioralProbeCorpusError("behavioral_expectations must be an array")
        expectations = tuple(
            _expectation_from_document(_mapping(item, "expectation"))
            for item in raw_expectations
        )

        payload = canonical_json_bytes(document)
        return cls(
            corpus_id=_string(document.get("corpus_id"), "corpus_id"),
            corpus_version=_string(document.get("corpus_version"), "corpus_version"),
            purpose=_string(document.get("purpose"), "purpose"),
            probes=probes,
            expectations=expectations,
            categories=_strings(document.get("categories"), "categories"),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )


def _probe_from_document(document: Mapping[str, object]) -> BehavioralProbe:
    if not _bool(
        document.get("not_a_ground_truth_label"),
        "item.not_a_ground_truth_label",
    ):
        raise BehavioralProbeCorpusError(
            "every probe must declare not_a_ground_truth_label as true"
        )
    text = _string(document.get("text"), "item.text")
    return BehavioralProbe(
        position=_int(document.get("position"), "item.position"),
        probe_id=_string(document.get("probe_id"), "item.probe_id"),
        text=text,
        content_hash=probe_content_hash(text),
        language=_string(document.get("language"), "item.language"),
        categories=_strings(document.get("categories"), "item.categories"),
        probes=_string(document.get("probes"), "item.probes"),
    )


def _expectation_from_document(
    document: Mapping[str, object],
) -> BehavioralExpectation:
    if not _bool(
        document.get("not_a_correctness_claim"),
        "expectation.not_a_correctness_claim",
    ):
        raise BehavioralProbeCorpusError(
            "every expectation must declare not_a_correctness_claim as true"
        )
    return BehavioralExpectation(
        expectation_id=_string(
            document.get("expectation_id"), "expectation.expectation_id"
        ),
        kind=ProbeExpectationKind(_string(document.get("kind"), "expectation.kind")),
        base_probe_id=_string(
            document.get("base_probe_id"), "expectation.base_probe_id"
        ),
        variant_probe_id=_optional_string(
            document.get("variant_probe_id"), "expectation.variant_probe_id"
        ),
        output_key=_string(document.get("output_key"), "expectation.output_key"),
        relation=ProbeExpectationRelation(
            _string(document.get("relation"), "expectation.relation")
        ),
        basis=ProbeExpectationBasis(
            _string(document.get("basis"), "expectation.basis")
        ),
        basis_detail=_string(
            document.get("basis_detail"), "expectation.basis_detail"
        ),
        statement=_string(document.get("statement"), "expectation.statement"),
    )


def load_behavioral_probe_corpus(
    document: Mapping[str, object],
) -> BehavioralProbeCorpus:
    """Parse one frozen probe-corpus document."""

    return BehavioralProbeCorpus.from_document(document)


def probe_categories(probes: Sequence[BehavioralProbe]) -> tuple[str, ...]:
    """Return every category exercised by these probes, in first-seen order."""

    seen: dict[str, None] = {}
    for probe in probes:
        for category in probe.categories:
            seen.setdefault(category, None)
    return tuple(seen)


__all__ = [
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
