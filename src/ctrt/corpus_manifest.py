"""Frozen corpus manifests and exact runtime content binding for CTRT."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.artifact_store import StoredArtifactRef
from ctrt.contracts import ContentItem, SourceType
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes


class CorpusManifestStatus(StrEnum):
    """Lifecycle state required for an executable corpus manifest."""

    FROZEN = "frozen"


class CorpusBindingError(ValueError):
    """Raised when runtime content differs from the frozen corpus manifest."""


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_sha256(value: str, field_name: str) -> None:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError(f"{field_name} must use a sha256: prefix")
    digest = value[len(prefix) :]
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(
            f"{field_name} must contain a lowercase 64-character SHA-256 digest"
        )


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def canonical_content_hash(text: str) -> str:
    """Hash the exact UTF-8 canonical text bytes presented to analyzers."""

    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def canonical_content_artifact_id(content_id: str, content_hash: str) -> str:
    """Derive an immutable artifact ID from content identity and exact text hash."""

    _require_non_empty(content_id, "content_id")
    _require_sha256(content_hash, "content_hash")
    return f"canonical-content:{content_id}:{content_hash.removeprefix('sha256:')}"


@dataclass(frozen=True, slots=True)
class CorpusContentEntry:
    """One ordered content identity frozen into a corpus manifest."""

    position: int
    content_id: str
    content_hash: str
    language: str
    source_type: SourceType
    extraction_ref: str
    source_uri: str | None = None
    content_artifact_ref: StoredArtifactRef | None = None

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("corpus content position must be non-negative")
        _require_non_empty(self.content_id, "content_id")
        _require_sha256(self.content_hash, "content_hash")
        _require_non_empty(self.language, "language")
        _require_non_empty(self.extraction_ref, "extraction_ref")
        if self.source_uri is not None:
            _require_non_empty(self.source_uri, "source_uri")
        if self.content_artifact_ref is not None:
            expected_id = canonical_content_artifact_id(
                self.content_id,
                self.content_hash,
            )
            if self.content_artifact_ref.artifact_id != expected_id:
                raise ValueError(
                    "content artifact reference ID must derive from content ID and hash"
                )

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> CorpusContentEntry:
        """Parse one canonical corpus content record."""

        reference_value = document.get("content_artifact_ref")
        reference = (
            None
            if reference_value is None
            else StoredArtifactRef.from_document(
                _mapping(reference_value, "content_artifact_ref")
            )
        )
        return cls(
            position=_integer(document.get("position"), "position"),
            content_id=_string(document.get("content_id"), "content_id"),
            content_hash=_string(document.get("content_hash"), "content_hash"),
            language=_string(document.get("language"), "language"),
            source_type=SourceType(
                _string(document.get("source_type"), "source_type")
            ),
            extraction_ref=_string(
                document.get("extraction_ref"),
                "extraction_ref",
            ),
            source_uri=_optional_string(document.get("source_uri"), "source_uri"),
            content_artifact_ref=reference,
        )


@dataclass(frozen=True, slots=True)
class CorpusManifestSnapshot:
    """Parsed frozen corpus manifest plus its canonical artifact identity."""

    corpus_id: str
    corpus_version: str
    status: CorpusManifestStatus
    contents: tuple[CorpusContentEntry, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.corpus_id, "corpus_id")
        _require_non_empty(self.corpus_version, "corpus_version")
        _parse_timestamp(self.created_at, "created_at")
        if self.status is not CorpusManifestStatus.FROZEN:
            raise ValueError("executable corpus manifest must be frozen")
        if not self.contents:
            raise ValueError("corpus manifest requires at least one content entry")
        positions = tuple(item.position for item in self.contents)
        if positions != tuple(range(len(self.contents))):
            raise ValueError("corpus content positions must be contiguous and ordered")
        content_ids = self.content_ids
        if len(content_ids) != len(set(content_ids)):
            raise ValueError("corpus content IDs must be unique")
        linked = tuple(item.content_artifact_ref is not None for item in self.contents)
        if any(linked) and not all(linked):
            raise ValueError(
                "corpus manifest may not mix linked and unlinked content entries"
            )
        expected_hash = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected_hash:
            raise ValueError("corpus artifact_hash must match canonical payload")

    @property
    def content_ids(self) -> tuple[str, ...]:
        """Return the manifest's exact ordered content population."""

        return tuple(item.content_id for item in self.contents)

    @property
    def has_content_artifacts(self) -> bool:
        """Return whether every entry links an immutable canonical content artifact."""

        return all(item.content_artifact_ref is not None for item in self.contents)

    @property
    def content_artifact_refs(self) -> tuple[StoredArtifactRef, ...]:
        """Return ordered content references or fail for an unlinked legacy manifest."""

        if not self.has_content_artifacts:
            raise ValueError("corpus manifest does not link canonical content artifacts")
        return tuple(
            item.content_artifact_ref
            for item in self.contents
            if item.content_artifact_ref is not None
        )

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> CorpusManifestSnapshot:
        """Parse and canonically identify a complete corpus manifest document."""

        contents_value = document.get("contents")
        if not isinstance(contents_value, list):
            raise ValueError("contents must be an array")
        contents = tuple(
            CorpusContentEntry.from_document(_mapping(item, "content entry"))
            for item in contents_value
        )
        payload = canonical_json_bytes(document)
        return cls(
            corpus_id=_string(document.get("corpus_id"), "corpus_id"),
            corpus_version=_string(
                document.get("corpus_version"),
                "corpus_version",
            ),
            status=CorpusManifestStatus(
                _string(document.get("status"), "status")
            ),
            contents=contents,
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def reference(self) -> VersionedArtifactRef:
        """Return the exact corpus reference required by a frozen plan."""

        return VersionedArtifactRef(
            artifact_id=self.corpus_id,
            artifact_version=self.corpus_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        """Return the canonical manifest artifact for append-only persistence."""

        return CanonicalArtifact(
            artifact_id=self.corpus_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


def validate_corpus_binding(
    plan: ExperimentPlan,
    manifest: CorpusManifestSnapshot,
    contents: tuple[ContentItem, ...],
) -> None:
    """Fail unless runtime content exactly matches the frozen corpus manifest."""

    if plan.corpus_ref != manifest.reference():
        raise CorpusBindingError(
            "experiment plan corpus_ref does not match the canonical corpus manifest"
        )
    if plan.content_ids != manifest.content_ids:
        raise CorpusBindingError(
            "experiment plan content_ids do not match the frozen corpus order"
        )
    runtime_ids = tuple(item.content_id for item in contents)
    if runtime_ids != manifest.content_ids:
        raise CorpusBindingError(
            "runtime content must match the frozen corpus IDs exactly and in order"
        )
    if len(runtime_ids) != len(set(runtime_ids)):
        raise CorpusBindingError("runtime content IDs must be unique")

    for entry, content in zip(manifest.contents, contents, strict=True):
        actual_hash = canonical_content_hash(content.text)
        if content.content_hash != actual_hash:
            raise CorpusBindingError(
                f"content {content.content_id!r} hash does not match its UTF-8 text"
            )
        if content.content_hash != entry.content_hash:
            raise CorpusBindingError(
                f"content {content.content_id!r} hash differs from the corpus manifest"
            )
        if content.language is None or content.language != entry.language:
            raise CorpusBindingError(
                f"content {content.content_id!r} language differs from the corpus manifest"
            )
        if content.source_type is not entry.source_type:
            raise CorpusBindingError(
                f"content {content.content_id!r} source type differs from the corpus manifest"
            )
        if content.source_uri != entry.source_uri:
            raise CorpusBindingError(
                f"content {content.content_id!r} source URI differs from the corpus manifest"
            )
        if content.canonical_extraction_ref != entry.extraction_ref:
            raise CorpusBindingError(
                f"content {content.content_id!r} extraction identity differs "
                "from the corpus manifest"
            )
