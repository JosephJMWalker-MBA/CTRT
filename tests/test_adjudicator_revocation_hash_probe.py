from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.adjudicator_credential_attestation import (
    CredentialBoundAdjudicationCorpusSnapshot,
)

ROOT = Path(__file__).parents[1]
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.0.0.json"
)


def test_adjudicator_credential_corpus_hash_probe() -> None:
    document = cast(
        dict[str, Any],
        json.loads(CORPUS_PATH.read_text(encoding="utf-8")),
    )
    corpus = CredentialBoundAdjudicationCorpusSnapshot.from_document(document)
    assert corpus.reference().artifact_hash == "sha256:PROBE"
