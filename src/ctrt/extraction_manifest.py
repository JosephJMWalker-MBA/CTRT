"""Immutable source, extraction, and extracted-content artifacts for CTRT."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.contracts import ContentItem, SourceType
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes


class ExtractionManifestError(ValueError):
    """Raised when extraction provenance or coordinate mapping is invalid."""


class ExtractionCorpusStatus(StrEnum):
    """Lifecycle state required for executable extraction corpora."""

    FROZEN = "frozen"


class CoordinateMappingKind(StrEnum):
    """Initial mapping vocabulary for the dependency-free extraction slice."""

    EXACT = "exact"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ExtractionManifestError(f"{field_name} must not be empty")


def _require_sha256(value: str, field_name: str) -> None:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ExtractionManifestError(f"{field_name} must use a sha256: prefix")
    digest = value[len(prefix) :]
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ExtractionManifestError(
            f"{field_name} must contain a lowercase 64-character SHA-256 digest"
        )


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExtractionManifestError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ExtractionManifestError(f"{field_name} must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExtractionManifestError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ExtractionManifestError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtractionManifestError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExtractionManifestError(f"{field_name} must be an integer")
    return value


def _text_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def source_artifact_id(source_id: str, source_hash: str) -> str:
    """Derive an immutable source artifact ID."""

    _require_non_empty(source_id, "source_id")
    _require_sha256(source_hash, "source_hash")
    return f"source-artifact:{source_id}:{source_hash.removeprefix('sha256:')}"


def extraction_artifact_id(
    *,
    content_id: str,
    source_artifact_ref: StoredArtifactRef,
    method_id: str,
    method_revision: str,
    configuration_hash: str,
    canonical_content_hash: str,
) -> str:
    """Derive extraction identity from all frozen extraction inputs."""

    _require_non_empty(content_id, "content_id")
    _require_non_empty(method_id, "method_id")
    _require_non_empty(method_revision, "method_revision")
    _require_sha256(configuration_hash, "configuration_hash")
    _require_sha256(canonical_content_hash, "canonical_content_hash")
    identity = {
        "content_id": content_id,
        "source_artifact_ref": source_artifact_ref,
        "method_id": method_id,
        "method_revision": method_revision,
        "configuration_hash": configuration_hash,
        "canonical_content_hash": canonical_content_hash,
    }
    digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return f"extraction:{content_id}:{digest}"


def extracted_content_artifact_id(
    content_id: str,
    content_hash: str,
    extraction_ref: str,
) -> str:
    """Derive content-record identity from text and extraction provenance."""

    _require_non_empty(content_id, "content_id")
    _require_sha256(content_hash, "content_hash")
    _require_non_empty(extraction_ref, "extraction_ref")
    extraction_digest = hashlib.sha256(extraction_ref.encode("utf-8")).hexdigest()
    return (
        f"extracted-content:{content_id}:"
        f"{content_hash.removeprefix('sha256:')}:{extraction_digest}"
    )


@dataclass(frozen=True, slots=True)
class SourceArtifactSnapshot:
    """Exact source text and metadata presented to an extraction method."""

    artifact_id: str
    source_id: str
    text: str
    source_hash: str
    source_type: SourceType
    source_uri: str | None
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ExtractionManifestError("source text must not be empty")
        if self.source_hash != _text_hash(self.text):
            raise ExtractionManifestError(
                "source hash must match the exact UTF-8 source text"
            )
        if self.artifact_id != source_artifact_id(
            self.source_id,
            self.source_hash,
        ):
            raise ExtractionManifestError(
                "source artifact ID must derive from source ID and source hash"
            )
        expected_hash = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected_hash:
            raise ExtractionManifestError(
                "source artifact hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> SourceArtifactSnapshot:
        """Parse and canonically identify one source artifact."""

        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            source_id=_string(document.get("source_id"), "source_id"),
            text=_string(document.get("text"), "text"),
            source_hash=_string(document.get("source_hash"), "source_hash"),
            source_type=SourceType(
                _string(document.get("source_type"), "source_type")
            ),
            source_uri=_optional_string(document.get("source_uri"), "source_uri"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> SourceArtifactSnapshot:
        """Parse an already hash-verified source artifact."""

        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtractionManifestError(
                "source artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "source artifact"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise ExtractionManifestError(
                "stored source artifact ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise ExtractionManifestError(
                "stored source artifact hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise ExtractionManifestError(
                "stored source artifact is not in canonical form"
            )
        return snapshot

    def reference(self) -> StoredArtifactRef:
        return StoredArtifactRef(
            artifact_id=self.artifact_id,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.artifact_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class ExtractedContentSnapshot:
    """Exact canonical analyzer input bound to one extraction record."""

    artifact_id: str
    content_id: str
    text: str
    content_hash: str
    language: str
    source_type: SourceType
    source_uri: str | None
    extraction_ref: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ExtractionManifestError("extracted content text must not be empty")
        if self.content_hash != _text_hash(self.text):
            raise ExtractionManifestError(
                "content hash must match exact UTF-8 canonical text"
            )
        expected_id = extracted_content_artifact_id(
            self.content_id,
            self.content_hash,
            self.extraction_ref,
        )
        if self.artifact_id != expected_id:
            raise ExtractionManifestError(
                "extracted content ID must derive from text and extraction identity"
            )
        expected_hash = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected_hash:
            raise ExtractionManifestError(
                "extracted content artifact hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ExtractedContentSnapshot:
        """Parse and canonically identify one extracted content artifact."""

        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            content_id=_string(document.get("content_id"), "content_id"),
            text=_string(document.get("text"), "text"),
            content_hash=_string(document.get("content_hash"), "content_hash"),
            language=_string(document.get("language"), "language"),
            source_type=SourceType(
                _string(document.get("source_type"), "source_type")
            ),
            source_uri=_optional_string(document.get("source_uri"), "source_uri"),
            extraction_ref=_string(
                document.get("extraction_ref"),
                "extraction_ref",
            ),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> ExtractedContentSnapshot:
        """Parse an already hash-verified extracted-content artifact."""

        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtractionManifestError(
                "extracted-content artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "extracted content"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise ExtractionManifestError(
                "stored extracted-content ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise ExtractionManifestError(
                "stored extracted-content hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise ExtractionManifestError(
                "stored extracted-content artifact is not canonical"
            )
        return snapshot

    def reference(self) -> StoredArtifactRef:
        return StoredArtifactRef(
            artifact_id=self.artifact_id,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.artifact_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )

    def to_content_item(self) -> ContentItem:
        return ContentItem(
            content_id=self.content_id,
            text=self.text,
            source_type=self.source_type,
            content_hash=self.content_hash,
            source_uri=self.source_uri,
            language=self.language,
            extraction_ref=self.extraction_ref,
        )


@dataclass(frozen=True, slots=True)
class CoordinateMapSpan:
    """One half-open source-to-canonical coordinate mapping span."""

    source_start: int
    source_end: int
    canonical_start: int
    canonical_end: int
    kind: CoordinateMappingKind

    def __post_init__(self) -> None:
        if self.source_start < 0 or self.canonical_start < 0:
            raise ExtractionManifestError("coordinate starts must be non-negative")
        if self.source_end <= self.source_start:
            raise ExtractionManifestError(
                "source_end must be greater than source_start"
            )
        if self.canonical_end <= self.canonical_start:
            raise ExtractionManifestError(
                "canonical_end must be greater than canonical_start"
            )
        if self.source_end - self.source_start != (
            self.canonical_end - self.canonical_start
        ):
            raise ExtractionManifestError(
                "exact coordinate spans must preserve length"
            )

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> CoordinateMapSpan:
        return cls(
            source_start=_integer(document.get("source_start"), "source_start"),
            source_end=_integer(document.get("source_end"), "source_end"),
            canonical_start=_integer(
                document.get("canonical_start"),
                "canonical_start",
            ),
            canonical_end=_integer(document.get("canonical_end"), "canonical_end"),
            kind=CoordinateMappingKind(_string(document.get("kind"), "kind")),
        )


@dataclass(frozen=True, slots=True)
class ExtractionManifestSnapshot:
    """Immutable extraction method, output, and coordinate mapping record."""

    artifact_id: str
    content_id: str
    source_artifact_ref: StoredArtifactRef
    method_id: str
    method_revision: str
    configuration_hash: str
    canonical_content_hash: str
    content_artifact_ref: StoredArtifactRef
    coordinate_map: tuple[CoordinateMapSpan, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _parse_timestamp(self.created_at, "created_at")
        expected_id = extraction_artifact_id(
            content_id=self.content_id,
            source_artifact_ref=self.source_artifact_ref,
            method_id=self.method_id,
            method_revision=self.method_revision,
            configuration_hash=self.configuration_hash,
            canonical_content_hash=self.canonical_content_hash,
        )
        if self.artifact_id != expected_id:
            raise ExtractionManifestError(
                "extraction ID must derive from frozen extraction inputs"
            )
        expected_content_id = extracted_content_artifact_id(
            self.content_id,
            self.canonical_content_hash,
            self.artifact_id,
        )
        if self.content_artifact_ref.artifact_id != expected_content_id:
            raise ExtractionManifestError(
                "content reference must derive from extraction identity"
            )
        if not self.coordinate_map:
            raise ExtractionManifestError(
                "extraction manifest requires coordinate mapping"
            )
        source_cursor = 0
        canonical_cursor = 0
        for span in self.coordinate_map:
            if span.source_start != source_cursor:
                raise ExtractionManifestError(
                    "source coordinate spans must be contiguous and ordered"
                )
            if span.canonical_start != canonical_cursor:
                raise ExtractionManifestError(
                    "canonical coordinate spans must be contiguous and ordered"
                )
            source_cursor = span.source_end
            canonical_cursor = span.canonical_end
        expected_hash = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected_hash:
            raise ExtractionManifestError(
                "extraction artifact hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ExtractionManifestSnapshot:
        coordinate_value = document.get("coordinate_map")
        if not isinstance(coordinate_value, list):
            raise ExtractionManifestError("coordinate_map must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            content_id=_string(document.get("content_id"), "content_id"),
            source_artifact_ref=StoredArtifactRef.from_document(
                _mapping(document.get("source_artifact_ref"), "source_artifact_ref")
            ),
            method_id=_string(document.get("method_id"), "method_id"),
            method_revision=_string(
                document.get("method_revision"),
                "method_revision",
            ),
            configuration_hash=_string(
                document.get("configuration_hash"),
                "configuration_hash",
            ),
            canonical_content_hash=_string(
                document.get("canonical_content_hash"),
                "canonical_content_hash",
            ),
            content_artifact_ref=StoredArtifactRef.from_document(
                _mapping(document.get("content_artifact_ref"), "content_artifact_ref")
            ),
            coordinate_map=tuple(
                CoordinateMapSpan.from_document(_mapping(item, "coordinate span"))
                for item in coordinate_value
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> ExtractionManifestSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtractionManifestError(
                "extraction artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "extraction artifact"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise ExtractionManifestError(
                "stored extraction ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise ExtractionManifestError(
                "stored extraction hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise ExtractionManifestError(
                "stored extraction artifact is not canonical"
            )
        return snapshot

    def reference(self) -> StoredArtifactRef:
        return StoredArtifactRef(
            artifact_id=self.artifact_id,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.artifact_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )

    def verify(
        self,
        source: SourceArtifactSnapshot,
        content: ExtractedContentSnapshot,
    ) -> None:
        """Verify the source, output, method identity, and exact coordinate map."""

        if source.reference() != self.source_artifact_ref:
            raise ExtractionManifestError(
                "source reference differs from extraction manifest"
            )
        if content.reference() != self.content_artifact_ref:
            raise ExtractionManifestError(
                "content reference differs from extraction manifest"
            )
        if content.content_id != self.content_id:
            raise ExtractionManifestError(
                "content ID differs from extraction manifest"
            )
        if content.content_hash != self.canonical_content_hash:
            raise ExtractionManifestError(
                "canonical content hash differs from extraction manifest"
            )
        if content.extraction_ref != self.artifact_id:
            raise ExtractionManifestError(
                "canonical content does not reference extraction manifest"
            )
        if source.source_type is not content.source_type:
            raise ExtractionManifestError(
                "source type differs between source and canonical content"
            )
        if source.source_uri != content.source_uri:
            raise ExtractionManifestError(
                "source URI differs between source and canonical content"
            )
        source_cursor = 0
        canonical_cursor = 0
        for span in self.coordinate_map:
            source_slice = source.text[span.source_start : span.source_end]
            canonical_slice = content.text[
                span.canonical_start : span.canonical_end
            ]
            if source_slice != canonical_slice:
                raise ExtractionManifestError(
                    "exact coordinate span maps non-identical text"
                )
            source_cursor = span.source_end
            canonical_cursor = span.canonical_end
        if source_cursor != len(source.text):
            raise ExtractionManifestError(
                "coordinate map does not cover complete source text"
            )
        if canonical_cursor != len(content.text):
            raise ExtractionManifestError(
                "coordinate map does not cover complete canonical text"
            )


@dataclass(frozen=True, slots=True)
class ExtractionCorpusEntry:
    """One ordered source-extraction-content graph in a frozen corpus."""

    position: int
    content_id: str
    content_hash: str
    language: str
    source_type: SourceType
    source_uri: str | None
    source_artifact_ref: StoredArtifactRef
    extraction_artifact_ref: StoredArtifactRef
    content_artifact_ref: StoredArtifactRef

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ExtractionManifestError("entry position must be non-negative")
        _require_sha256(self.content_hash, "content_hash")
        expected_prefix = f"extraction:{self.content_id}:"
        if not self.extraction_artifact_ref.artifact_id.startswith(expected_prefix):
            raise ExtractionManifestError(
                "extraction artifact reference must identify content_id"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ExtractionCorpusEntry:
        return cls(
            position=_integer(document.get("position"), "position"),
            content_id=_string(document.get("content_id"), "content_id"),
            content_hash=_string(document.get("content_hash"), "content_hash"),
            language=_string(document.get("language"), "language"),
            source_type=SourceType(
                _string(document.get("source_type"), "source_type")
            ),
            source_uri=_optional_string(document.get("source_uri"), "source_uri"),
            source_artifact_ref=StoredArtifactRef.from_document(
                _mapping(document.get("source_artifact_ref"), "source_artifact_ref")
            ),
            extraction_artifact_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("extraction_artifact_ref"),
                    "extraction_artifact_ref",
                )
            ),
            content_artifact_ref=StoredArtifactRef.from_document(
                _mapping(document.get("content_artifact_ref"), "content_artifact_ref")
            ),
        )

    def verify(
        self,
        source: SourceArtifactSnapshot,
        extraction: ExtractionManifestSnapshot,
        content: ExtractedContentSnapshot,
    ) -> None:
        if source.reference() != self.source_artifact_ref:
            raise ExtractionManifestError(
                f"content {self.content_id!r} source reference differs"
            )
        if extraction.reference() != self.extraction_artifact_ref:
            raise ExtractionManifestError(
                f"content {self.content_id!r} extraction reference differs"
            )
        if content.reference() != self.content_artifact_ref:
            raise ExtractionManifestError(
                f"content {self.content_id!r} content reference differs"
            )
        observed = (
            content.content_id,
            content.content_hash,
            content.language,
            content.source_type,
            content.source_uri,
        )
        expected = (
            self.content_id,
            self.content_hash,
            self.language,
            self.source_type,
            self.source_uri,
        )
        if observed != expected:
            raise ExtractionManifestError(
                f"content {self.content_id!r} metadata differs from corpus"
            )
        extraction.verify(source, content)


@dataclass(frozen=True, slots=True)
class ExtractionCorpusManifestSnapshot:
    """Frozen ordered extraction corpus plus canonical artifact identity."""

    corpus_id: str
    corpus_version: str
    status: ExtractionCorpusStatus
    contents: tuple[ExtractionCorpusEntry, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _parse_timestamp(self.created_at, "created_at")
        if not self.contents:
            raise ExtractionManifestError(
                "extraction corpus requires at least one content entry"
            )
        positions = tuple(item.position for item in self.contents)
        if positions != tuple(range(len(self.contents))):
            raise ExtractionManifestError(
                "extraction corpus positions must be contiguous and ordered"
            )
        if len(self.content_ids) != len(set(self.content_ids)):
            raise ExtractionManifestError(
                "extraction corpus content IDs must be unique"
            )
        expected_hash = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected_hash:
            raise ExtractionManifestError(
                "extraction corpus hash must match canonical payload"
            )

    @property
    def content_ids(self) -> tuple[str, ...]:
        return tuple(item.content_id for item in self.contents)

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ExtractionCorpusManifestSnapshot:
        contents_value = document.get("contents")
        if not isinstance(contents_value, list):
            raise ExtractionManifestError("contents must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            corpus_id=_string(document.get("corpus_id"), "corpus_id"),
            corpus_version=_string(
                document.get("corpus_version"),
                "corpus_version",
            ),
            status=ExtractionCorpusStatus(
                _string(document.get("status"), "status")
            ),
            contents=tuple(
                ExtractionCorpusEntry.from_document(
                    _mapping(item, "extraction corpus entry")
                )
                for item in contents_value
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def reference(self) -> VersionedArtifactRef:
        return VersionedArtifactRef(
            artifact_id=self.corpus_id,
            artifact_version=self.corpus_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.corpus_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class StoredExtractedCorpus:
    """Verified source, extraction, and content graph reconstructed from storage."""

    manifest_ref: StoredArtifactRef
    source_refs: tuple[StoredArtifactRef, ...]
    extraction_refs: tuple[StoredArtifactRef, ...]
    content_refs: tuple[StoredArtifactRef, ...]
    contents: tuple[ContentItem, ...]

    def __post_init__(self) -> None:
        count = len(self.contents)
        if count == 0 or not (
            len(self.source_refs)
            == len(self.extraction_refs)
            == len(self.content_refs)
            == count
        ):
            raise ValueError(
                "stored extraction corpus requires one complete graph per content"
            )


def _load(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> CanonicalArtifact:
    return store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )


def load_extracted_corpus(
    store: FileSystemArtifactStore,
    manifest: ExtractionCorpusManifestSnapshot,
) -> StoredExtractedCorpus:
    """Reconstruct exact analyzer inputs from the stored extraction graph."""

    stored_manifest = _load(
        store,
        StoredArtifactRef(
            artifact_id=manifest.corpus_id,
            artifact_hash=manifest.artifact_hash,
        ),
    )
    if stored_manifest.payload != manifest.canonical_payload:
        raise ArtifactIntegrityError(
            "stored extraction corpus differs from expected manifest"
        )
    sources: list[SourceArtifactSnapshot] = []
    extractions: list[ExtractionManifestSnapshot] = []
    contents: list[ExtractedContentSnapshot] = []
    for entry in manifest.contents:
        source = SourceArtifactSnapshot.from_artifact(
            _load(store, entry.source_artifact_ref)
        )
        content = ExtractedContentSnapshot.from_artifact(
            _load(store, entry.content_artifact_ref)
        )
        extraction = ExtractionManifestSnapshot.from_artifact(
            _load(store, entry.extraction_artifact_ref)
        )
        entry.verify(source, extraction, content)
        sources.append(source)
        extractions.append(extraction)
        contents.append(content)
    return StoredExtractedCorpus(
        manifest_ref=store.reference(manifest.corpus_id),
        source_refs=tuple(item.reference() for item in sources),
        extraction_refs=tuple(item.reference() for item in extractions),
        content_refs=tuple(item.reference() for item in contents),
        contents=tuple(item.to_content_item() for item in contents),
    )


def persist_extracted_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    manifest: ExtractionCorpusManifestSnapshot,
    sources: tuple[SourceArtifactSnapshot, ...],
    extractions: tuple[ExtractionManifestSnapshot, ...],
    contents: tuple[ExtractedContentSnapshot, ...],
) -> StoredExtractedCorpus:
    """Persist source and output graphs first, then publish the corpus last."""

    if plan.corpus_ref != manifest.reference():
        raise ExtractionManifestError(
            "experiment plan corpus_ref differs from extraction corpus"
        )
    if plan.content_ids != manifest.content_ids:
        raise ExtractionManifestError(
            "experiment plan content order differs from extraction corpus"
        )
    if not (
        len(sources)
        == len(extractions)
        == len(contents)
        == len(manifest.contents)
    ):
        raise ExtractionManifestError(
            "source, extraction, content, and corpus populations must match"
        )
    for entry, source, extraction, content in zip(
        manifest.contents,
        sources,
        extractions,
        contents,
        strict=True,
    ):
        entry.verify(source, extraction, content)
        if store.append(source.artifact()) != source.reference():
            raise ArtifactIntegrityError("stored source reference differs")
        if store.append(content.artifact()) != content.reference():
            raise ArtifactIntegrityError("stored content reference differs")
        if store.append(extraction.artifact()) != extraction.reference():
            raise ArtifactIntegrityError("stored extraction reference differs")
    stored_manifest = store.append(manifest.artifact())
    if stored_manifest.artifact_hash != manifest.artifact_hash:
        raise ArtifactIntegrityError("stored extraction corpus reference differs")
    return load_extracted_corpus(store, manifest)
