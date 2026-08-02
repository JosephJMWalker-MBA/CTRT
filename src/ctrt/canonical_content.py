"""Immutable canonical content artifacts and storage-backed corpus reconstruction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.contracts import ContentItem, SourceType
from ctrt.corpus_manifest import (
    CorpusContentEntry,
    CorpusManifestSnapshot,
    canonical_content_artifact_id,
    canonical_content_hash,
    validate_corpus_binding,
)
from ctrt.experiments import ExperimentPlan
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes


class CanonicalContentError(ValueError):
    """Raised when canonical content bytes or metadata fail verification."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CanonicalContentError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise CanonicalContentError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CanonicalContentError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


@dataclass(frozen=True, slots=True)
class CanonicalContentSnapshot:
    """Exact text and metadata required to reconstruct one analyzer input."""

    artifact_id: str
    content_id: str
    text: str
    content_hash: str
    language: str
    source_type: SourceType
    extraction_ref: str
    source_uri: str | None
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise CanonicalContentError("canonical content text must not be empty")
        expected_content_hash = canonical_content_hash(self.text)
        if self.content_hash != expected_content_hash:
            raise CanonicalContentError(
                "canonical content hash must match the exact UTF-8 text bytes"
            )
        expected_artifact_id = canonical_content_artifact_id(
            self.content_id,
            self.content_hash,
        )
        if self.artifact_id != expected_artifact_id:
            raise CanonicalContentError(
                "canonical content artifact ID must derive from content ID and text hash"
            )
        expected_extraction_ref = f"content-item:{self.content_id}"
        if self.extraction_ref != expected_extraction_ref:
            raise CanonicalContentError(
                "canonical content currently requires content-item extraction identity"
            )
        expected_artifact_hash = (
            f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        )
        if self.artifact_hash != expected_artifact_hash:
            raise CanonicalContentError(
                "canonical content artifact hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CanonicalContentSnapshot:
        """Parse and canonically identify one content artifact document."""

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
            extraction_ref=_string(
                document.get("extraction_ref"),
                "extraction_ref",
            ),
            source_uri=_optional_string(document.get("source_uri"), "source_uri"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_content_item(cls, content: ContentItem) -> CanonicalContentSnapshot:
        """Create a canonical artifact snapshot from a verified content item."""

        if content.language is None or not content.language.strip():
            raise CanonicalContentError(
                "canonical content artifacts require an explicit language"
            )
        document: dict[str, object] = {
            "artifact_id": canonical_content_artifact_id(
                content.content_id,
                content.content_hash,
            ),
            "content_id": content.content_id,
            "text": content.text,
            "content_hash": content.content_hash,
            "language": content.language,
            "source_type": content.source_type.value,
            "source_uri": content.source_uri,
            "extraction_ref": content.canonical_extraction_ref,
        }
        return cls.from_document(document)

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> CanonicalContentSnapshot:
        """Parse an already hash-verified stored canonical artifact."""

        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CanonicalContentError(
                "canonical content artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "canonical content artifact"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise CanonicalContentError(
                "stored canonical content artifact ID differs from its payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise CanonicalContentError(
                "stored canonical content artifact hash differs from its payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise CanonicalContentError(
                "stored canonical content artifact is not in canonical form"
            )
        return snapshot

    def reference(self) -> StoredArtifactRef:
        """Return the exact immutable reference declared by the corpus manifest."""

        return StoredArtifactRef(
            artifact_id=self.artifact_id,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        """Return canonical JSON bytes ready for append-only persistence."""

        return CanonicalArtifact(
            artifact_id=self.artifact_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )

    def to_content_item(self) -> ContentItem:
        """Reconstruct the exact provider-neutral analyzer input."""

        return ContentItem(
            content_id=self.content_id,
            text=self.text,
            source_type=self.source_type,
            content_hash=self.content_hash,
            source_uri=self.source_uri,
            language=self.language,
            extraction_ref=self.extraction_ref,
        )

    def verify_entry(self, entry: CorpusContentEntry) -> None:
        """Fail unless this artifact exactly realizes one frozen manifest entry."""

        if entry.content_artifact_ref is None:
            raise CanonicalContentError(
                "corpus entry does not link a canonical content artifact"
            )
        if self.reference() != entry.content_artifact_ref:
            raise CanonicalContentError(
                f"content {entry.content_id!r} artifact reference differs from manifest"
            )
        expected = (
            entry.content_id,
            entry.content_hash,
            entry.language,
            entry.source_type,
            entry.extraction_ref,
            entry.source_uri,
        )
        observed = (
            self.content_id,
            self.content_hash,
            self.language,
            self.source_type,
            self.extraction_ref,
            self.source_uri,
        )
        if observed != expected:
            raise CanonicalContentError(
                f"content {entry.content_id!r} artifact metadata differs from manifest"
            )


@dataclass(frozen=True, slots=True)
class StoredCanonicalCorpus:
    """Verified stored corpus manifest plus reconstructed ordered content inputs."""

    manifest_ref: StoredArtifactRef
    content_refs: tuple[StoredArtifactRef, ...]
    contents: tuple[ContentItem, ...]

    def __post_init__(self) -> None:
        if len(self.content_refs) != len(self.contents):
            raise ValueError("stored corpus requires one artifact reference per content item")
        if tuple(item.content_id for item in self.contents) == ():
            raise ValueError("stored corpus requires at least one content item")


def _load_snapshot(
    store: FileSystemArtifactStore,
    entry: CorpusContentEntry,
) -> CanonicalContentSnapshot:
    reference = entry.content_artifact_ref
    if reference is None:
        raise CanonicalContentError(
            "corpus manifest does not link canonical content artifacts"
        )
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    snapshot = CanonicalContentSnapshot.from_artifact(artifact)
    snapshot.verify_entry(entry)
    return snapshot


def load_canonical_corpus(
    store: FileSystemArtifactStore,
    manifest: CorpusManifestSnapshot,
) -> StoredCanonicalCorpus:
    """Reconstruct and verify every content item using only stored artifacts."""

    if not manifest.has_content_artifacts:
        raise CanonicalContentError(
            "storage-backed execution requires a fully linked corpus manifest"
        )
    manifest_artifact = store.get(
        manifest.corpus_id,
        expected_hash=manifest.artifact_hash,
    )
    if manifest_artifact.payload != manifest.canonical_payload:
        raise ArtifactIntegrityError(
            "stored corpus manifest differs from the expected canonical manifest"
        )
    snapshots = tuple(_load_snapshot(store, entry) for entry in manifest.contents)
    contents = tuple(item.to_content_item() for item in snapshots)
    return StoredCanonicalCorpus(
        manifest_ref=store.reference(manifest.corpus_id),
        content_refs=tuple(item.reference() for item in snapshots),
        contents=contents,
    )


def persist_canonical_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    manifest: CorpusManifestSnapshot,
    contents: tuple[ContentItem, ...],
) -> StoredCanonicalCorpus:
    """Persist linked content artifacts first and the corpus manifest last."""

    if not manifest.has_content_artifacts:
        raise CanonicalContentError(
            "canonical content persistence requires a fully linked corpus manifest"
        )
    validate_corpus_binding(plan, manifest, contents)
    for entry, content in zip(manifest.contents, contents, strict=True):
        snapshot = CanonicalContentSnapshot.from_content_item(content)
        snapshot.verify_entry(entry)
        reference = store.append(snapshot.artifact())
        if reference != snapshot.reference():
            raise ArtifactIntegrityError(
                "stored canonical content reference differs from expected identity"
            )
    manifest_ref = store.append(manifest.artifact())
    if manifest_ref.artifact_hash != manifest.artifact_hash:
        raise ArtifactIntegrityError(
            "stored corpus manifest reference differs from expected identity"
        )
    return load_canonical_corpus(store, manifest)
