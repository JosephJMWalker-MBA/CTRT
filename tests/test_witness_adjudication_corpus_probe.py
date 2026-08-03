# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def test_generate_adjudication_bound_corpus() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs"
        / "corpora"
        / "extraction"
        / "synthetic-corpus.v0.8.0.json"
    )
    document = cast(
        dict[str, Any],
        json.loads(path.read_text(encoding="utf-8")),
    )
    document.update(
        {
            "corpus_id": "corpus.synthetic-three-items.witness-adjudication-bound",
            "corpus_version": "0.9.0",
            "created_at": "2026-08-03T03:39:00Z",
            "checkpoint_witness_attestation_refs": [
                {
                    "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.alpha.v0.1.0",
                    "artifact_hash": "sha256:4816d4a7ab5aa3767e132a275c7565e8eea5f5c3155c0240d4d1d65de1b03cbd",
                    "canonicalization_version": "ctrt-canonical-json@0.1.0",
                    "media_type": "application/json",
                },
                {
                    "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.beta.v0.1.0",
                    "artifact_hash": "sha256:c5477d6c9b2e48fd061b2a33859ca32d1e6e2a573392a30125c7239726ebe144",
                    "canonicalization_version": "ctrt-canonical-json@0.1.0",
                    "media_type": "application/json",
                },
                {
                    "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.gamma.conflict.v0.1.0",
                    "artifact_hash": "sha256:95fd503da4e7115b8eda660dde00fd20e13c52469a06a644107d7a73662bd4ef",
                    "canonicalization_version": "ctrt-canonical-json@0.1.0",
                    "media_type": "application/json",
                },
            ],
            "adjudication_predecessor_corpus_ref": {
                "artifact_id": "corpus.synthetic-three-items.witness-bound",
                "artifact_version": "0.8.0",
                "artifact_hash": "sha256:fff4040660e400c467de4cd53e3f6b6fec1a85fe8910c82558d07bb316b70db5",
            },
            "witness_conflict_adjudicator_registry_ref": {
                "artifact_id": "registry.synthetic-witness-conflict-adjudicators",
                "artifact_version": "0.1.0",
                "artifact_hash": "sha256:9d1b928d874d84a405693274c096966400c74930fae8efd6f1d027b6645634aa",
            },
            "witness_conflict_adjudication_policy_ref": {
                "artifact_id": "policy.synthetic-witness-conflict-adjudication",
                "artifact_version": "0.1.0",
                "artifact_hash": "sha256:e590bc9415592ea0cf4943a6a7fa1d939b46cc9ad7ecbf001579baf59849cdc2",
            },
            "witness_conflict_adjudication_ref": {
                "artifact_id": "witness-conflict-adjudication:adjudication.synthetic.gamma-conflict.v0.1.0",
                "artifact_hash": "sha256:efbffaff4790173fed2bbef6377c89f79b93c88252477ad1f7a50290c69f8ece",
                "canonicalization_version": "ctrt-canonical-json@0.1.0",
                "media_type": "application/json",
            },
        }
    )
    raise AssertionError(json.dumps(document, indent=2, ensure_ascii=False))
