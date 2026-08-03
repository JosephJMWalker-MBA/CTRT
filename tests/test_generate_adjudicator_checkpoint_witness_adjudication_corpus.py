# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.3.0.json"
OUTPUT = ROOT / "generated-artifacts" / "synthetic-corpus.v1.4.0.json"


def test_generate_adjudicator_checkpoint_witness_adjudication_corpus() -> None:
    document = cast(dict[str, Any], json.loads(SOURCE.read_text(encoding="utf-8")))
    document["corpus_id"] = (
        "corpus.synthetic-three-items.adjudicator-checkpoint-witness-adjudication-bound"
    )
    document["corpus_version"] = "1.4.0"
    document["created_at"] = "2026-08-03T16:01:00Z"
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
            "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.adjudicator-gamma.conflict.v0.1.0",
            "artifact_hash": "sha256:807375f416e1fbf9c4dff0799da57ccdac885ec8bf863021a74a5df8d41f51e9",
            "canonicalization_version": "ctrt-canonical-json@0.1.0",
            "media_type": "application/json",
        },
    ]
    document["adjudicator_checkpoint_witness_adjudication_predecessor_corpus_ref"] = {
        "artifact_id": "corpus.synthetic-three-items.adjudicator-checkpoint-witness-bound",
        "artifact_version": "1.3.0",
        "artifact_hash": "sha256:40ace6feb9b4193f4181d485f14bc07684f5b8503787c9412bddb4602cf84a0e",
    }
    document["adjudicator_checkpoint_witness_conflict_adjudicator_registry_ref"] = {
        "artifact_id": "registry.synthetic-adjudicator-checkpoint-witness-conflict-adjudicators",
        "artifact_version": "0.1.0",
        "artifact_hash": "sha256:75d53fccaf08e780f26e18ee3be142681ea28fad9160c79ff047b7ec89a5af1c",
    }
    document["adjudicator_checkpoint_witness_conflict_adjudication_policy_ref"] = {
        "artifact_id": "policy.synthetic-adjudicator-checkpoint-witness-conflict-adjudication",
        "artifact_version": "0.1.0",
        "artifact_hash": "sha256:49ec2d5e4fe656a455a08cfc89bce8be74f20a5de7261791a3321d68f1545f3c",
    }
    document["adjudicator_checkpoint_witness_conflict_adjudication_ref"] = {
        "artifact_id": "witness-conflict-adjudication:adjudication.synthetic.adjudicator-checkpoint-gamma-conflict.v0.1.0",
        "artifact_hash": "sha256:274d7fad984419e32354cf69d3d9200a8abec5f8bd200b45e18be930e092acf4",
        "canonicalization_version": "ctrt-canonical-json@0.1.0",
        "media_type": "application/json",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert json.loads(OUTPUT.read_text(encoding="utf-8")) == document
