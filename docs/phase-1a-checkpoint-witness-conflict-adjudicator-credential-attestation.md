# Phase 1A: Checkpoint-witness conflict-adjudicator credential attestation

## Bounded question

> Did an accepted issuer issue a structurally valid, current credential for the exact pseudonymous adjudicator identity revision and `witness_conflict_adjudicator` role used by the immutable `1.14.0` conflict adjudication?

This layer answers only that question.

It does not reevaluate whether the witnesses agreed, whether the adjudication was correct, whether the selected checkpoint is externally true, or whether the new credential has later been revoked through an append-only revocation history.

## Preserved predecessor

The exact predecessor is:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-adjudication-bound@1.14.0
sha256:a2b4ff05a5e23bcdf0d54b721b4e3cd376788a65f7464b26dc543207d9cfb74e
```

`1.14.0` remains immutable and continues to report:

```text
checkpoint witness outcome = abstain
resolution status          = resolved
adjudication outcome       = execute
```

The gamma alternate observation, fork evidence, preserved dissent, selected declared checkpoint head, adjudicator identity revision, and adjudication rationale are inherited by exact reference rather than copied or rewritten.

## Fixed credential authority graph

### Accepted issuer registry

```text
registry.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-issuers@0.1.0
sha256:6d6f0690afa8d0d3817e5d64e15654487e469c00abb7e215be5f22e323f07a15
```

Issuer:

```text
issuer.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-governance
```

Issuer revision:

```text
synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-governance@0.1.0
```

Accepted credential type:

```text
ctrt.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-role
```

### Accepted credential policy

```text
policy.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credentials@0.1.0
sha256:b25e1aea19f4d5865fdce15a3f2739e7b45d4e028c1bbfd346d0a20cdfe66adf
```

The policy binds:

- the exact issuer registry;
- the exact `1.14.0` conflict-adjudicator registry;
- the exact credential type;
- exact role matching;
- fail-closed abstention for not-yet-valid, expired, suspended, or revoked status.

### Immutable credential

```text
adjudicator-credential:credential.synthetic.witness-conflict-adjudicator-checkpoint-fork.v0.1.0
sha256:e992110c0dadc3990406485d6b666977f68d74b78417b477ea255875fc3a7c0d
```

Subject:

```text
adjudicator.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
```

Identity revision:

```text
synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
```

Authorized role:

```text
witness_conflict_adjudicator
```

Validity interval:

```text
2026-08-03T19:57:33Z <= evaluated_at < 2027-08-03T19:57:33Z
```

### Credential-bound successor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-bound@1.15.0
sha256:feb13271bed910f480e5ae0af730e4b68ff8636a7172a3f6b4a0c3bd0d51b542
```

The compact successor contains only:

- exact `1.14.0` predecessor reference;
- exact issuer-registry reference;
- exact credential-policy reference;
- exact adjudicator ID and identity revision;
- exact credential-attestation reference;
- unchanged ordered content population;
- successor timestamp.

No inherited evidence is duplicated into the successor manifest.

## Publication order

The graph is published manifest-last:

1. issuer registry;
2. credential policy;
3. credential attestation;
4. compact `1.15.0` successor manifest;
5. exact-hash reread of the complete graph.

The manifest cannot become the canonical entry point until every dependency already exists in the append-only artifact store.

## Typed contract adapter

Implementation:

```text
src/ctrt/checkpoint_witness_conflict_adjudicator_credential.py
```

Primary snapshot:

```text
CredentialBoundCheckpointWitnessConflictCorpusSnapshot
```

Public contract surface:

```text
CredentialAttestationSnapshot
CredentialBoundCheckpointWitnessConflictCorpusSnapshot
CredentialDecisionReport
CredentialError
CredentialPolicySnapshot
StoredCredentialEvidence
load_checkpoint_witness_conflict_credential_evidence
validate_checkpoint_witness_conflict_credentials
persist_checkpoint_witness_conflict_credential_corpus
```

The adapter delegates credential semantics to the established provider-neutral adjudicator-credential validator. It adds only:

- exact `1.14.0` predecessor binding;
- the context-specific compact `1.15.0` manifest;
- context-specific load, validation, and manifest-last persistence entry points.

It does not duplicate role, identity, issuer, status, or temporal validation logic.

## Credential decision semantics

### Execute

Execution requires all of the following:

- frozen experiment plan exactly matches `1.15.0`;
- exact `1.14.0` predecessor reference and payload;
- accepted issuer registry;
- accepted policy bound to the issuer and adjudicator registries;
- exact adjudicator ID and identity revision;
- exact credential type;
- exact authorized role;
- exact subject reference;
- accepted issuer and issuer revision;
- active credential status;
- evaluation inside the half-open validity interval;
- credential population exactly matches manifest order.

Canonical outcome:

```text
credential outcome = execute
```

### Governed abstention

The credential decision abstains when structurally valid evidence reports a policy-defined non-executable state, including:

```text
credential-not-yet-valid
credential-expired
credential-status:suspended
credential-status:revoked
```

The decision and abstention reasons are persisted. The predecessor runner is not invoked.

### Structural failure

The layer raises a fail-closed structural error for incompatible evidence, including:

- unknown or substituted adjudicator ID;
- identity-revision drift;
- subject-reference drift;
- issuer or issuer-revision drift;
- unsupported credential type;
- missing exact role;
- policy or registry reference drift;
- credential reference or order drift;
- `1.14.0` predecessor drift;
- content-order drift;
- malformed timestamps or chronology;
- stored payload/hash mismatch.

Structural failure is not represented as an abstention because the graph itself cannot be interpreted under the accepted contract.

## Outer credential-gated runner

Implementation:

```text
src/ctrt/credentialed_checkpoint_witness_conflict_adjudication_runner.py
```

Runner:

```text
CredentialedCheckpointWitnessConflictExperimentRunner
```

The runner performs:

1. exact frozen-plan, successor, predecessor, issuer, policy, credential population, adjudicator, adjudication, run identity, and chronology preflight;
2. storage-backed loading of the complete `1.15.0` credential graph;
3. independent validation and persistence of the current credential decision;
4. terminal outer abstention when the credential decision abstains;
5. exact `1.15.0 -> 1.14.0` plan narrowing only after credential execution;
6. invocation of the unchanged PR #36 runner with the exact preserved `1.14.0` graph;
7. outer final persistence;
8. storage-backed reread of the successor, predecessor, registries, policy, credential, adjudication, current decision, and optional PR #36 final.

## Explicit plan scopes

```text
1.15.0 plan -> current conflict-adjudicator credential decision and outer finalization
1.14.0 plan -> unchanged PR #36 disagreement/adjudication lifecycle
1.13.0 plan -> unchanged PR #35 named-witness lifecycle
1.12.0 plan -> unchanged PR #34 checkpoint lifecycle
1.11.0 plan -> unchanged PR #33 revocation lifecycle
1.10.0 plan -> unchanged inherited credential lifecycle
1.9.0 plan  -> unchanged inherited adjudication lifecycle
```

Only the corpus reference and identical ordered content IDs are narrowed. Experiment identity, experiment version, execution parameters, and all inherited evidence remain unchanged.

## Independent outcome matrix

### Canonical current credential execution

```text
current credential                    = execute
current checkpoint witness            = abstain
current resolution status             = resolved
current conflict adjudication         = execute
1.13.0 predecessor witness            = execute
inherited revocation                  = execute
inherited credential                  = execute
inherited checkpoint witness          = execute
inherited resolution status           = not_required
inherited adjudication                = execute
terminal outcome                      = execute
```

### Expired current credential

```text
current credential                    = abstain
all predecessor and inherited outcomes = null
terminal outcome                      = abstain
```

The current credential decision remains stored. PR #36 is not invoked.

### Current credential executes; inherited suspension later applies

```text
current credential                    = execute
current checkpoint witness            = abstain
current resolution status             = resolved
current conflict adjudication         = execute
1.13.0 predecessor witness            = execute
inherited revocation                  = abstain
remaining inherited outcomes          = null
terminal outcome                      = abstain
```

The current credential authorization remains visible even when a later independent governance layer stops execution.

## Run-specific artifacts

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-decision
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-abstention
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-completion
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-terminal-abstention
```

The outer final record keeps current credential and all delegated outcomes in separate fields.

## Test map

Contract and storage tests prove:

- exact hashes for issuer registry, policy, credential, predecessor, and successor;
- exact closed successor and final schemas;
- exact `1.14.0` predecessor binding;
- exact adjudicator ID, identity revision, subject, type, issuer, and role binding;
- active credential execution;
- not-yet-valid abstention;
- half-open expiration abstention;
- suspended-state abstention without adjudication rewrite;
- substituted identity structural failure;
- predecessor drift rejection;
- unsupported confidence rejection;
- manifest-last persistence and deterministic reconstruction.

Stored lifecycle tests use the real PR #30-#36 evidence chain and prove:

1. active current credential delegates exact PR #36;
2. expired current credential abstains before PR #36;
3. active current credential remains separate from a later inherited revocation abstention;
4. current credential evaluation after the current witness evaluation fails at outer preflight;
5. every inherited receipt is bound to the exact outer experiment run ID;
6. execution, current credential abstention, and downstream terminal abstention satisfy one closed final schema.

## Trust boundary

This layer establishes only a deterministic relationship among supplied immutable artifacts under the accepted credential policy.

It does not establish:

- credential non-revocation through an append-only revocation history;
- legal or real-world adjudicator or issuer identity;
- cryptographic authorship, signatures, or private-key possession;
- trusted external time;
- issuer independence, competence, honesty, or authority outside the synthetic graph;
- adjudicator independence, competence, honesty, or correctness;
- witness independence, competence, honesty, or correctness;
- adjudication correctness;
- correctness or external truth of the selected checkpoint head;
- global checkpoint uniqueness or public availability;
- absence of undisclosed credentials, events, ledgers, or alternate chains;
- majority support, quorum, consensus, confidence, reputation, or trust;
- extraction, analyzer, model, dataset, or content accuracy;
- a frontend, deployment, or aggregate CTRT score.

## Bounded successor

The next governance layer may publish an append-only revocation policy, ledger, and events for this exact credential. That successor must preserve `1.15.0`, the current credential decision, the complete `1.14.0` disagreement and adjudication graph, fork evidence, dissent, and every inherited artifact unchanged.
