from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.reviewer_credential_attestation import CredentialBoundReviewCorpusSnapshot


def test_probe_v050_canonical_hash() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs"
        / "corpora"
        / "extraction"
        / "synthetic-corpus.v0.5.0.json"
    )
    document = cast(
        dict[str, Any],
        json.loads(path.read_text(encoding="utf-8")),
    )
    corpus = CredentialBoundReviewCorpusSnapshot.from_document(document)
    expected = (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    assert corpus.artifact_hash == expected
