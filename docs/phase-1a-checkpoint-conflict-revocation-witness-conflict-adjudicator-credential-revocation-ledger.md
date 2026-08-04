# Phase 1A — Checkpoint-conflict witness adjudicator credential revocation ledger

## Purpose

This layer adds append-only, time-relative status history to the exact issuer-bound credential introduced for checkpoint-conflict witness adjudication in ADR-0035.

It answers one bounded operational question:

> What was the exact effective status of the exact credential at the declared time, according to the exact frozen issuer-authored event history?

It does not change the credential, issuer registry, credential policy, adjudication record, witness observations, witness outcome, fork evidence, dissent, rationale, selected checkpoint head, or any lower execution artifact.

## Position in the authority graph

```text
1.11.0 revocation-bound corpus
  -> exact 1.10.0 issuer-bound credential corpus
    -> exact 1.9.0 witness-conflict adjudication corpus
      -> exact 1.8.0 witness-bound corpus and receipt
        -> exact 1.7.0 checkpoint-bound lower lifecycle
```

Each layer makes a narrower claim without rewriting the layer below it.

## Four independent outcomes

```text
witness outcome       -> what the required named witnesses reported
adjudication outcome  -> what accepted adjudication authority selected
credential outcome    -> whether that authority was issuer-authorized then
revocation outcome    -> whether append-only status history permitted credential evaluation
```

These outcomes may differ legitimately.

Examples:

```text
revocation=execute, credential=execute, adjudication=execute
```

means the status history permitted credential evaluation, the credential was eligible, and the adjudication authorized execution.

```text
revocation=abstain, credential=null, adjudication=null
```

means effective suspension or revocation stopped the run before credential evaluation.

```text
revocation=execute, credential=abstain, adjudication=null
```

means revocation history permitted credential evaluation, but the credential independently failed its own validity or status rules later.

## Fixed immutable artifacts

### Revocation policy

Path:

```text
docs/candidates/synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-policy.v0.1.0.json
```

Identity:

```text
policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation@0.1.0
```

Canonical hash:

```text
sha256:c2c986f5f75c0e1bcb288283e634e60cfd99bf1f5289cc2381b8ea2e90ca030f
```

The policy is accepted and requires:

- exact attestation issuer authority;
- permitted effects limited to `active`, `suspended`, and `revoked`;
- monotonic effective time;
- linear supersession;
- abstention for effective `suspended` or `revoked` status.

Created at:

```text
2026-08-03T19:54:32Z
```

### Future-effective suspension event

Path:

```text
docs/corpora/extraction/revocations/witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation/witness-conflict-adjudicator-credential-suspension-event.json
```

Identity:

```text
adjudicator-credential-revocation-event:event.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator.suspension.v0.1.0
```

Canonical hash:

```text
sha256:2ebecda7a78b91ffde208dc7f200feb2b79bcb6aefdbcf5d806526ce6791be1a
```

The event binds:

```text
credential = adjudicator-credential:credential.synthetic.checkpoint-conflict-revocation-witness-conflict.v0.1.0
credential hash = sha256:a206414a2a1e98f510326e8a0cf6ecae2f35a58740f5f50b936382123549d318
adjudicator = adjudicator.synthetic.checkpoint-conflict-revocation-checkpoint-witness-conflict
issuer = issuer.synthetic.checkpoint-conflict-revocation-witness-conflict-governance
issuer revision = synthetic-checkpoint-conflict-revocation-witness-conflict-governance@0.1.0
effect = suspended
recorded_at = 2026-08-03T19:54:36Z
effective_at = 2027-01-01T00:00:00Z
supersedes_event_id = null
```

### Frozen revocation ledger

Path:

```text
docs/corpora/extraction/revocations/witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation/witness-conflict-adjudicator-credential-revocation-ledger.v0.1.0.json
```

Identity:

```text
ledger.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations@0.1.0
```

Canonical hash:

```text
sha256:697066b82e49ceb53b3b9c3c1539dbb9801f981eb94e89dbd3275c14f9e4bda6
```

The ledger is frozen and binds:

- the exact `1.10.0` credential corpus;
- the exact ADR-0035 issuer registry;
- the exact revocation policy;
- the exact ordered event population.

Created at:

```text
2026-08-03T19:54:42Z
```

### Compact successor corpus

Path:

```text
docs/corpora/extraction/synthetic-corpus.v1.11.0.json
```

Identity:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-bound@1.11.0
```

Canonical hash:

```text
sha256:33b05c3429a0d8f58bb12a4ad497c1c885a4e23386fc80fa017f8cbe9ccaf280
```

Exact predecessor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-bound@1.10.0
sha256:1ef073d0b8af20d4ea511f7828a0f90d753d532a1c46b3d6bd36e8a90df21b0f
```

Published at:

```text
2026-08-03T19:54:48Z
```

The ordered content population remains:

```text
content-001
content-002
content-003
```

## Temporal model

### `recorded_at`

`recorded_at` states when the event entered the issuer-authored history.

An event may not belong to a historical ledger decision before this time.

### `effective_at`

`effective_at` states when the already-recorded event changes effective credential status.

A future-effective event may be recorded and frozen before its effect begins.

### Required chronology

For every accepted decision:

```text
policy.created_at
  <= event.recorded_at
  <= ledger.created_at
  <= successor.created_at
  <= revocation_evaluated_at
  <= credential_evaluated_at
```

The complete canonical execution chronology is:

```text
2026-08-03T19:53:30Z  witness evaluated
2026-08-03T19:54:05Z  credential issuer registry created
2026-08-03T19:54:15Z  credential policy created
2026-08-03T19:54:25Z  credential issued
2026-08-03T19:54:30Z  credential validity begins
2026-08-03T19:54:32Z  revocation policy created
2026-08-03T19:54:36Z  future suspension recorded
2026-08-03T19:54:42Z  revocation ledger frozen
2026-08-03T19:54:48Z  1.11.0 successor published
2026-08-03T19:54:50Z  revocation status evaluated
2026-08-03T19:55:00Z  credential evaluated
2026-08-03T19:55:30Z  adjudication evaluated
2026-08-03T19:56:00Z  adjudication lifecycle completed
2026-08-03T19:56:30Z  credential lifecycle completed
2026-08-03T19:56:45Z  revocation lifecycle completed
```

The future suspension becomes effective at:

```text
2027-01-01T00:00:00Z
```

## Publication order

Publication is manifest-last:

```text
1. accepted revocation policy
2. immutable event population in exact order
3. frozen revocation ledger
4. compact 1.11.0 successor manifest
5. exact-hash reread of the complete graph
```

The manifest is not published when any earlier artifact fails validation, append, or reread.

## Contract module

Path:

```text
src/ctrt/checkpoint_conflict_witness_adjudicator_credential_revocation_ledger.py
```

Primary successor type:

```text
RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot
```

The successor wraps the exact immutable:

```text
CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
```

Public contract operations:

```text
load_checkpoint_conflict_witness_adjudicator_credential_revocation_evidence
validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger
persist_checkpoint_conflict_witness_adjudicator_credential_revocation_bound_corpus
```

The context adapter reuses the established generic adjudicator credential revocation grammar:

```text
AdjudicatorCredentialRevocationPolicySnapshot
AdjudicatorCredentialRevocationEventSnapshot
AdjudicatorCredentialRevocationLedgerSnapshot
AdjudicatorCredentialRevocationDecisionReport
StoredAdjudicatorCredentialRevocationEvidence
```

It adds the context-specific temporal rule that recorded history must exist before the as-of decision uses it.

## Effective-status algorithm

The validator performs these steps:

1. verify the exact frozen `1.11.0` plan and content order;
2. verify the exact `1.10.0` predecessor;
3. verify the exact revocation policy and frozen ledger references;
4. verify policy, event recording, ledger freeze, successor publication, and evaluation chronology;
5. verify the ledger binds the exact credential corpus, issuer registry, policy, and ordered event population;
6. verify every event binds the exact credential, adjudicator, issuer, and issuer revision;
7. verify each effect is permitted;
8. verify event IDs and references are unique;
9. verify linear supersession and nondecreasing effective time;
10. derive the immutable credential's declared base status;
11. select applicable events where `effective_at <= evaluated_at`;
12. apply applicable events in exact ledger order;
13. retain every applied event ID;
14. produce `execute` for permitted effective status or governed `abstain` for `suspended` or `revoked`.

## Canonical status states

### Before the suspension boundary

```text
evaluated_at = 2026-12-31T23:59:59Z
base_status = active
effective_status = active
applied_event_ids = []
revocation_outcome = execute
```

### At the suspension boundary

```text
evaluated_at = 2027-01-01T00:00:00Z
base_status = active
effective_status = suspended
applied_event_ids = [event.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator.suspension.v0.1.0]
revocation_outcome = abstain
```

The original credential remains:

```text
status = active
revoked_at = null
revocation_reason = null
```

Those fields are preserved evidence, not a mutable current-status cache.

## Revocation-gated runner

Path:

```text
src/ctrt/revocation_gated_checkpoint_conflict_witness_adjudication_runner.py
```

Primary runner:

```text
RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner
```

Verified receipt:

```text
VerifiedCheckpointConflictWitnessRevocationReceipt
```

Final manifest:

```text
CheckpointConflictWitnessRevocationFinalManifest
```

Failure type:

```text
CheckpointConflictWitnessRevocationExperimentError
```

Failure stages:

```text
preflight
evidence-loading
revocation-validation
decision-persistence
credential-execution
final-persistence
verification
```

## Runner sequence

The runner performs:

1. exact plan, predecessor, policy, ledger, run, content-order, and chronology preflight;
2. storage-backed loading and hash verification of the complete revocation graph;
3. storage-backed loading and hash verification of the exact credential graph;
4. exact as-of revocation validation;
5. run-specific revocation-decision append and reread;
6. terminal revocation abstention or exact `1.10.0` plan derivation;
7. delegation to the unchanged ADR-0035 credential runner only after revocation `execute`;
8. outer final append;
9. reread of the final, successor, predecessor, policy, ledger, events, credential authority, adjudication record, decision, and optional credential final.

## Explicit plan scopes

```text
1.11.0 plan   -> revocation evaluation and outer finalization
1.10.0 plan   -> unchanged credential evaluation
1.9.0 plan    -> unchanged witness-conflict adjudication
1.8.0 receipt -> immutable original witness result and observations
1.7.0 scope   -> lower checkpoint and downstream lifecycle
```

Only the corpus reference is narrowed between layers.

## Run-specific artifacts

Revocation decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-decision
```

Terminal revocation abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-abstention
```

Successful delegated execution:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-completion
```

Revocation authorization followed by later credential or lower-layer abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-terminal-abstention
```

## Outcome behavior

### Revocation `abstain`

The final contains:

```text
revocation_outcome = abstain
credential_outcome = null
checkpoint_witness_outcome = null
resolution_status = null
adjudication_outcome = null
terminal_outcome = abstain
credential_final_ref = null
```

No ADR-0035 credential decision or ADR-0034 adjudication decision is created by the run.

### Revocation `execute`, credential `abstain`

The final contains:

```text
revocation_outcome = execute
credential_outcome = abstain
checkpoint_witness_outcome = null
resolution_status = null
adjudication_outcome = null
terminal_outcome = abstain
credential_final_ref = exact ADR-0035 abstention final
```

The later credential abstention does not change the earlier revocation outcome.

### Full execution

The canonical path contains:

```text
revocation_outcome = execute
credential_outcome = execute
checkpoint_witness_outcome = execute
resolution_status = not_required
adjudication_outcome = execute
terminal_outcome = execute
```

All earlier decisions and finals remain separately stored.

## Schemas

Context-specific successor schema:

```text
schemas/checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-bound-corpus.schema.json
```

Generic reused schemas:

```text
schemas/adjudicator-credential-revocation-policy.schema.json
schemas/adjudicator-credential-revocation-event.schema.json
schemas/adjudicator-credential-revocation-ledger.schema.json
schemas/adjudicator-credential-revocation-decision.schema.json
```

Outer final schema:

```text
schemas/revocation-gated-checkpoint-conflict-witness-adjudication-final.schema.json
```

Schemas reject undeclared fields such as confidence, vote count, quorum, consensus, reputation, private identity, or aggregate authority.

## Test coverage

Contract tests prove:

- deterministic canonical policy, event, ledger, and successor hashes;
- exact `1.10.0` predecessor binding;
- exact content order;
- active status before the future-effective event;
- suspended status at the event boundary;
- base credential status remains unchanged;
- applied event IDs remain explicit;
- issuer-revision drift is structural failure;
- event recording after ledger freeze is structural failure;
- evaluation before successor publication is structural failure;
- exact manifest-last persistence and idempotent storage reconstruction;
- rejection of unsupported confidence fields;
- policy, event, ledger, successor, decision, and final schemas.

Stored lifecycle tests prove:

1. active status delegates the exact PR #32 lifecycle;
2. effective suspension creates no PR #32 credential decision and no PR #31 adjudication decision;
3. revocation evaluation after credential evaluation fails structurally;
4. revocation `execute` remains distinct from a later credential-expiry `abstain`;
5. outer execution, abstention, and terminal-abstention finals satisfy the schema.

## Privacy boundary

Artifacts contain only:

- stable pseudonymous IDs;
- immutable identity and issuer revisions;
- exact credential, policy, event, ledger, and corpus references;
- declared effects and reasons;
- explicit recorded, effective, evaluation, and completion times;
- separate revocation, credential, witness, adjudication, and terminal outcomes.

They do not require legal names, contact details, private keys, account identifiers, demographic traits, or reputation scores.

## Trust boundary

Verification does not prove:

- legal or real-world issuer or adjudicator identity;
- cryptographic authorship;
- possession of a private key;
- trusted external time;
- issuer trustworthiness or legal authority;
- completeness beyond the exact frozen ledger;
- absence of undisclosed events;
- global ledger uniqueness or public availability;
- adjudicator competence, independence, honesty, or correctness;
- adjudication or witness correctness;
- majority support, quorum, consensus, confidence, or reputation;
- extraction, analyzer, model, or content accuracy;
- an aggregate CTRT score.

## Intentionally deferred

This layer does not add:

- revocation-ledger checkpoints;
- named witnesses over ledger checkpoints;
- checkpoint-witness conflict adjudication;
- credentials for those future adjudicators;
- signatures, keys, identity providers, external timestamp authorities, or live transparency services;
- real datasets, models, APIs, frontend, or deployment.

The bounded successor is a checkpoint over the exact frozen `1.11.0` revocation ledger without modifying any prior artifact.

## Validation commands

```text
python -m ruff check src tests
python -m mypy
python -m pytest -q
```

No workflow, lint, type-check, or test exception is required by this layer.
