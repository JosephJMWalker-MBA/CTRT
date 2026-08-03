from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.adjudicator_credential_revocation_ledger import (
    RevocationBoundAdjudicatorCredentialCorpusSnapshot,
)

ROOT = Path(__file__).parents[1]
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.1.0.json"
)


def test_adjudicator_revocation_corpus_hash_probe() -> None:
    document = cast(
        dict[str, Any],
        json.loads(CORPUS_PATH.read_text(encoding="utf-8")),
    )
    corpus = RevocationBoundAdjudicatorCredentialCorpusSnapshot.from_document(document)
    assert corpus.reference().artifact_hash == "sha256:PROBE"
