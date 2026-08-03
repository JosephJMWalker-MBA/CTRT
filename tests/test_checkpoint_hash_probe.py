from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.credential_revocation_ledger import RevocationBoundCredentialCorpusSnapshot


def test_probe_v060_canonical_hash() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs"
        / "corpora"
        / "extraction"
        / "synthetic-corpus.v0.6.0.json"
    )
    document = cast(
        dict[str, Any],
        json.loads(path.read_text(encoding="utf-8")),
    )
    corpus = RevocationBoundCredentialCorpusSnapshot.from_document(document)
    expected = (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    assert corpus.reference().artifact_hash == expected
