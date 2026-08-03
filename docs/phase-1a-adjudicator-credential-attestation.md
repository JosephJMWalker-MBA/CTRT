# Phase 1A: Adjudicator credential attestation

## Purpose

This phase adds an issuer-bound credential gate above the existing witness-conflict adjudication layer.

The gate answers one narrow question:

> At the declared evaluation time, did an accepted issuer authorize this exact adjudicator identity revision to exercise the exact witness-conflict adjudicator role?

It does not decide whether the adjudication was correct.

The original witness observations, fork evidence, dissent, rationale, selected head, and adjudication artifact remain immutable and independently inspectable.

## Constitutional boundary

CTRT does not convert credential evidence into a trust score, consensus percentage, or content verdict.

The layer publishes:

- exact identity and role bindings;
- issuer and policy references;
- validity and status evidence;
- explicit abstention reasons;
- downstream lifecycle relationships;
- limitations and non-claims.

It does not pronounce the adjudicator, checkpoint, content, or analyzer result good or bad.

## Artifact graph

The fixed synthetic graph extends the `0.9.0` witness-adjudication corpus:

```text
0.9.0 adjudication-bound corpus
  ├── witness registry and policy
  ├── witness attestations
  ├── checkpoint chain
  ├── fork evidence and dissent
  ├── adjudicator registry
  ├── adjudication policy
  └── immutable adjudication record

adjudicator credential issuer registry
adjudicator credential policy
adjudicator credential attestation
  ↓
1.0.0 adjudicator-credential-bound corpus
```

The `1.0.0` manifest is appended only after its new graph members are persisted and reverified.

## Fixed synthetic artifacts

### Issuer registry

Path:

```text
docs/candidates/
  synthetic-witness-conflict-adjudicator-credential-issuer-registry.v0.1.0.json
```

Identity:

```text
registry.synthetic-witness-conflict-adjudicator-credential-issuers@0.1.0
```

The registry contains one active synthetic issuer:

```text
issuer.synthetic.witness-conflict-governance
synthetic-witness-conflict-governance@0.1.0
```

Authorized credential type:

```text
ctrt.witness-conflict-adjudicator-role
```

### Credential policy

Path:

```text
docs/candidates/
  synthetic-witness-conflict-adjudicator-credential-policy.v0.1.0.json
```

Identity:

```text
policy.synthetic-witness-conflict-adjudicator-credentials@0.1.0
```

The policy binds the exact issuer registry and exact witness-conflict adjudicator registry.

The initial policy requires:

- exact role matching;
- abstention when not yet valid;
- abstention when expired;
- abstention when suspended;
- abstention when revoked.

### Adjudicator credential

Path:

```text
docs/corpora/extraction/revocations/witnesses/
  adjudicator-fork-credential.json
```

Identity:

```text
adjudicator-credential:credential.synthetic.fork.v0.1.0
```

Subject:

```text
adjudicator.synthetic.fork
synthetic-adjudicator@0.1.0
```

Authorized role:

```text
witness_conflict_adjudicator
```

Validity interval:

```text
2026-08-03T13:07:00Z <= evaluated_at < 2027-08-03T13:07:00Z
```

### Credential-bound corpus

Path:

```text
docs/corpora/extraction/synthetic-corpus.v1.0.0.json
```

Identity:

```text
corpus.synthetic-three-items.adjudicator-credential-bound@1.0.0
```

The manifest retains every inherited field and adds:

```text
adjudicator_credential_predecessor_corpus_ref
adjudicator_credential_issuer_registry_ref
adjudicator_credential_policy_ref
witness_conflict_adjudicator_credentials
```

The predecessor is the exact canonical `0.9.0` corpus:

```text
sha256:41300e406ca187e2f3301b08ac2e151ccf9fd2689e5b12c706f3514d354a8116
```

## Contract module

Implementation:

```text
src/ctrt/adjudicator_credential_attestation.py
```

### `AdjudicatorCredentialPolicySnapshot`

Binds:

- policy identity and version;
- lifecycle state;
- exact issuer registry reference;
- exact adjudicator registry reference;
- credential type;
- exact-role requirement;
- fail-closed status and time rules;
- creation timestamp;
- canonical payload and hash.

### `AdjudicatorCredentialAttestationSnapshot`

Binds:

- artifact and attestation IDs;
- credential type;
- pseudonymous adjudicator ID;
- exact identity revision;
- deterministic subject reference;
- issuer ID and revision;
- authorized roles;
- status;
- issuance and validity timestamps;
- optional revocation timestamp and reason;
- canonical payload and hash.

The parser rejects unsupported fields. This prevents personal identity attributes or ad hoc score fields from entering the credential contract.

### `CredentialBoundAdjudicationCorpusSnapshot`

Wraps the existing `AdjudicationBoundWitnessCorpusSnapshot` and binds:

- exact predecessor corpus;
- exact issuer registry;
- exact credential policy;
- one ordered credential entry per adjudicator registry member.

It does not mutate or reinterpret the predecessor adjudication graph.

### `AdjudicatorCredentialDecisionReport`

Records:

- experiment identity;
- credential-bound corpus;
- adjudicator registry;
- issuer registry;
- credential policy;
- immutable adjudication reference;
- credential outcome;
- per-adjudicator summaries;
- evaluation time.

Each summary preserves:

- adjudicator ID and identity revision;
- issuer ID and revision;
- authorized role;
- attestation status;
- validity interval;
- structured abstention evidence.

No scalar trust score is produced.

## Structural validation

`validate_adjudicator_credential_attestations` requires:

1. a frozen experiment plan;
2. exact plan/corpus identity and content order;
3. exact adjudicator registry reference;
4. exact issuer registry reference;
5. exact credential policy reference;
6. exact adjudication reference;
7. accepted adjudicator, issuer, and policy lifecycle states;
8. policy references matching the supplied registries;
9. one credential entry for every registry member;
10. exact entry-to-attestation reference equality;
11. exact adjudicator ID and identity revision;
12. exact role equality;
13. exact credential type;
14. existing issuer and exact issuer revision;
15. issuer authorization for the credential type;
16. credential coverage for the adjudicator named by the adjudication record.

Any mismatch fails structurally and produces no verified final receipt.

## Eligibility evaluation

After structural validation, the gate evaluates eligibility.

Abstention reasons may include:

```text
credential-issuer-inactive
credential-status:suspended
credential-status:revoked
credential-not-yet-valid
credential-expired
```

The decision is:

```text
execute
```

only when no credential summary triggers abstention.

Otherwise it is:

```text
abstain
```

This is not a score or vote. One inactive required credential is sufficient to deny permission because each required authorization is independently necessary.

## Storage lifecycle

`persist_credential_bound_adjudication_corpus` performs:

1. predecessor identity and content checks;
2. storage reread of the exact predecessor corpus;
3. structural and current-eligibility validation;
4. issuer registry persistence;
5. credential policy persistence;
6. credential attestation persistence;
7. `1.0.0` corpus persistence last;
8. complete graph reread and hash verification.

Publication requires credentials that are eligible at the publication evaluation time.

An inactive test credential can still be evaluated by the run-time validator in an independently constructed test graph, but it cannot publish a canonical eligible corpus manifest.

## Execution runner

Implementation:

```text
src/ctrt/credentialed_adjudicated_witness_runner.py
```

Class:

```text
CredentialedAdjudicatedWitnessExperimentRunner
```

### Lifecycle

The runner performs:

1. preflight;
2. storage-backed credential evidence loading;
3. credential validation;
4. credential-decision persistence;
5. either terminal credential abstention or delegation;
6. final persistence;
7. final verification.

### Run-specific decision

```text
<experiment-run-id>:adjudicator-credential-decision
```

### Terminal artifacts

Credential abstention:

```text
<experiment-run-id>:adjudicator-credential-abstention
```

Successful downstream execution:

```text
<experiment-run-id>:adjudicator-credential-completion
```

A later downstream governance abstention:

```text
<experiment-run-id>:adjudicator-credential-terminal-abstention
```

## No-downstream abstention guarantee

When the adjudicator credential outcome is `abstain`, the runner does not invoke the existing adjudicated witness runner.

Therefore it creates no new run-specific:

```text
credential-revocation-checkpoint-verification
checkpoint-witness-decision
witness-conflict-adjudication-decision
credential-revocation-decision
governed execution session
analyzer result
```

The credential decision and final abstention marker remain available and verified.

The immutable predecessor adjudication record remains stored because it predates the run and is part of the corpus graph.

## Delegated execution

When the credential outcome is `execute`, the runner delegates the exact existing `AdjudicatedWitnessCheckpointExperimentRunner` without changing its witness, fork, dissent, selected-head, revocation, reviewer-credential, quality, or analyzer semantics.

The credentialed receipt preserves downstream outcomes separately:

```text
credential_outcome
witness_outcome
adjudication_outcome
revocation_outcome
terminal_outcome
```

Credential authorization cannot overwrite the original witness abstention or adjudication record.

## Failure preservation

If downstream execution fails after credential authorization:

- the issuer registry remains stored;
- the credential policy remains stored;
- the credential attestation remains stored;
- the immutable adjudication remains stored;
- the run-specific credential decision remains stored;
- any downstream artifacts completed before failure remain stored;
- no credential completion artifact is claimed.

If final persistence fails, prior verified evidence remains available but no final verified receipt is returned.

## Schemas

This phase adds:

```text
schemas/adjudicator-credential-issuer-registry.schema.json
schemas/adjudicator-credential-policy.schema.json
schemas/adjudicator-credential-attestation.schema.json
schemas/adjudicator-credential-bound-corpus.schema.json
schemas/adjudicator-credential-decision.schema.json
schemas/credentialed-adjudicator-final.schema.json
```

The issuer registry, policy, and attestation schemas are closed documents.

The corpus schema validates the new credential-binding surface while inherited fields remain governed by the existing nested parsers and schemas.

The decision and final schemas contain no trust score, vote count, consensus percentage, or aggregate confidence field.

## Test matrix

`tests/test_adjudicator_credential_attestation.py` covers:

- active credential execution;
- preservation of the immutable adjudication reference;
- schema validation;
- not-yet-valid abstention;
- expired abstention;
- suspended status;
- revoked status;
- no downstream artifacts after credential abstention;
- identity-revision drift;
- issuer-revision drift;
- private identity field rejection;
- append-only idempotence;
- exact storage reconstruction;
- downstream analyzer failure;
- final persistence failure;
- absence of credential scores from policy semantics.

The complete repository suite contains 274 passing tests before final documentation and export validation.

## Verification statement

A verified adjudicator credential receipt establishes that CTRT reverified the exact supplied artifact relationships and evaluated the credential at the declared time.

It does not establish:

- legal identity;
- issuer trustworthiness;
- cryptographic authorship;
- adjudicator correctness;
- global checkpoint uniqueness;
- complete witness or fork disclosure;
- extraction or analyzer accuracy;
- content quality;
- consensus;
- an aggregate CTRT score.

## Deferred work

The next bounded layer is an append-only adjudicator credential revocation ledger.

It should preserve status changes as separate immutable events with deterministic as-of evaluation, while leaving both the original credential and adjudication record unchanged.
