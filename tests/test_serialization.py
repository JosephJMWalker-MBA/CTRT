from dataclasses import dataclass
from enum import StrEnum

import pytest

from ctrt.serialization import (
    CANONICALIZATION_VERSION,
    CanonicalSerializationError,
    canonical_json_text,
    canonical_sha256,
    serialize_artifact,
)


class State(StrEnum):
    READY = "ready"


@dataclass(frozen=True)
class Fixture:
    name: str
    state: State
    values: tuple[float, ...]


def test_mapping_order_does_not_change_canonical_bytes_or_hash() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    assert canonical_json_text(left) == '{"a":1,"b":2}'
    assert canonical_json_text(left) == canonical_json_text(right)
    assert canonical_sha256(left) == canonical_sha256(right)


def test_dataclasses_enums_tuples_and_negative_zero_are_canonicalized() -> None:
    fixture = Fixture(name="example", state=State.READY, values=(-0.0, 1.5))

    assert canonical_json_text(fixture) == (
        '{"name":"example","state":"ready","values":[0.0,1.5]}'
    )


def test_unicode_is_preserved_as_utf8_without_ascii_escaping() -> None:
    assert canonical_json_text({"text": "理解"}) == '{"text":"理解"}'


def test_nonfinite_numbers_and_unordered_values_are_rejected() -> None:
    with pytest.raises(CanonicalSerializationError, match="non-finite"):
        canonical_json_text({"value": float("nan")})
    with pytest.raises(CanonicalSerializationError, match="does not support set"):
        canonical_json_text({"values": {"a", "b"}})
    with pytest.raises(CanonicalSerializationError, match="keys must be strings"):
        canonical_json_text({1: "value"})


def test_serialized_artifact_hash_matches_payload_and_changes_with_content() -> None:
    first = serialize_artifact("artifact-001", {"value": 1})
    second = serialize_artifact("artifact-001", {"value": 2})

    assert first.canonicalization_version == CANONICALIZATION_VERSION
    assert first.text == '{"value":1}'
    assert first.artifact_hash == canonical_sha256({"value": 1})
    assert first.artifact_hash != second.artifact_hash
