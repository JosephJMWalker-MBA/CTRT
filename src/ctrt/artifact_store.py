"""Append-only filesystem persistence for canonical CTRT artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ctrt.artifact_pipeline import ExperimentArtifactBundle
from ctrt.serialization import (
    CANONICALIZATION_VERSION,
    JSON_MEDIA_TYPE,
    CanonicalArtifact,
    canonical_json_bytes,
    serialize_artifact,
)


class ArtifactStoreError(RuntimeError):
    """Base class for append-only artifact-store failures."""


class ArtifactNotFoundError(ArtifactStoreError):
    """Raised when an artifact ID or hash is absent."""


class ArtifactConflictError(ArtifactStoreError):
    """Raised when an existing artifact ID is assigned different content."""


class ArtifactIntegrityError(ArtifactStoreError):
    """Raised when stored bytes or index metadata fail verification."""


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _digest(artifact_hash: str) -> str:
    prefix = "sha256:"
    if not artifact_hash.startswith(prefix):
        raise ValueError("artifact hash must use a sha256: prefix")
    digest = artifact_hash[len(prefix) :]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("artifact hash must contain a lowercase 64-character SHA-256 digest")
    return digest


def _required_string(document: Mapping[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ArtifactIntegrityError(f"stored artifact index has invalid {key}")
    return value


@dataclass(frozen=True, slots=True)
class StoredArtifactRef:
    """Immutable identity recorded by the artifact ID index."""

    artifact_id: str
    artifact_hash: str
    canonicalization_version: str = CANONICALIZATION_VERSION
    media_type: str = JSON_MEDIA_TYPE

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("stored artifact_id must not be empty")
        _digest(self.artifact_hash)
        if self.canonicalization_version != CANONICALIZATION_VERSION:
            raise ValueError("unsupported stored canonicalization version")
        if self.media_type != JSON_MEDIA_TYPE:
            raise ValueError("unsupported stored artifact media type")

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> StoredArtifactRef:
        """Parse and validate one persisted ID-index record."""

        return cls(
            artifact_id=_required_string(document, "artifact_id"),
            artifact_hash=_required_string(document, "artifact_hash"),
            canonicalization_version=_required_string(
                document,
                "canonicalization_version",
            ),
            media_type=_required_string(document, "media_type"),
        )


@dataclass(frozen=True, slots=True)
class BundleArtifactRef:
    """One role-bound artifact required by a complete experiment bundle."""

    role: str
    artifact: StoredArtifactRef

    def __post_init__(self) -> None:
        if not self.role.strip():
            raise ValueError("bundle artifact role must not be empty")


@dataclass(frozen=True, slots=True)
class ExperimentBundleManifest:
    """Completion marker for one fully persisted experiment artifact bundle."""

    bundle_id: str
    run_record_id: str
    artifacts: tuple[BundleArtifactRef, ...]

    def __post_init__(self) -> None:
        if not self.bundle_id.strip() or not self.run_record_id.strip():
            raise ValueError("bundle identity fields must not be empty")
        roles = tuple(item.role for item in self.artifacts)
        if len(roles) != len(set(roles)):
            raise ValueError("bundle artifact roles must be unique")
        required = {"plan", "candidate-eligibility", "environment", "comparison", "run-record"}
        if not required.issubset(roles):
            raise ValueError("bundle manifest is missing a required artifact role")
        result_roles = tuple(role for role in roles if role.startswith("result:"))
        if len(result_roles) < 2:
            raise ValueError("bundle manifest requires at least two result artifacts")


@dataclass(frozen=True, slots=True)
class StoredExperimentBundle:
    """Verified reference to a persisted experiment bundle manifest."""

    manifest: ExperimentBundleManifest
    manifest_ref: StoredArtifactRef

    def __post_init__(self) -> None:
        if self.manifest.bundle_id != self.manifest_ref.artifact_id:
            raise ValueError("bundle manifest reference must use the bundle ID")


class FileSystemArtifactStore:
    """Local append-only store using content-addressed blobs and immutable ID indexes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._blob_root = root / "blobs" / "sha256"
        self._index_root = root / "ids" / "sha256"
        self._blob_root.mkdir(parents=True, exist_ok=True)
        self._index_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _id_key(artifact_id: str) -> str:
        return hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()

    def _blob_path(self, artifact_hash: str) -> Path:
        return self._blob_root / _digest(artifact_hash)

    def _index_path(self, artifact_id: str) -> Path:
        return self._index_root / f"{self._id_key(artifact_id)}.json"

    @staticmethod
    def _write_exclusive(path: Path, payload: bytes) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return False
        return True

    @staticmethod
    def _read_index(path: Path) -> StoredArtifactRef:
        try:
            document = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError("stored artifact index is unreadable") from exc
        return StoredArtifactRef.from_document(document)

    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        """Persist canonical bytes exactly once; identical repeats are idempotent."""

        reference = StoredArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_hash=artifact.artifact_hash,
            canonicalization_version=artifact.canonicalization_version,
            media_type=artifact.media_type,
        )
        blob_path = self._blob_path(reference.artifact_hash)
        if not self._write_exclusive(blob_path, artifact.payload):
            existing_payload = blob_path.read_bytes()
            if existing_payload != artifact.payload:
                raise ArtifactIntegrityError(
                    "stored hash resolves to different bytes; collision or corruption detected"
                )

        index_path = self._index_path(reference.artifact_id)
        index_payload = canonical_json_bytes(reference)
        if not self._write_exclusive(index_path, index_payload):
            existing = self._read_index(index_path)
            if existing.artifact_id != reference.artifact_id:
                raise ArtifactIntegrityError("artifact ID index-key collision detected")
            if existing.artifact_hash != reference.artifact_hash:
                raise ArtifactConflictError(
                    "artifact ID is append-only and already references a different hash"
                )
            if existing != reference:
                raise ArtifactIntegrityError("artifact ID index metadata does not match")

        self.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        return reference

    def get(self, artifact_id: str, *, expected_hash: str | None = None) -> CanonicalArtifact:
        """Retrieve canonical bytes by ID and re-verify their SHA-256 identity."""

        index_path = self._index_path(artifact_id)
        if not index_path.exists():
            raise ArtifactNotFoundError(f"artifact ID is not stored: {artifact_id}")
        reference = self._read_index(index_path)
        if reference.artifact_id != artifact_id:
            raise ArtifactIntegrityError("artifact ID index does not match the requested ID")
        if expected_hash is not None and reference.artifact_hash != expected_hash:
            raise ArtifactIntegrityError("stored artifact hash does not match the expected hash")
        payload = self.read_payload(reference.artifact_hash)
        return CanonicalArtifact(
            artifact_id=reference.artifact_id,
            payload=payload,
            artifact_hash=reference.artifact_hash,
            canonicalization_version=reference.canonicalization_version,
            media_type=reference.media_type,
        )

    def read_payload(self, artifact_hash: str) -> bytes:
        """Retrieve bytes by content hash and verify the digest before returning them."""

        blob_path = self._blob_path(artifact_hash)
        if not blob_path.exists():
            raise ArtifactNotFoundError(f"artifact hash is not stored: {artifact_hash}")
        try:
            payload = blob_path.read_bytes()
        except OSError as exc:
            raise ArtifactIntegrityError("stored artifact blob is unreadable") from exc
        if _sha256_bytes(payload) != artifact_hash:
            raise ArtifactIntegrityError("stored artifact blob failed SHA-256 verification")
        return payload

    def reference(self, artifact_id: str) -> StoredArtifactRef:
        """Return a verified immutable reference for one stored artifact ID."""

        artifact = self.get(artifact_id)
        return StoredArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_hash=artifact.artifact_hash,
            canonicalization_version=artifact.canonicalization_version,
            media_type=artifact.media_type,
        )


def _bundle_artifacts(
    bundle: ExperimentArtifactBundle,
) -> tuple[tuple[str, CanonicalArtifact], ...]:
    result_items = tuple(
        (f"result:{index}", artifact)
        for index, artifact in enumerate(bundle.results)
    )
    return (
        ("plan", bundle.plan),
        ("candidate-eligibility", bundle.candidate_eligibility),
        ("environment", bundle.environment),
        *result_items,
        ("comparison", bundle.comparison),
        ("run-record", bundle.run_record_artifact),
    )


def persist_experiment_bundle(
    store: FileSystemArtifactStore,
    bundle: ExperimentArtifactBundle,
) -> StoredExperimentBundle:
    """Persist all bundle artifacts, then append a completion manifest last."""

    references = tuple(
        BundleArtifactRef(role=role, artifact=store.append(artifact))
        for role, artifact in _bundle_artifacts(bundle)
    )
    manifest = ExperimentBundleManifest(
        bundle_id=f"{bundle.run_record.record_id}:artifact-bundle",
        run_record_id=bundle.run_record.record_id,
        artifacts=references,
    )
    manifest_artifact = serialize_artifact(manifest.bundle_id, manifest)
    stored = StoredExperimentBundle(
        manifest=manifest,
        manifest_ref=store.append(manifest_artifact),
    )
    verify_experiment_bundle(store, stored)
    return stored


def verify_experiment_bundle(
    store: FileSystemArtifactStore,
    stored: StoredExperimentBundle,
) -> None:
    """Re-verify the manifest and every artifact required by the bundle."""

    manifest_artifact = store.get(
        stored.manifest_ref.artifact_id,
        expected_hash=stored.manifest_ref.artifact_hash,
    )
    expected_manifest = serialize_artifact(stored.manifest.bundle_id, stored.manifest)
    if manifest_artifact.payload != expected_manifest.payload:
        raise ArtifactIntegrityError("stored bundle manifest differs from the expected manifest")
    for item in stored.manifest.artifacts:
        store.get(
            item.artifact.artifact_id,
            expected_hash=item.artifact.artifact_hash,
        )
