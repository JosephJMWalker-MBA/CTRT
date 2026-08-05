# Phase 1A: Current revocation-checkpoint witness-conflict adjudicator credential attestation

## Bounded question

> Did an accepted issuer attest the exact adjudicator identity revision for the exact `witness_conflict_adjudicator` role at the evaluation time?

This layer does not reconsider the witness conflict or the adjudicator's selected head. It credentials the exact adjudicator identity preserved by `1.24.0` and either delegates unchanged to that lifecycle or stops before it.

## Exact ancestry

```text
1.25.0 credential-bound successor
  -> exact 1.24.0 current revocation-checkpoint witness conflict adjudication
  -> exact 1.23.0 named-witness population
  -> exact 1.22.0 revocation-ledger checkpoint
  -> exact 1.21.0 revocation ledger
  -> exact 1.20.0 prior conflict-adjudicator credential
  -> exact 1.19.0 prior conflict adjudication
```

Only the corpus reference narrows between adjacent plans. The ordered content IDs remain:

```text
content-001
content-002
content-003
```

## Fixed graph

### Exact predecessor

```text
artifact_id: corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound
version:     1.24.0
hash:        sha256:a98bcdc6c6c146de7d688ea708285f8d4b82bd93a8486ac5e37e76bf3acaa5fb
```

### Credential issuer registry

```text
artifact_id: registry.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-issuers
version:     0.1.0
hash:        sha256:374aa9e74626fbad3d713c7314b52ba3216c5f83967d42b5cab8850f25e41c9e
```

### Credential policy

```text
artifact_id: policy.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credentials
version:     0.1.0
hash:        sha256:ca068064ee98571231ec8bf56ab35f54f35fedeacd2536c49ef02f48f5882f98
```

### Credential attestation

```text
artifact_id: adjudicator-credential:credential.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator.v0.1.0
hash:        sha256:e80e03f9112abe7ff8e482e532a6eea5ac636cefe147794e554200a428732092
```

### Successor corpus

```text
artifact_id: corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-bound
version:     1.25.0
hash:        sha256:b43a185d7b21879b3a234fe84233f324ae66a07a034b9ae3b7cd3577c226dca0
```

## Exact subject

```text
adjudicator_id:
  adjudicator.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork

identity_revision:
  synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0

role:
  witness_conflict_adjudicator
```

The credential subject reference derives from the exact pair:

```text
witness-conflict-adjudicator:<adjudicator_id>@<identity_revision>
```

## Issuer and credential type

```text
issuer_id:
  issuer.synthetic.current-revocation-checkpoint-witness-conflict-governance

issuer_revision:
  synthetic-current-revocation-checkpoint-witness-conflict-governance@0.1.0

credential_type:
  ctrt.current-revocation-checkpoint-witness-conflict-adjudicator-role
```

The issuer registry is accepted and the issuer is active. The issuer explicitly lists the credential type.

## Chronology

```text
1.24.0 successor published       2026-08-03T19:58:36Z
issuer registry published        2026-08-03T19:58:37Z
credential policy published      2026-08-03T19:58:38Z
credential issued                2026-08-03T19:58:39Z
credential valid from            2026-08-03T19:58:40Z
1.25.0 successor published       2026-08-03T19:58:41Z
credential evaluated             2026-08-03T19:58:42Z
1.24.0 conflicting witnesses     2026-08-03T19:58:43Z or later
```

The validity interval is half-open:

```text
valid_from <= evaluated_at < valid_until
```

The exact active credential uses:

```text
valid_until = 2027-08-03T19:58:40Z
```

## Contract module

```text
src/ctrt/current_revocation_checkpoint_witness_conflict_adjudicator_credential.py
```

Public API:

```text
CredentialAttestationSnapshot
CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot
CredentialDecisionReport
CredentialError
CredentialPolicySnapshot
StoredCredentialEvidence
load_current_revocation_checkpoint_witness_conflict_credential_evidence
persist_current_revocation_checkpoint_witness_conflict_credential_corpus
validate_current_revocation_checkpoint_witness_conflict_credentials
```

The adapter reuses the generic adjudicator credential machinery while binding the exact `1.24.0` predecessor and new prefix.

## Runner module

```text
src/ctrt/credentialed_current_revocation_checkpoint_witness_conflict_runner.py
```

Execution order:

```text
preflight
  -> evidence loading
  -> credential validation
  -> credential decision persistence
  -> credential abstention or exact 1.24.0 plan derivation
  -> unchanged PR #46 execution
  -> final persistence
  -> verification reread
```

Runner stages:

```text
preflight
evidence-loading
credential-validation
credential-decision-persistence
adjudication-execution
final-persistence
verification
```

## Plan scopes

### `1.25.0`

Owns:

- exact credential-bound corpus;
- issuer registry;
- credential policy;
- credential attestation;
- credential decision;
- outer finalization.

### `1.24.0`

Owns the unchanged current revocation-checkpoint witness conflict adjudication and every lower lifecycle.

The outer runner creates the exact predecessor plan only when the credential decision is `execute`:

```text
corpus_ref  = exact 1.24.0 reference
content_ids = unchanged ordered population
run_id      = unchanged
```

## Credential outcomes

### Execute

The credential decision executes only when:

- the plan is frozen and matches `1.25.0` exactly;
- the predecessor equals exact `1.24.0`;
- the adjudicator registry equals the exact `1.24.0` registry;
- issuer and policy references equal the manifest;
- the credential population equals the registry population in order;
- the attested identity revision equals the registry identity revision;
- the authorized role equals `witness_conflict_adjudicator` exactly;
- the credential type equals the policy credential type;
- the issuer revision matches and may issue the type;
- the issuer is active;
- the credential status is active;
- the evaluation time is within the half-open validity window.

### Abstain

Governed abstention reasons include:

```text
credential-issuer-inactive
credential-status:suspended
credential-status:revoked
credential-not-yet-valid
credential-expired
```

Credential abstention stores the credential decision and outer final, but creates no PR #46 runtime artifact.

## Final record

The final manifest preserves the new credential outcome separately from every PR #46 outcome:

```text
current_revocation_checkpoint_conflict_adjudicator_credential_outcome
conflicting_current_revocation_checkpoint_witness_outcome
current_revocation_checkpoint_resolution_status
current_revocation_checkpoint_conflict_adjudication_outcome
resolved_current_revocation_checkpoint_witness_outcome
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

No field implies that credential eligibility proves adjudication correctness.

## Storage order

The manifest-last persistence order is:

```text
accepted issuer registry
accepted credential policy
credential attestation
1.25.0 corpus manifest
```

At runtime:

```text
credential decision
optional PR #46 artifacts
outer final manifest
verification reread
```

## Tests

Contract tests cover:

- fixed hashes;
- closed schemas;
- exact `1.24.0` predecessor binding;
- active credential execution;
- not-yet-valid abstention;
- exact expiration boundary;
- suspended credential abstention;
- identity-revision substitution failure;
- predecessor drift failure;
- manifest-last deterministic reconstruction;
- unsupported-confidence rejection.

Lifecycle tests cover:

- active credential delegation to an exact real PR #46 receipt;
- same run ID and exact `1.24.0` plan narrowing;
- suspended credential stopping before PR #46;
- credential execution preserving a later revocation abstention;
- invalid chronology failing at preflight;
- one closed final schema for execution, credential abstention, and delegated abstention.

Public API tests lock both contract and runner exports.

## Structural failure versus governed abstention

Structural failures indicate that the evidence graph cannot be trusted as the declared graph. Examples include identity substitution, role substitution, reference drift, population drift, noncanonical storage, or chronology inversion.

Governed abstentions indicate that the graph is structurally valid but policy does not authorize execution at the evaluation time.

The two states remain distinct.

## Trust boundary

The layer does not prove legal identity, cryptographic authorship, signatures, private-key possession, trusted time, issuer or adjudicator independence, competence, honesty, correctness, correctness of the selected head, checkpoint completeness, absence of alternate histories, quorum, consensus, confidence, reputation, analytical accuracy, deployment, or an aggregate score.

## Next bounded layer

After this exact layer is merged, the next bounded layer may introduce an append-only revocation ledger for the `1.25.0` credential.

It must preserve every artifact and decision listed above unchanged.
