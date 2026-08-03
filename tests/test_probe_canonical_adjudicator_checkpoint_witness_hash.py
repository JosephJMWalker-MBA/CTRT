import json
from pathlib import Path

from ctrt.serialization import canonical_sha256


def test_probe_canonical_adjudicator_checkpoint_witness_hash() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs"
        / "corpora"
        / "extraction"
        / "synthetic-corpus.v1.3.0.json"
    )
    raise AssertionError(canonical_sha256(json.loads(path.read_text(encoding="utf-8"))))
