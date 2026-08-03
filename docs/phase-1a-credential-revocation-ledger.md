# Phase 1A: Credential revocation ledger

This phase adds deterministic credential status evaluation without rewriting the original reviewer credential and without contacting a live revocation service.

## Problem

A reviewer credential can be valid when issued and later suspended, revoked, or reinstated. Storing only the credential's current state would make historical experiment records unstable. Editing the original credential would erase the exact evidence used by earlier runs.

CTRT instead preserves status changes as immutable issuer events and evaluates one frozen event population as of the experiment timestamp.

## Artifact graph

```text
Reviewer credential attestation (immutable)
        │
        ├── Credential revocation event 1
        │          effect + effective_at + reason
        │
        └── Credential revocation event 2
                   supersedes event 1, but does not delete it

Credential revocation policy
        │
        ├── exact issuer requirement
        ├── permitted effects
        ├── linear supersession
        ├── monotonic effective time
        └── abstention states

Credential revocation ledger
        │
        ├── exact credential corpus reference
        ├── exact issuer registry reference
        ├── exact policy reference
        └── ordered event references

Revocation-bound corpus
        │
        ├── exact credential-bound predecessor
        ├── exact revocation policy
        └── exact frozen ledger

Run-specific revocation decision
        │
        ├── effective status for each reviewer
        ├── every applied event ID
        ├── final effective event ID
        └── execute or abstain

Final revocation-gated artifact
        ├── revocation abstention, or
        └── downstream credentialed result
```

## Public contracts

### `CredentialRevocationPolicySnapshot`

Freezes:

- accepted policy identity and version;
- permitted effects: `active`, `suspended`, `revoked`;
- exact attestation-issuer requirement;
- monotonic effective-time requirement;
- linear supersession requirement;
- statuses that require abstention.

### `CredentialRevocationEventSnapshot`

Preserves one immutable event with:

- event and artifact IDs;
- exact credential-attestation reference;
- reviewer ID;
- issuer ID and immutable revision;
- status effect;
- `effective_at`;
- `recorded_at`;
- reason;
- optional prior event superseded.

`effective_at` answers when the status changes for evaluation. `recorded_at` answers when the event was placed in the record. Neither is inferred from the runtime clock.

### `CredentialRevocationLedgerSnapshot`

Freezes one ordered event population. The first implementation permits one linear history per credential. Later events must supersede the immediately previous event and may not move effective time backward.

### `RevocationBoundCredentialCorpusSnapshot`

Extends the complete credential-bound corpus with:

- an exact `0.5.0` predecessor reference;
- the revocation-policy reference;
- the frozen-ledger reference.

The synthetic `0.6.0` corpus uses a distinct artifact ID, allowing both predecessor and successor to coexist in the append-only store.

### `CredentialRevocationDecisionReport`

Stores the run's deterministic as-of result. Every reviewer summary contains:

- original attestation status;
- effective status;
- ordered applied event IDs;
- effective event ID, if any;
- explicit abstention reasons.

The report contains no reviewer score, vote count, consensus percentage, or content judgment.

### `RevocationGatedCredentialedExtractionExperimentRunner`

Wraps the existing credential-attested runner. Its stages are:

1. preflight;
2. evidence loading;
3. revocation validation;
4. decision persistence;
5. downstream credentialed execution, when permitted;
6. final persistence;
7. final reverification.

## As-of semantics

For each reviewer:

1. start from the immutable credential attestation's status;
2. inspect that reviewer's events in ledger order;
3. enforce the linear supersession and timestamp rules;
4. apply only events with `effective_at <= evaluated_at`;
5. preserve every applied event ID;
6. use the last applied event as the effective status.

The fixed synthetic event suspends the secondary reviewer on January 1, 2027.

Therefore the same frozen ledger:

- permits execution on August 3, 2026;
- abstains on January 2, 2027;
- can permit a later run only if a new issuer-authorized `active` event explicitly supersedes the suspension.

The suspension remains visible in the later run's applied history.

## Failure versus abstention

### Structural failure

The runner fails before a verified decision when:

- an event references an unknown credential;
- reviewer or issuer identity differs;
- issuer revision differs;
- event issuer is not the attestation issuer;
- status effect is not policy-permitted;
- event IDs repeat;
- supersession is broken;
- effective time moves backward;
- policy, ledger, corpus, or stored hashes differ.

### Verified abstention

A structurally valid effective status of `suspended` or `revoked` yields a verified abstention.

The run stores and reverifies:

- the run-specific revocation decision;
- the final credential-revocation abstention artifact.

It deliberately does not create:

- a reviewer-credential decision;
- a review-adjudication decision;
- an extraction-quality decision;
- analyzer sessions;
- experiment completion.

## Persistence order

For a new revocation-bound corpus:

1. persist the predecessor credential corpus and its graph;
2. persist the accepted revocation policy;
3. persist every immutable event;
4. persist the frozen ledger;
5. publish the revocation-bound corpus last.

This means partial event ingestion cannot masquerade as a complete corpus.

## Fixed synthetic artifacts

- `docs/candidates/synthetic-credential-revocation-policy.v0.1.0.json`
- `docs/corpora/extraction/revocations/secondary-suspension-2027.json`
- `docs/corpora/extraction/revocations/synthetic-ledger.v0.1.0.json`
- `docs/corpora/extraction/synthetic-corpus.v0.6.0.json`

Schemas:

- `schemas/credential-revocation-policy.schema.json`
- `schemas/credential-revocation-event.schema.json`
- `schemas/credential-revocation-ledger.schema.json`
- `schemas/revocation-bound-credential-corpus.schema.json`
- `schemas/credential-revocation-decision.schema.json`
- `schemas/revocation-gated-credentialed-final.schema.json`

## Verified checks

A final revocation-gated receipt preserves these exact checks:

```text
exact-revocation-policy-bound
exact-revocation-ledger-bound
issuer-authority-and-event-supersession-verified
credential-status-evaluated-as-of-experiment-time
revocation-decision-persisted
revocation-outcome-finalized
```

## Limits

This phase does not connect to:

- a live identity provider;
- a live revocation endpoint;
- cryptographic signatures;
- issuer transparency logs;
- private identity records;
- real reviewers or credentials.

A verified result proves deterministic evaluation of the stored artifacts. It does not prove that the issuer is trustworthy, the ledger is globally complete, or the reviewer is correct.
