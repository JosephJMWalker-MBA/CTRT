from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.serialization import canonical_sha256


def test_probe_v070_canonical_hash() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs"
        / "corpora"
        / "extraction"
        / "synthetic-corpus.v0.7.0.json"
    )
    document = cast(
        dict[str, Any],
        json.loads(path.read_text(encoding="utf-8")),
    )
    assert canonical_sha256(document) == (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
