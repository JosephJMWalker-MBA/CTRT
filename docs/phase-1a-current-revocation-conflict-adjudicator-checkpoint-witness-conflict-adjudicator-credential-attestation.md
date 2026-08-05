# Phase 1A — Current revocation conflict-adjudicator checkpoint-witness conflict-adjudicator credential attestation

## Purpose

This layer places an issuer-bound credential gate around the exact `1.29.0` conflict adjudication introduced by PR #51.

It asks one bounded question:

> At the evaluation timestamp, does the exact accepted issuer-bound credential authorize the exact adjudicator identity revision for the exact `witness_conflict_adjudicator` role used by the immutable `1.29.0` adjudication?

It does not reevaluate the conflict, select a different checkpoint head, remove dissent, or alter any predecessor artifact.

## Exact predecessor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound@1.29.0
sha256:7f764303de2ed1d57856403bd900d0690ebf18c37b40a944e29e0e9b27a70cc4
```

The complete `1.29.0` graph remains immutable, including:

- alpha and beta matching observations;
- gamma's separately appended conflicting observation;
- the conflicting witness abstention;
- the accepted conflict-adjudicator registry and policy;
- the resolved adjudication;
- the selected exact `1.27.0` checkpoint head;
- fork evidence and preserved dissent;
- all delegated checkpoint, revocation, credential, witness, adjudication, and terminal outcomes.

## Exact credential graph

### Issuer registry

```text
artifact ID:
  registry.synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-issuers

version:
  0.1.0

hash:
  sha256:764b0e77ee7b1dc2bea93b896402002c5b81b6a785d05b5ba4aafa8ee05fda8c
```

### Credential policy

```text
artifact ID:
  policy.synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credentials

version:
  0.1.0

hash:
  sha256:a5074d6dab65673e899297bb3e1243dc013c88ba75d05845a1ad3b409c885a4a
```

### Credential attestation

```text
artifact ID:
  adjudicator-credential:credential.synthetic.current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator.v0.1.0

hash:
  sha256:26759637a9f3a4b8e8cc2996a071abdbb9f4cbccd7c0cf873344f7a48f4885b6
```

### Credential-bound successor

```text
corpus.synthetic-three-items.current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-bound@1.30.0
sha256:a9ece983cac8c81dee0bfd61df4cd396ea03eb1df339c0ef6cc43e0604b39209
```

## Exact subject and authority

```text
adjudicator ID:
  adjudicator.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork

identity revision:
  synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0

subject reference:
  witness-conflict-adjudicator:adjudicator.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork@synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0

required role:
  witness_conflict_adjudicator
```

The credential authorizes only this exact combination.

A different adjudicator ID, identity revision, subject reference, role, credential type, issuer ID, or issuer revision is not a weaker credential. It is a structurally different graph and fails closed.

## Chronology

```text
1.29.0 successor published  2026-08-03T19:59:08Z
issuer registry published   2026-08-03T19:59:09Z
credential policy published 2026-08-03T19:59:10Z
credential issued           2026-08-03T19:59:11Z
credential valid from       2026-08-03T19:59:12Z
1.30.0 successor published  2026-08-03T19:59:13Z
credential evaluated        2026-08-03T19:59:14Z or later
PR #51 conflict evaluation  after credential execution
PR #51 adjudication         after conflict evaluation
outer completion            after PR #51 completion or credential abstention
```

The credential validity interval is half-open:

```text
valid_from <= evaluated_at < valid_until
```

The exact upper boundary is:

```text
2027-08-03T19:59:12Z
```

Evaluation at that timestamp is expired and therefore abstains.

## Storage order

Static graph publication is dependency-first and manifest-last:

```text
issuer registry
  -> credential policy
  -> credential attestation
  -> `1.30.0` successor manifest
```

Runtime publication is decision-first and final-last:

```text
load and reverify exact `1.30.0` graph
  -> validate credential
  -> persist credential decision
  -> credential abstention or exact `1.29.0` plan derivation
  -> execute PR #51 unchanged
  -> persist outer final
  -> reread every referenced artifact
```

The exact experiment run ID and ordered content IDs are retained across plan narrowing.

Only the corpus reference changes from `1.30.0` to `1.29.0` after the credential outcome is `execute`.

## Outcome matrix

### Active credential within the validity interval

```text
credential outcome = execute
PR #51             = executed unchanged
```

The final record separately preserves:

- the credential outcome;
- the current conflicting witness outcome;
- the current resolution status;
- the current adjudication outcome;
- the resolved witness outcome;
- every one of the 23 PR #50 and inherited outcomes;
- the terminal outcome.

### Not-yet-valid credential

```text
credential outcome = abstain
reason             = credential-not-yet-valid
all PR #51 fields  = null
terminal outcome   = abstain
```

### Expired credential

```text
credential outcome = abstain
reason             = credential-expired
all PR #51 fields  = null
terminal outcome   = abstain
```

### Suspended or revoked credential

```text
credential outcome = abstain
all PR #51 fields  = null
terminal outcome   = abstain
```

The `1.29.0` adjudication record, selected head, fork evidence, and dissent remain unchanged and addressable.

### Later delegated abstention

```text
credential outcome     = execute
PR #51 adjudication    = execute
later delegated result = abstain
terminal outcome       = abstain
```

The later abstention does not rewrite credential authorization or any earlier outcome.

## Structural failure versus governed abstention

A governed abstention requires a structurally valid graph whose accepted policy explicitly maps the credential's time or status to `abstain`.

Structural failures include:

- wrong `1.29.0` predecessor;
- wrong ordered content population;
- missing or duplicate credential entries;
- issuer registry, credential policy, or credential substitution;
- adjudicator ID or identity-revision substitution;
- subject-reference, role, or credential-type drift;
- issuer ID or issuer-revision drift;
- adjudication substitution;
- chronology inversion;
- cross-run receipt substitution;
- noncanonical serialization;
- stored payload or hash drift;
- undeclared schema fields.

Structural failure raises a stage-specific experiment error and does not create a governed abstention artifact.

## Runner stages

```text
preflight
evidence-loading
credential-validation
credential-decision-persistence
adjudication-execution
final-persistence
verification
```

Each error preserves the stage and any completed content IDs reported by the unchanged delegated lifecycle.

## Public contract

The credential adapter exports:

```text
CredentialAttestationSnapshot
CredentialBoundCurrentRevocationConflictAdjudicatorCheckpointWitnessCorpusSnapshot
CredentialDecisionReport
CredentialError
CredentialPolicySnapshot
StoredCredentialEvidence
load_current_revocation_conflict_adjudicator_checkpoint_witness_credential_evidence
persist_current_revocation_conflict_adjudicator_checkpoint_witness_credential_corpus
validate_current_revocation_conflict_adjudicator_checkpoint_witness_credentials
```

The outer runner exports its exact verified-check tuple, experiment error, final manifest, runner, stage, status, and verified receipt.

Public API regression tests prevent accidental renaming or exposure drift.

## Schema boundaries

The `1.30.0` successor schema fixes:

- exact corpus ID and version;
- exact ordered content IDs;
- exact `1.29.0` predecessor reference;
- exact issuer registry reference;
- exact credential policy reference;
- exact adjudicator ID and identity revision;
- exact credential attestation reference;
- exact creation timestamp;
- no additional properties.

The final schema requires the credential outcome and all 27 PR #51 and inherited outcome fields separately, including explicit `null` values after credential abstention.

It rejects undeclared confidence, consensus, reputation, trust, or aggregate score fields.

## Trust boundary

This layer does not prove:

- the real-world identity of the issuer or adjudicator;
- cryptographic authorship;
- legal authority;
- independence, competence, honesty, or correctness;
- that the selected checkpoint head is objectively true;
- that the ledger is complete;
- that alternate histories do not exist;
- that timestamps come from a trusted external source;
- majority support, quorum, or consensus;
- confidence, reputation, or aggregate trust;
- CTRT analytical accuracy or deployment readiness.

It proves only that the exact stored credential graph satisfied its exact accepted deterministic policy at the evaluation timestamp and therefore either allowed or stopped the unchanged `1.29.0` lifecycle.

## Validation targets

The layer is complete only when:

1. Ruff passes without exceptions;
2. strict mypy passes without exceptions;
3. the complete inherited test suite passes;
4. fixed artifact hashes match the committed graph;
5. the closed schemas accept only the intended records;
6. manifest-last reconstruction is deterministic;
7. active credentials delegate the exact PR #51 plan;
8. expired credentials create no PR #51 runtime final;
9. later delegated abstentions remain independent;
10. the branch remains exactly based on the PR #51 merge commit.

## Deferred lifecycle evidence

The credential is immutable. Any later suspension or revocation history must be appended as a separate bounded graph rather than mutating this attestation.
