# Phase 1A: Current checkpoint-witness conflict-adjudicator credential attestation

## Bounded question

> Was the exact adjudicator that issued the preserved `1.19.0` resolution authorized by an accepted credential for the exact identity revision and `witness_conflict_adjudicator` role at evaluation time?

This layer answers only that question.

It does not reevaluate witness agreement, fork evidence, dissent, the selected checkpoint head, adjudication rationale, adjudication correctness, or external truth.

## Preserved predecessor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound-witness-conflict-adjudication-bound@1.19.0
sha256:ec430190b7e75d0f0e5e7a207a9a786edf24c090046098d2e7699b294876e784
```

The predecessor remains:

```text
conflicting witness outcome = abstain
resolution status           = resolved
adjudication outcome        = execute
```

The following remain immutable:

- alpha and beta matching observations;
- gamma's conflicting observation;
- the original witness abstention;
- exact fork evidence;
- preserved dissent;
- accepted adjudicator registry and identity revision;
- accepted adjudication policy;
- selected exact `1.17.0` checkpoint head;
- rationale and decision time;
- every lower and inherited artifact.

## Fixed credential graph

### Issuer registry

```text
registry.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-issuers@0.1.0
sha256:1c13ed78af7964464be460350c06ce32097e2e58c718c0f2b6a2d4fff6296fe8
```

Issuer:

```text
issuer.synthetic.current-checkpoint-witness-conflict-governance
synthetic-current-checkpoint-witness-conflict-governance@0.1.0
```

Accepted credential type:

```text
ctrt.current-checkpoint-witness-conflict-adjudicator-role
```

### Credential policy

```text
policy.synthetic-current-checkpoint-witness-conflict-adjudicator-credentials@0.1.0
sha256:ef4953a1c33f07e4e31aab2b5a0f7784c99354b147286a9c45bdd24ecd899526
```

The policy binds the exact `1.19.0` conflict-adjudicator registry and requires:

```text
exact role match             = true
abstain on not-yet-valid     = true
abstain on expired           = true
abstain on suspended         = true
abstain on revoked           = true
```

### Credential

```text
adjudicator-credential:credential.synthetic.current-checkpoint-witness-conflict-adjudicator.v0.1.0
sha256:6c538f6ac902906ebbea7e59155e183fdaf8dd0ec37eb2848d1bd7f07433efa6
```

Exact subject:

```text
adjudicator_id = adjudicator.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
identity_revision = synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
role = witness_conflict_adjudicator
```

Validity:

```text
2026-08-03T19:58:09Z <= evaluated_at < 2027-08-03T19:58:09Z
```

### Successor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-bound@1.20.0
sha256:8cba471df7daa5664a87822fb8fad5a68b10b19422129ee266224f153ede5f20
```

The compact successor contains only:

- exact `1.19.0` predecessor reference;
- unchanged ordered content IDs;
- exact issuer registry reference;
- exact credential policy reference;
- exact adjudicator ID and identity revision;
- exact credential reference;
- successor timestamp.

It does not duplicate inherited disagreement or adjudication evidence.

## Manifest-last publication

Publication order is:

1. accepted credential issuer registry;
2. accepted credential policy;
3. immutable credential;
4. compact `1.20.0` successor manifest;
5. exact-hash reread of the successor, predecessor, registry, policy, credential, and adjudication record.

The manifest is never published before its dependencies.

## Contract adapter

```text
src/ctrt/current_checkpoint_witness_conflict_adjudicator_credential.py
```

Primary type:

```text
CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot
```

Public operations:

```text
load_current_checkpoint_witness_conflict_credential_evidence
validate_current_checkpoint_witness_conflict_credentials
persist_current_checkpoint_witness_conflict_credential_corpus
```

The adapter reuses the established provider-neutral adjudicator-credential grammar. It adds only:

- exact `1.19.0` predecessor binding;
- context-specific compact manifest parsing;
- exact content-order preservation;
- successor chronology;
- context-specific manifest-last storage entry points.

## Credential-gated runner

```text
src/ctrt/credentialed_current_checkpoint_witness_conflict_runner.py
```

`CredentialedCurrentCheckpointWitnessConflictExperimentRunner` performs:

1. exact frozen-plan, successor, predecessor, adjudicator registry, issuer registry, policy, credential population, adjudication record, run identity, and chronology preflight;
2. storage-backed loading of the complete `1.20.0` graph;
3. independent credential validation;
4. credential-decision persistence before predecessor execution;
5. terminal abstention when the credential outcome is `abstain`;
6. exact plan narrowing from `1.20.0` to `1.19.0` only after credential execution;
7. unchanged PR #41 invocation under the same experiment run ID;
8. outer final persistence;
9. complete storage-backed reread of the successor, predecessor, authorities, credential, adjudication, decision, and optional PR #41 final.

## Scope transition

```text
1.20.0 plan → current conflict-adjudicator credential decision and outer finalization
1.19.0 plan → unchanged PR #41 conflict/adjudication lifecycle
1.18.0 plan → unchanged canonical current named-witness lifecycle
1.17.0 plan → unchanged current checkpoint lifecycle
1.16.0 plan → unchanged current credential-revocation lifecycle
1.15.0 plan → unchanged lower conflict-adjudicator credential lifecycle
1.14.0 plan → unchanged lower conflict/adjudication lifecycle
1.13.0 plan → unchanged lower named-witness lifecycle
1.12.0 plan → unchanged inherited checkpoint lifecycle
```

Only the corpus reference and identical ordered content IDs narrow. Experiment identity, version, execution parameters, and inherited evidence remain unchanged.

## Independent outcomes

The final record preserves separately:

```text
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

### Active credential; complete execution

```text
new conflict-adjudicator credential = execute
conflicting witness                 = abstain
current resolution                  = resolved
current conflict adjudication       = execute
canonical current witnesses         = execute
current revocation                  = execute
current credential                  = execute
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

### Expired or otherwise inactive new credential

```text
new conflict-adjudicator credential = abstain
all PR #41 outcomes                 = null
terminal outcome                    = abstain
PR #41                              = not invoked
```

The credential decision remains stored.

### New credential executes; later current suspension applies

```text
new conflict-adjudicator credential = execute
conflicting witness                 = abstain
current resolution                  = resolved
current conflict adjudication       = execute
canonical current witnesses         = execute
current revocation                  = abstain
all later outcomes                  = null
terminal outcome                    = abstain
```

The earlier credential and adjudication executions remain visible and unchanged.

## Run-specific artifacts

Credential decision:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-decision
```

Credential abstention:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-abstention
```

Successful completion:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-completion
```

Credential execution followed by downstream abstention:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-terminal-abstention
```

## Structural failures

The boundary fails closed for:

- non-frozen plan;
- successor or predecessor reference drift;
- content-order drift;
- conflict-adjudicator registry drift;
- issuer registry drift;
- credential policy drift;
- credential population or ordering drift;
- adjudicator ID or identity-revision substitution;
- subject-reference mismatch;
- credential type or role mismatch;
- unknown, inactive, or wrong-revision issuer;
- adjudication-record mismatch;
- invalid chronology;
- run-identity mismatch;
- stored artifact or canonical serialization drift.

Not-yet-valid, expired, suspended, and revoked credentials are governed abstentions rather than structural failures when their evidence is otherwise valid.

## Test contract

Contract and storage tests prove:

- exact graph hashes and closed schemas;
- exact `1.19.0` predecessor binding;
- exact adjudicator, identity revision, subject, issuer, type, and role binding;
- active execution;
- not-yet-valid and half-open expiration abstention;
- suspended credential abstention without adjudication rewriting;
- identity substitution and predecessor drift failure;
- deterministic manifest-last reconstruction;
- unsupported confidence rejection.

Stored lifecycle tests use the real PR #30 through PR #41 evidence chain and prove:

1. active credential delegates exact PR #41;
2. the same experiment run ID crosses the `1.20.0 → 1.19.0` boundary;
3. expired credential creates no PR #41 final;
4. active credential remains independent from a later current revocation abstention;
5. invalid outer chronology fails before delegation;
6. execution and abstention satisfy one closed final schema;
7. every public contract and runner symbol remains importable.

## Trust boundary

This layer does not establish:

- append-only credential non-revocation;
- legal or real-world adjudicator or issuer identity;
- cryptographic authorship, signatures, or private-key possession;
- trusted external time;
- issuer, adjudicator, or witness independence, competence, honesty, or correctness;
- adjudication correctness;
- correctness or external truth of the selected checkpoint;
- checkpoint or ledger completeness;
- absence of alternate histories or undisclosed credentials;
- global uniqueness or public availability;
- majority support, quorum, consensus, confidence, reputation, or trust;
- extraction, analyzer, model, dataset, or content accuracy;
- a frontend, deployment, or aggregate CTRT score.

## Intentionally deferred

The next bounded layer may publish an append-only revocation policy, ledger, and events for this exact `1.20.0` credential.

That layer must preserve the complete `1.20.0` credential graph and every `1.19.0` disagreement and adjudication artifact unchanged.

## Reviewer checklist

1. Does `1.20.0` bind the exact immutable `1.19.0` predecessor?
2. Is the policy bound to the exact accepted adjudicator and issuer registries?
3. Is the credential bound to the exact adjudicator ID, identity revision, subject, type, issuer, and role?
4. Are temporal and status abstentions fail-closed without rewriting adjudication evidence?
5. Is the credential decision persisted before PR #41 execution?
6. Does credential abstention prevent every PR #41 artifact?
7. Does credential execution narrow only to exact `1.19.0` under the same run ID?
8. Are the new credential and every delegated outcome preserved independently?
9. Is later credential revocation explicitly deferred to an append-only successor layer?
