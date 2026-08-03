from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from test_adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    CHECKPOINT_PATH,
    CORPUS_PATH,
    LOG_PATH,
    checkpoint,
    checkpoint_corpus,
    checkpoint_log,
    checkpoint_plan,
    checkpoint_policy,
    stored_ref_document,
)
from test_adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    revocation_ledger,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints,
)


def versioned_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_version": reference.artifact_version,
        "artifact_hash": reference.artifact_hash,
    }


def corpus_for(
    *,
    changed_checkpoint: Any,
    changed_log: Any,
):
    document = deepcopy(load_document(CORPUS_PATH))
    document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_log_ref"
    ] = versioned_ref_document(changed_log.reference())
    document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_head_ref"
    ] = stored_ref_document(changed_checkpoint.reference())
    return checkpoint_corpus(document)


def log_for(changed_checkpoint: Any):
    document = deepcopy(load_document(LOG_PATH))
    reference = stored_ref_document(changed_checkpoint.reference())
    document["checkpoint_refs"] = [reference]
    document["head_checkpoint_ref"] = reference
    return checkpoint_log(document)


def validate_changed(*, changed_checkpoint: Any, changed_log: Any) -> None:
    selected = corpus_for(
        changed_checkpoint=changed_checkpoint,
        changed_log=changed_log,
    )
    plan = replace(
        checkpoint_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
        plan=plan,
        corpus=selected,
        policy=checkpoint_policy(),
        log=changed_log,
        ledger=revocation_ledger(),
        checkpoints=(changed_checkpoint,),
        verified_at="2026-08-03T19:27:00Z",
    )


def test_checkpoint_manifest_content_order_drift_is_rejected() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["content_ids"] = ["content-003", "content-002", "content-001"]
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="content order",
    ):
        checkpoint_corpus(document)


def test_non_contiguous_checkpoint_sequence_is_rejected() -> None:
    document = deepcopy(load_document(CHECKPOINT_PATH))
    document["sequence_number"] = 1
    changed = checkpoint(document)
    changed_log = log_for(changed)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="contiguous",
    ):
        validate_changed(changed_checkpoint=changed, changed_log=changed_log)


def test_genesis_predecessor_is_rejected() -> None:
    document = deepcopy(load_document(CHECKPOINT_PATH))
    document["predecessor_checkpoint_ref"] = stored_ref_document(
        checkpoint().reference()
    )
    changed = checkpoint(document)
    changed_log = log_for(changed)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="genesis",
    ):
        validate_changed(changed_checkpoint=changed, changed_log=changed_log)


def test_stale_revocation_ledger_reference_is_rejected() -> None:
    document = deepcopy(load_document(CHECKPOINT_PATH))
    document["revocation_ledger_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    changed = checkpoint(document)
    changed_log = log_for(changed)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="ledger reference",
    ):
        validate_changed(changed_checkpoint=changed, changed_log=changed_log)
