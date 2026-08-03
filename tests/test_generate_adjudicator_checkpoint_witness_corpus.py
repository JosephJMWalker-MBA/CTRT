# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.2.0.json"


def test_generate_adjudicator_checkpoint_witness_corpus() -> None:
    document = cast(
        dict[str, Any],
        json.loads(SOURCE.read_text(encoding="utf-8")),
    )
    document["corpus_id"] = (
        "corpus.synthetic-three-items.adjudicator-checkpoint-witness-bound"
    )
    document["corpus_version"] = "1.3.0"
    document["created_at"] = "2026-08-03T14:56:00Z"
    document["adjudicator_checkpoint_witness_predecessor_corpus_ref"] = {
        "artifact_id": "corpus.synthetic-three-items.adjudicator-revocation-checkpoint-bound",
        "artifact_version": "1.2.0",
        "artifact_hash": "sha256:152eab38e3b72a2d8293ec88202fed3adaaf969df22e160b7a9f12983580d257",
    }
    document["adjudicator_checkpoint_witness_registry_ref"] = {
        "artifact_id": "registry.synthetic-adjudicator-checkpoint-witnesses",
        "artifact_version": "0.1.0",
        "artifact_hash": "sha256:b5ac0ac412e26fb1c7b175459cad16647a3fbae24a8d8906d3fcceff14bcd770",
    }
    document["adjudicator_checkpoint_witness_policy_ref"] = {
        "artifact_id": "policy.synthetic-adjudicator-checkpoint-witnesses",
        "artifact_version": "0.1.0",
        "artifact_hash": "sha256:794179e9e7f97a96129e3a59820fcaf2f2c19c591ebe81fce2c32c8213253b30",
    }
    document["adjudicator_checkpoint_witness_attestation_refs"] = [
        {
            "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.adjudicator-alpha.v0.1.0",
            "artifact_hash": "sha256:5d2c87e61e76cabb114e51692bb44b3f2c9de5f14eb6a1e28c7da7c464c0a267",
            "canonicalization_version": "ctrt-canonical-json@0.1.0",
            "media_type": "application/json",
        },
        {
            "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.adjudicator-beta.v0.1.0",
            "artifact_hash": "sha256:fa2f6713be315e5b0cef2f92d66a69980eab376821d7ad9cf5020fd9283627f8",
            "canonicalization_version": "ctrt-canonical-json@0.1.0",
            "media_type": "application/json",
        },
        {
            "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.adjudicator-gamma.v0.1.0",
            "artifact_hash": "sha256:0251fa5a4ee60769791ddf81978e0a3cfffe300ca641cabe0b8cbbcb01c36e24",
            "canonicalization_version": "ctrt-canonical-json@0.1.0",
            "media_type": "application/json",
        },
    ]
    raise AssertionError(json.dumps(document, indent=2, ensure_ascii=False))
