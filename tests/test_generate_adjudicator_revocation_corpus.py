from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.0.0.json"


def test_generate_adjudicator_revocation_corpus() -> None:
    document = cast(
        dict[str, Any],
        json.loads(SOURCE.read_text(encoding="utf-8")),
    )
    document["corpus_id"] = (
        "corpus.synthetic-three-items.adjudicator-credential-revocation-bound"
    )
    document["corpus_version"] = "1.1.0"
    document["created_at"] = "2026-08-03T13:48:30Z"
    document["adjudicator_credential_revocation_predecessor_corpus_ref"] = {
        "artifact_id": "corpus.synthetic-three-items.adjudicator-credential-bound",
        "artifact_version": "1.0.0",
        "artifact_hash": (
            "sha256:66d51cea8628df405ceb94e15a39effc55d3fa08b21adcaaae5ef5c539eb0dca"
        ),
    }
    document["adjudicator_credential_revocation_policy_ref"] = {
        "artifact_id": (
            "policy.synthetic-witness-conflict-adjudicator-credential-revocation"
        ),
        "artifact_version": "0.1.0",
        "artifact_hash": (
            "sha256:4c1caa0d4ec560c8a69cb0838390290787702297677c861ddc2c7522913f4e6f"
        ),
    }
    document["adjudicator_credential_revocation_ledger_ref"] = {
        "artifact_id": (
            "ledger.synthetic-witness-conflict-adjudicator-credential-revocations"
        ),
        "artifact_version": "0.1.0",
        "artifact_hash": (
            "sha256:ea15075c2df63244aabed53d61e28c19171ae4c45c61414e426bd89f2364bbc2"
        ),
    }
    raise AssertionError(json.dumps(document, indent=2, ensure_ascii=False))
