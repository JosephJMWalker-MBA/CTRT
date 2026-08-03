from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.serialization import canonical_sha256

ROOT = Path(__file__).parents[1]


def test_probe_adjudicator_checkpoint_corpus_hash() -> None:
    document = cast(
        dict[str, Any],
        json.loads(
            (
                ROOT
                / "docs"
                / "corpora"
                / "extraction"
                / "synthetic-corpus.v1.2.0.json"
            ).read_text(encoding="utf-8")
        ),
    )
    raise AssertionError(canonical_sha256(document))
