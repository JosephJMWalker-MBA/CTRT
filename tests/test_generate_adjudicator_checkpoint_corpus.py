from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.1.0.json"


def test_generate_adjudicator_checkpoint_corpus() -> None:
    document = cast(
        dict[str, Any],
        json.loads(SOURCE.read_text(encoding="utf-8")),
    )
    document["corpus_id"] = (
        "corpus.synthetic-three-items.adjudicator-revocation-checkpoint-bound"
    )
    document["corpus_version"] = "1.2.0"
    document["created_at"] = "2026-08-03T14:53:00Z"
    document["adjudicator_revocation_checkpoint_predecessor_corpus_ref"] = {
        "artifact_id": (
            "corpus.synthetic-three-items.adjudicator-credential-revocation-bound"
        ),
        "artifact_version": "1.1.0",
        "artifact_hash": (
            "sha256:0cc4d77649e2d240e719ed98f618f968ba884289663eaf07fd375241ca7e20ab"
        ),
    }
    document["adjudicator_credential_revocation_checkpoint_policy_ref"] = {
        "artifact_id": (
            "policy.synthetic-witness-conflict-adjudicator-revocation-checkpoints"
        ),
        "artifact_version": "0.1.0",
        "artifact_hash": (
            "sha256:7d9a30205a858e6e7cfa386ba370b151159efbc277ee49af6bad26ac6865c7e8"
        ),
    }
    document["adjudicator_credential_revocation_checkpoint_log_ref"] = {
        "artifact_id": (
            "log.synthetic-witness-conflict-adjudicator-revocation-checkpoints"
        ),
        "artifact_version": "0.1.0",
        "artifact_hash": (
            "sha256:4b940c395da7a18c4e337f424f642c39839f373e685fe31fd037c3981b694a43"
        ),
    }
    document["adjudicator_credential_revocation_checkpoint_head_ref"] = {
        "artifact_id": (
            "adjudicator-credential-revocation-checkpoint:"
            "checkpoint.synthetic.witness-conflict-adjudicator-revocations.0000"
        ),
        "artifact_hash": (
            "sha256:4034f2202a16a95902b535e38330d71358e5485ded645c4c649cccb1967c5e45"
        ),
        "canonicalization_version": "ctrt-canonical-json@0.1.0",
        "media_type": "application/json",
    }
    raise AssertionError(json.dumps(document, indent=2, ensure_ascii=False))
