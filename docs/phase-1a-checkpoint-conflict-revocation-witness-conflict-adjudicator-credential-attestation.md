# Phase 1A: Checkpoint-conflict revocation witness conflict-adjudicator credential attestation

## Purpose

This layer binds the exact adjudication authority introduced in ADR-0034 to immutable issuer credentials before that authority may affect execution.

It answers one bounded question:

> Was the exact pseudonymous identity revision authorized for the exact `witness_conflict_adjudicator` role at the declared time?

It does not reconsider the witness evidence or the adjudication decision.

## Position in the governance chain

```text
1.7.0 checkpoint-bound revocation corpus
  -> 1.8.0 named-witness corpus
  -> 1.9.0 witness-conflict adjudication corpus
  -> 1.10.0 conflict-adjudicator credential corpus
```

The execution scopes are:

```text
1.10.0 plan  -> credential validation and outer finalization
1.9.0 plan   -> unchanged PR #31 adjudication lifecycle
1.8.0 receipt -> preserved original witness outcome and attestations
1.7.0 plan/receipt -> lower checkpoint, revocation, and downstream lifecycle
```

Every transition narrows only the corpus reference. Experiment identity, version, content order, candidate population, analyzer population, execution windows, and earlier evidence remain unchanged.

## Fixed credential identity

```text
adjudicator_id = adjudicator.synthetic.checkpoint-conflict-revocation-checkpoint-witness-conflict
identity_revision = synthetic-checkpoint-conflict-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
role = witness_conflict_adjudicator
credential_type = ctrt.checkpoint-conflict-revocation-witness-conflict-adjudicator-role
```

The exact subject reference is:

```text
witness-conflict-adjudicator:adjudicator.synthetic.checkpoint-conflict-revocation-checkpoint-witness-conflict@synthetic-checkpoint-conflict-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
```

## Fixed issuer authority

Issuer registry:

```text
registry.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-issuers@0.1.0
sha256:abf4080842b6e807df2ef84f9b5871fd3d0624e89415d14cabcff11aead41057
```

Issuer record:

```text
issuer_id = issuer.synthetic.checkpoint-conflict-revocation-witness-conflict-governance
issuer_revision = synthetic-checkpoint-conflict-revocation-witness-conflict-governance@0.1.0
active = true
```

Credential policy:

```text
policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credentials@0.1.0
sha256:0ca87c6ecf3e073268bb163bcfbf9915c951da3acdf158d01df8459250ce7724
```

The policy requires:

- the exact issuer registry;
- the exact ADR-0034 adjudicator registry;
- the exact credential type;
- exact role matching;
- abstention when not yet valid, expired, suspended, or revoked.

Credential attestation:

```text
adjudicator-credential:credential.synthetic.checkpoint-conflict-revocation-witness-conflict.v0.1.0
sha256:a206414a2a1e98f510326e8a0cf6ecae2f35a58740f5f50b936382123549d318
```

## Chronology

```text
19:53:30Z  witness evaluation
19:54:05Z  issuer registry created
19:54:15Z  credential policy created
19:54:25Z  credential issued
19:54:30Z  credential validity begins
19:55:00Z  credential evaluated
19:55:30Z  adjudication evaluated
19:56:00Z  adjudication lifecycle completed
19:56:30Z  outer credential lifecycle completed
```

The credential validity interval is:

```text
2026-08-03T19:54:30Z <= evaluated_at < 2027-08-03T19:54:30Z
```

Credential evaluation after adjudication is a structural failure, not an abstention.

## Append-only corpus evolution

Predecessor:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound@1.9.0
sha256:080d41cf305eaf28c120fb20359c4d01392409351af2bae350c8400cdb9b5d43
```

Successor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-bound@1.10.0
sha256:1ef073d0b8af20d4ea511f7828a0f90d753d532a1c46b3d6bd36e8a90df21b0f
```

The `1.10.0` manifest preserves and binds:

- the exact `1.9.0` predecessor;
- the exact `1.8.0` witness predecessor reference;
- the exact `1.7.0` checkpoint predecessor reference;
- the conflict-adjudicator registry;
- the adjudication policy;
- the adjudication record;
- the witness registry and policy;
- the ordered witness attestations;
- the issuer registry;
- the credential policy;
- the ordered credential population;
- the ordered content population.

The context adapter compares the preserved authority tuple against the actual immutable `1.9.0` object. It does not infer predecessor equality from similar IDs or reconstruct the predecessor from the `1.10.0` payload alone.

## Publication order

Publication is manifest-last:

1. append the issuer registry;
2. append the credential policy;
3. append the credential attestation population;
4. append the compact `1.10.0` manifest;
5. reread every artifact by exact hash.

A failure before step 4 leaves no successor manifest claiming a complete graph.

## Contract adapter

The public contract module is:

```text
src/ctrt/checkpoint_conflict_witness_adjudicator_credential.py
```

It exposes:

```text
CheckpointConflictWitnessAdjudicatorCredentialError
CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
CredentialDecisionReport
StoredCredentialEvidence
load_checkpoint_conflict_witness_adjudicator_credential_evidence
validate_checkpoint_conflict_witness_adjudicator_credentials
persist_checkpoint_conflict_witness_adjudicator_credential_corpus
```

The adapter reuses the existing generic adjudicator credential engine. It adds only the context-specific predecessor and authority-preservation checks required by the `1.10.0` graph.

## Credential-gated runner

The runner is:

```text
src/ctrt/credentialed_checkpoint_conflict_witness_adjudication_runner.py
```

The public runner is:

```text
CredentialedCheckpointConflictWitnessAdjudicationExperimentRunner
```

It performs:

1. exact frozen-plan and content-order preflight;
2. exact `1.10.0 -> 1.9.0` predecessor verification;
3. exact authority-reference verification;
4. witness, credential, adjudication, and completion chronology verification;
5. storage-backed loading of the credential graph;
6. credential validation at the declared time;
7. run-specific credential-decision persistence and reread;
8. terminal credential abstention or delegation to the unchanged PR #31 runner;
9. final-manifest persistence;
10. storage-backed final verification.

## Run-specific artifacts

Credential decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-decision
```

Credential abstention final:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-abstention
```

Credential-authorized completion:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-completion
```

Credential authorization followed by a later abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-terminal-abstention
```

## State semantics

### Active and valid

```text
credential_outcome = execute
```

The runner derives an exact `1.9.0` plan and invokes PR #31 unchanged.

For the canonical `not_required` adjudication graph:

```text
credential_outcome         = execute
checkpoint_witness_outcome = execute
resolution_status          = not_required
adjudication_outcome       = execute
terminal_outcome           = execute
```

### Not yet valid

```text
credential_outcome = abstain
```

No PR #31 adjudication decision or final is created.

### Expired

```text
credential_outcome = abstain
```

No PR #31 adjudication decision or final is created. The immutable adjudication record remains present as evidence, but it is not executed by this run.

### Suspended or revoked

```text
credential_outcome = abstain
```

These are governed abstentions when the graph is otherwise structurally coherent.

### Structural drift

No credential outcome is produced for:

- identity-revision drift;
- issuer-revision drift;
- role mismatch;
- credential-type mismatch;
- subject-reference mismatch;
- predecessor substitution;
- authority-reference substitution;
- credential-population drift;
- impossible chronology;
- storage or serialization failure.

## Evidence preservation

The credential layer never rewrites:

- the original witness outcome;
- matching or conflicting witness observations;
- fork evidence;
- dissent;
- adjudication rationale;
- selected checkpoint head;
- adjudication resolution status;
- adjudication outcome;
- lower checkpoint, revocation, reviewer, or analyzer outcomes.

A resolved conflict may still carry:

```text
checkpoint_witness_outcome = abstain
adjudication_outcome       = execute
credential_outcome         = execute
```

All three are valid because they answer different questions.

## Final schema

The outer final schema is:

```text
schemas/credentialed-checkpoint-conflict-witness-adjudication-final.schema.json
```

It enforces:

- credential abstention requires null adjudication outcomes and final reference;
- credential abstention requires terminal abstention;
- credential execution requires delegated adjudication evidence;
- all artifact references carry exact hashes;
- unknown fields are rejected.

## Test coverage

Contract tests prove:

- issuer, policy, credential, and `1.10.0` schemas;
- deterministic canonical `1.10.0` hash;
- exact `1.9.0` predecessor binding;
- exact preserved authority graph;
- active credential execution eligibility;
- expiry abstention without altering the adjudication reference;
- identity-revision drift as structural failure;
- storage reconstruction is exact and idempotent;
- unsupported confidence fields are rejected.

Lifecycle tests prove:

1. an active credential delegates the exact PR #31 lifecycle;
2. an expired credential persists its own decision and final but creates no PR #31 decision artifact;
3. a not-yet-valid credential terminates before PR #31 execution;
4. credential evaluation after adjudication is structural preflight failure.

The final schema is validated against both execution and abstention artifacts.

## Privacy and trust boundary

Stored artifacts contain:

- stable pseudonymous adjudicator and issuer IDs;
- immutable identity and issuer revisions;
- declared roles and credential types;
- exact artifact references and hashes;
- issuance and validity times;
- declared credential status;
- credential, witness, and adjudication outcomes.

They do not require names, addresses, private contact data, government identifiers, biographies, or private keys.

## Non-claims

This layer does not prove:

- legal identity of the adjudicator or issuer;
- cryptographic authorship;
- possession of a private key;
- trusted external time;
- issuer trustworthiness or legal authority;
- adjudicator competence, independence, honesty, or correctness;
- adjudication correctness;
- witness correctness or independence;
- credential non-revocation beyond the declared attestation state;
- public availability or global checkpoint uniqueness;
- majority support, quorum, consensus, confidence, or reputation;
- real-world completeness;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred successor

The next bounded layer is an append-only, time-relative revocation ledger for this exact credential authority.

It must not modify the credential, issuer record, adjudication, original witness abstention, fork evidence, dissent, rationale, or selected checkpoint head.
