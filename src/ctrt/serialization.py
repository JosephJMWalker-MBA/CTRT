"""Deterministic canonical JSON serialization and hashing for CTRT artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum

CANONICALIZATION_VERSION = "ctrt-canonical-json@0.1.0"
JSON_MEDIA_TYPE = "application/json"


class CanonicalSerializationError(ValueError):
    """Raised when a value cannot be represented by the CTRT canonical profile."""


def _canonical_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalSerializationError("canonical JSON forbids non-finite numbers")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalSerializationError("canonical JSON mapping keys must be strings")
            result[key] = _canonical_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset, bytes, bytearray)):
        raise CanonicalSerializationError(
            f"canonical JSON does not support {type(value).__name__} values"
        )
    raise CanonicalSerializationError(
        f"canonical JSON does not support {type(value).__name__} values"
    )


def canonical_data(value: object) -> object:
    """Convert a supported value into JSON-compatible canonical data."""

    return _canonical_value(value)


def canonical_json_text(value: object) -> str:
    """Serialize a supported value using the CTRT canonical JSON profile."""

    return json.dumps(
        canonical_data(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_bytes(value: object) -> bytes:
    """Return canonical UTF-8 JSON bytes with no trailing newline."""

    return canonical_json_text(value).encode("utf-8")


def canonical_sha256(value: object) -> str:
    """Hash canonical JSON bytes using the repository's sha256: convention."""

    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True, slots=True)
class CanonicalArtifact:
    """Canonical serialized artifact payload and its deterministic identity."""

    artifact_id: str
    payload: bytes
    artifact_hash: str
    canonicalization_version: str = CANONICALIZATION_VERSION
    media_type: str = JSON_MEDIA_TYPE

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("artifact_id must not be empty")
        expected = f"sha256:{hashlib.sha256(self.payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ValueError("artifact_hash must match canonical payload bytes")
        if self.canonicalization_version != CANONICALIZATION_VERSION:
            raise ValueError("unsupported canonicalization version")
        if self.media_type != JSON_MEDIA_TYPE:
            raise ValueError("unsupported canonical artifact media type")

    @property
    def text(self) -> str:
        """Decode the canonical UTF-8 payload."""

        return self.payload.decode("utf-8")


def serialize_artifact(artifact_id: str, value: object) -> CanonicalArtifact:
    """Serialize and hash one immutable artifact using the canonical profile."""

    payload = canonical_json_bytes(value)
    return CanonicalArtifact(
        artifact_id=artifact_id,
        payload=payload,
        artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
    )
