from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.witness_conflict_adjudication import AdjudicationBoundWitnessCorpusSnapshot

ROOT = Path(__file__).parents[1]
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.9.0.json"
)


def test_adjudication_corpus_hash_probe() -> None:
    document = cast(
        dict[str, Any],
        json.loads(CORPUS_PATH.read_text(encoding="utf-8")),
    )
    corpus = AdjudicationBoundWitnessCorpusSnapshot.from_document(document)
    assert corpus.reference().artifact_hash == "sha256:PROBE"
