# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def test_generate_witness_bound_corpus() -> None:
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
    document.update(
        {
            "corpus_id": "corpus.synthetic-three-items.witness-bound",
            "corpus_version": "0.8.0",
            "created_at": "2026-08-03T03:04:00Z",
            "witness_predecessor_corpus_ref": {
                "artifact_id": "corpus.synthetic-three-items.checkpoint-bound",
                "artifact_version": "0.7.0",
                "artifact_hash": "sha256:438064d97f7de03fd0691ba96e51d3fba0a2be80599235054ec53287c59768f3",
            },
            "checkpoint_witness_registry_ref": {
                "artifact_id": "registry.synthetic-checkpoint-witnesses",
                "artifact_version": "0.1.0",
                "artifact_hash": "sha256:aeb4180c247db518a834eaaf445f2a5815bdac34b13f036f1a25470e2a74d8c1",
            },
            "checkpoint_witness_policy_ref": {
                "artifact_id": "policy.synthetic-checkpoint-witnesses",
                "artifact_version": "0.1.0",
                "artifact_hash": "sha256:75eac249bf3ded723ce1d8b57b70642866ca59eb6575b4363823e72f3db13edd",
            },
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
                    "artifact_id": "checkpoint-witness-attestation:attestation.synthetic.gamma.v0.1.0",
                    "artifact_hash": "sha256:f6d614cc1afd07a50ee466922c7f1499e1b125052fdc87980624da3df8089811",
                    "canonicalization_version": "ctrt-canonical-json@0.1.0",
                    "media_type": "application/json",
                },
            ],
        }
    )
    raise AssertionError(json.dumps(document, indent=2, ensure_ascii=False))
