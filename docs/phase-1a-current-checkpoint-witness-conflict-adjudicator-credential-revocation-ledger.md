# Phase 1A: Current checkpoint-witness conflict-adjudicator credential revocation ledger

## Bounded question

> According to the exact accepted revocation policy and exact frozen issuer-authored event ledger, what was the effective status of the exact `1.20.0` credential at the declared evaluation time?

This layer answers only that question.

It does not reevaluate credential issuance, witness agreement, fork evidence, dissent, the selected checkpoint head, adjudication rationale, or external truth.

## Preserved predecessor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-bound@1.20.0
sha256:8cba471df7daa5664a87822fb8fad5a68b10b19422129ee266224f153ede5f20
```

The predecessor preserves:

```text
conflicting witness outcome = abstain
resolution status           = resolved
adjudication outcome        = execute
credential outcome          = execute
```

The credential, issuer registry, credential policy, witness observations, fork evidence, dissent, selected head, rationale, adjudication record, and every lower artifact remain immutable.

## Fixed revocation graph

### Revocation policy

```text
policy.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation@0.1.0
sha256:04430a4444d931e9e7e1793c3d3e05bbb9f18912d0e5daa15224ea1c261181a8
```

The accepted policy requires:

```text
permitted effects               = active, suspended, revoked
attestation issuer match        = required
monotonic effective time        = required
linear supersession             = required
abstain on suspended or revoked = true
```

### Future-effective event

```text
adjudicator-credential-revocation-event:event.synthetic.current-checkpoint-witness-conflict-adjudicator.suspension.v0.1.0
sha256:86fe5a56df406791385c432080c36cdc84620686a359d7edfd155ed41d3ec720
```

The event binds:

```text
credential = adjudicator-credential:credential.synthetic.current-checkpoint-witness-conflict-adjudicator.v0.1.0
adjudicator = adjudicator.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
issuer = issuer.synthetic.current-checkpoint-witness-conflict-governance
issuer revision = synthetic-current-checkpoint-witness-conflict-governance@0.1.0
effect = suspended
recorded_at = 2026-08-03T19:58:13Z
effective_at = 2027-01-01T00:00:00Z
```

Recording the event does not apply it early.

### Frozen ledger

```text
ledger.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocations@0.1.0
sha256:38345155c8550fa4d5bdb16b786039c5aac6904071862ec09a770e09f25d7960
```

The ledger binds the exact `1.20.0` credential corpus, accepted issuer registry, accepted revocation policy, and ordered event references.

### Successor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.21.0
sha256:b6a3065ffb517dda9fb498404021371f7d5b320af144842c3f7d2453c99ace1e
```

The compact successor contains only:

- exact `1.20.0` predecessor reference;
- unchanged ordered content IDs;
- exact revocation policy reference;
- exact frozen ledger reference;
- successor timestamp.

It does not duplicate credential, disagreement, adjudication, or inherited evidence.

## Manifest-last publication

Publication order is:

1. accepted revocation policy;
2. immutable issuer-authored status events;
3. frozen ordered ledger;
4. compact `1.21.0` successor manifest;
5. exact-hash reread of the complete graph.

Required chronology is:

```text
policy created <= event recorded <= ledger frozen <= successor published <= evaluated_at
```

Event effective time is evaluated independently from event recording time.

## Contract adapter

```text
src/ctrt/current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger.py
```

Primary type:

```text
RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
```

Public operations:

```text
load_current_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence
validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger
persist_current_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus
```

The adapter reuses the provider-neutral adjudicator-credential revocation grammar. It adds only exact `1.20.0` predecessor binding, context-specific compact parsing, publication chronology, and manifest-last storage entry points.

## Revocation-gated runner

```text
src/ctrt/revocation_gated_current_checkpoint_witness_conflict_runner.py
```

`RevocationGatedCurrentCheckpointWitnessConflictExperimentRunner` performs:

1. exact frozen-plan, successor, predecessor, policy, ledger, run identity, and chronology preflight;
2. storage-backed loading of the `1.21.0` revocation graph and preserved `1.20.0` credential evidence;
3. independent as-of revocation validation;
4. revocation-decision persistence before any credential execution;
5. terminal abstention when revocation status is suspended or revoked;
6. exact plan narrowing from `1.21.0` to `1.20.0` only after revocation execution;
7. unchanged PR #42 invocation under the same experiment run ID;
8. outer final persistence;
9. complete storage-backed reread of successor, predecessor, policy, ledger, events, credential authorities, adjudication, decision, and optional PR #42 final.

The outer argument names explicitly distinguish the new conflict-adjudicator revocation scope from lower `current_revocation_*` evidence already carried by PR #42.

## Scope transition

```text
1.21.0 plan → new conflict-adjudicator revocation decision and outer finalization
1.20.0 plan → unchanged PR #42 conflict-adjudicator credential lifecycle
1.19.0 plan → unchanged conflict and adjudication lifecycle
1.18.0 plan → unchanged canonical current named-witness lifecycle
1.17.0 plan → unchanged current checkpoint lifecycle
1.16.0 plan → unchanged lower current credential-revocation lifecycle
1.15.0 plan → unchanged lower conflict-adjudicator credential lifecycle
1.14.0 plan → unchanged lower conflict and adjudication lifecycle
```

Only the corpus reference and identical ordered content IDs narrow. Experiment identity, version, execution parameters, and inherited evidence remain unchanged.

## Independent outcomes

The final record preserves separately:

```text
current_conflict_adjudicator_revocation_outcome
current_conflict_adjudicator_credential_outcome
conflicting_witness_outcome
current_resolution_status
current_conflict_adjudication_outcome
resolved_current_witness_outcome
current_revocation_outcome
current_credential_outcome
lower_checkpoint_witness_outcome
lower_resolution_status
lower_conflict_adjudication_outcome
lower_predecessor_witness_outcome
inherited_revocation_outcome
inherited_credential_outcome
inherited_checkpoint_witness_outcome
inherited_resolution_status
inherited_adjudication_outcome
terminal_outcome
```

A later result never rewrites an earlier evidentiary or authority claim.

## Outcome matrix

### Before the future suspension boundary

```text
new revocation outcome              = execute
new credential outcome              = execute
conflicting witness                 = abstain
current resolution                  = resolved
current conflict adjudication       = execute
canonical current witnesses         = execute
lower current revocation            = execute
lower current credential            = execute
lower checkpoint witness            = abstain
lower resolution                    = resolved
lower conflict adjudication         = execute
lower predecessor witness           = execute
inherited revocation                = execute
inherited credential                = execute
inherited checkpoint witness        = execute
inherited resolution                = not_required
inherited adjudication              = execute
terminal outcome                    = execute
```

### At or after the future suspension boundary

```text
new revocation outcome              = abstain
all PR #42 outcomes                 = null
terminal outcome                    = abstain
PR #42                              = not invoked
```

The revocation decision and immutable history remain stored.

### New revocation executes; lower suspension later applies

```text
new revocation outcome              = execute
new credential outcome              = execute
conflicting witness                 = abstain
current resolution                  = resolved
current conflict adjudication       = execute
canonical current witnesses         = execute
lower current revocation            = abstain
all later outcomes                  = null
terminal outcome                    = abstain
```

The earlier revocation, credential, and adjudication executions remain visible and unchanged.

## Run-specific artifacts

Revocation decision:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-decision
```

Revocation abstention:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-abstention
```

Successful completion:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-completion
```

Revocation execution followed by downstream abstention:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-terminal-abstention
```

## Structural failures

The boundary fails closed for:

- non-frozen plan;
- successor or predecessor drift;
- content-order drift;
- policy or ledger drift;
- credential, adjudicator, issuer, or issuer-revision mismatch;
- event reference, event order, or event payload drift;
- non-monotonic effective time;
- non-linear supersession;
- event recording after ledger freeze;
- evaluation before graph publication;
- run-identity mismatch;
- stored artifact or canonical serialization drift.

A valid effective `suspended` or `revoked` state is a governed abstention rather than structural failure.

## Test contract

Contract and storage tests prove:

- exact canonical graph hashes and closed schemas;
- exact immutable `1.20.0` predecessor binding;
- active status before the future event boundary;
- suspended abstention at the exact effective boundary;
- base credential state remains immutable;
- issuer and content-order drift fail structurally;
- event recording after ledger freeze fails structurally;
- deterministic manifest-last reconstruction;
- unsupported confidence rejection.

Stored lifecycle tests use the real PR #30 through PR #42 evidence chain and prove:

1. active revocation status delegates exact PR #42;
2. the same experiment run ID crosses the `1.21.0 → 1.20.0` boundary;
3. effective suspension creates no PR #42 credential decision or final;
4. the new revocation outcome remains independent from later lower revocation abstention;
5. invalid outer chronology fails before delegation;
6. execution and abstention satisfy one closed final schema;
7. every public contract and runner symbol remains importable.

## Trust boundary

This layer does not establish ledger completeness, absence of undisclosed events, trusted external time, cryptographic authorship, signatures, private-key possession, legal or real-world identity, issuer or adjudicator independence, competence, honesty, correctness, adjudication correctness, selected-checkpoint truth, public availability, majority support, quorum, consensus, confidence, reputation, analytical accuracy, deployment, or an aggregate CTRT score.

## Intentionally deferred

The next bounded layer may publish an immutable checkpoint over this exact `1.21.0` revocation ledger.

That layer must preserve the complete `1.21.0` graph and every `1.20.0` credential and `1.19.0` disagreement and adjudication artifact unchanged.

## Reviewer checklist

1. Does `1.21.0` bind the exact immutable `1.20.0` predecessor?
2. Are policy, event, ledger, credential, adjudicator, and issuer references exact?
3. Is recording time distinct from effective time?
4. Does the future event remain visible but unapplied before its boundary?
5. Is the revocation decision persisted before PR #42 execution?
6. Does revocation abstention prevent every PR #42 runtime artifact?
7. Does execution narrow only to exact `1.20.0` under the same run ID?
8. Are new revocation and every delegated outcome preserved independently?
9. Are ledger checkpointing and witness governance explicitly deferred?