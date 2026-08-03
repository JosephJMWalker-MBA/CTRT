# Phase 1A: Adjudicator-Checkpoint Conflict Adjudicator Credential Attestation

## Purpose

This slice places issuer-bound credential evidence above the adjudicator introduced by ADR-0029.

ADR-0029 preserves an original checkpoint-witness outcome of `abstain`, the conflicting observation, fork evidence, dissent, rationale, and a separate authorized decision that may permit only the independently verified checkpoint head to proceed. This slice asks a narrower question before that authorization may affect execution:

> Was the exact pseudonymous adjudicator identity revision authorized for the exact conflict-adjudicator role at the declared evaluation time?

It does not reconsider or rewrite the conflict, the witness outcome, or the adjudication.

## Fixed synthetic graph

```text
corpus.synthetic-three-items.adjudicator-checkpoint-witness-adjudication-bound@1.4.0
    ↓
registry.synthetic-adjudicator-checkpoint-witness-conflict-adjudicator-credential-issuers@0.1.0
    ↓
policy.synthetic-adjudicator-checkpoint-witness-conflict-adjudicator-credentials@0.1.0
    ↓
adjudicator-credential:
credential.synthetic.adjudicator-checkpoint-fork.v0.1.0
    ↓
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-bound@1.5.0
```

The new credential binds:

```text
adjudicator_id:
adjudicator.synthetic.adjudicator-checkpoint-fork

identity_revision:
synthetic-adjudicator-checkpoint-conflict-adjudicator@0.1.0

authorized_role:
witness_conflict_adjudicator

credential_type:
ctrt.adjudicator-checkpoint-witness-conflict-adjudicator-role
```

## Reused contracts

This slice reuses the established generic adjudicator credential contracts for:

- issuer-registry parsing and lifecycle;
- credential-policy lifecycle;
- immutable credential attestations;
- exact role and identity-revision binding;
- active, suspended, and revoked status;
- explicit validity intervals;
- canonical credential decision reports.

The new module adds only the context-specific corpus wrapper, storage reconstruction, validation boundary, publication function, and outer runner.

This avoids creating a second credential grammar merely because the governed adjudication occurs at a later layer.

## Publication lifecycle

`persist_credential_bound_adjudicator_checkpoint_conflict_corpus`:

1. re-reads and verifies the exact canonical `1.4.0` predecessor;
2. verifies the complete conflict-adjudicator credential population;
3. verifies exact identity revision, role, issuer, policy, type, and validity;
4. appends the issuer registry;
5. appends the credential policy;
6. appends credential attestations in exact registry order;
7. appends the `1.5.0` corpus manifest last;
8. reloads and re-verifies the complete stored credential graph.

An interrupted publication may leave valid unreferenced members, but no `1.5.0` manifest claims completion until every dependency exists.

## Execution lifecycle

`CredentialedAdjudicatorCheckpointConflictExperimentRunner`:

1. binds the frozen plan to the exact `1.5.0` corpus and ordered content set;
2. loads the registry, issuer registry, policy, credential, and preserved adjudication from append-only storage;
3. evaluates credential status at `checkpoint_conflict_credential_evaluated_at`;
4. persists a run-specific credential decision;
5. produces terminal credential abstention or delegates the unchanged ADR-0029 runner;
6. persists a final credential manifest;
7. re-reads and verifies every referenced artifact.

Run-specific decision:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-decision
```

Terminal artifacts:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-abstention
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-completion
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-terminal-abstention
```

## Abstention boundary

A structurally valid but inactive credential stops before any new:

- adjudicator-checkpoint witness execution;
- witness-conflict adjudication decision;
- checkpoint execution;
- adjudicator revocation or credential evaluation;
- reviewer governance;
- governed analyzer session;
- analyzer result;
- experiment completion.

The immutable predecessor conflict and adjudication artifacts remain available because they belong to the frozen `1.4.0` graph.

## Separate outcomes

The final receipt preserves:

- checkpoint-conflict adjudicator credential outcome;
- original adjudicator-checkpoint witness outcome, if delegated;
- conflict-adjudication outcome, if delegated;
- downstream adjudicator revocation and credential outcomes;
- reviewer checkpoint-witness and adjudication outcomes;
- reviewer revocation outcome;
- terminal review or analysis outcome.

No layer overwrites another layer's evidence.

## Schemas

The slice adds:

```text
schemas/adjudicator-checkpoint-conflict-adjudicator-credential-bound-corpus.schema.json
schemas/credentialed-adjudicator-checkpoint-conflict-final.schema.json
```

It reuses:

```text
schemas/adjudicator-credential-issuer-registry.schema.json
schemas/adjudicator-credential-policy.schema.json
schemas/adjudicator-credential-attestation.schema.json
schemas/adjudicator-credential-decision.schema.json
```

## Verification meaning

`verified` means the supplied frozen artifacts, exact identities, role, issuer, status, timestamps, credential decision, delegated relationships, final manifest, and stored hashes were checked and rechecked.

It does not establish real identity, issuer trust, signatures, adjudicator correctness, witness truthfulness, global checkpoint uniqueness, complete disclosure, consensus, extraction accuracy, content quality, or an aggregate score.

## Intentionally excluded

- credential revocation events for the new conflict adjudicator;
- revocation checkpoints or witnesses for that authority;
- signatures, keys, identity providers, and live status services;
- real adjudicators, models, datasets, APIs, frontend, or deployment;
- majority vote, quorum, consensus percentage, reputation, or trust scores.
