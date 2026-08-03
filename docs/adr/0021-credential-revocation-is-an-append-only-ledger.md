# ADR-0021: Credential revocation is an append-only ledger

- **Status:** Accepted
- **Date:** 2026-08-03
- **Decision owners:** CTRT stewardship
- **Supersedes:** None
- **Related:** ADR-0020 reviewer credential attestation

## Context

ADR-0020 made reviewer-role credentials immutable artifacts. That creates a necessary distinction between the credential as issued and later information about whether the credential remains usable.

Rewriting the original attestation when a reviewer is suspended, revoked, or reinstated would destroy the historical record used by earlier experiments. Reading only a present-day status would also make a past experiment impossible to reproduce: the answer could change merely because the credential changed later.

CTRT therefore needs a status mechanism that:

1. leaves every issued attestation unchanged;
2. preserves every later issuer-authored status event;
3. determines status at the experiment's declared evaluation time;
4. permits a later event to supersede an earlier event without deleting it;
5. fails closed when issuer identity, credential identity, chronology, or event history is malformed;
6. abstains before review or analyzer execution when the effective status is inactive.

## Decision

Credential status changes SHALL be represented as immutable append-only events in a frozen revocation ledger.

### Original attestation remains immutable

A `ReviewerCredentialAttestationSnapshot` remains the issuer's original statement. Suspension, revocation, reinstatement, or correction SHALL NOT edit that artifact.

### Status events are separate artifacts

Each `CredentialRevocationEventSnapshot` binds:

- its own immutable event ID;
- the exact credential-attestation artifact reference;
- reviewer ID;
- issuer ID and immutable issuer revision;
- one status effect: `active`, `suspended`, or `revoked`;
- effective timestamp;
- recorded timestamp;
- reason;
- optional immediately superseded event ID.

The event contains no legal name, address, government identifier, biometric information, or private credential payload.

### Frozen ordered ledger

A `CredentialRevocationLedgerSnapshot` freezes:

- the exact predecessor credential corpus;
- the exact issuer registry;
- the exact revocation policy;
- an ordered population of immutable event references.

The ledger is published only after every referenced event exists.

### Deterministic as-of evaluation

Credential status begins with the immutable attestation's status. For each reviewer, events are evaluated in ledger order. Only events whose `effective_at` timestamp is less than or equal to the experiment's `evaluated_at` timestamp affect the decision.

`recorded_at` preserves when the event entered the record. It does not replace `effective_at` and is not used as a hidden wall-clock dependency.

The same frozen ledger may therefore:

- permit an experiment before a future suspension becomes effective;
- abstain after the suspension becomes effective;
- permit a later experiment after an authorized superseding reinstatement.

### Linear supersession

For one credential:

- the first event may not supersede another event;
- every later event must supersede the immediately prior event for that credential;
- effective timestamps must be monotonic;
- the earlier event remains in the ledger and in the decision's applied event history.

This first implementation intentionally chooses a linear history rather than parallel branches or conflict resolution among revocation authorities.

### Structural failure versus governed abstention

Structural defects fail validation. Examples include:

- unknown credential-attestation reference;
- substituted reviewer identity;
- unknown or mismatched issuer revision;
- event issuer different from the attestation issuer;
- unsupported status effect;
- duplicate event ID;
- broken supersession chain;
- non-monotonic effective time;
- ledger, policy, corpus, or stored hash drift.

A structurally valid event history that resolves to `suspended` or `revoked` produces a verified abstention. In that outcome:

- the revocation decision is persisted and reverified;
- the credential-attestation runner is not invoked;
- review adjudication is not invoked;
- extraction-quality evaluation is not invoked;
- no analyzer executes;
- no governed session or experiment completion is created;
- a final credential-revocation abstention artifact is stored.

A verified abstention is a successful governance outcome, not an execution error.

### Downstream separation

An effective `active` status permits the existing credential-attested lifecycle to begin. It does not guarantee that lifecycle will execute analyzers. Downstream credential validity, review disagreement, extraction quality, or analyzer execution may still independently abstain or fail.

The final artifact preserves both the revocation outcome and the downstream terminal outcome.

### Append-only corpus evolution

The revocation-bound synthetic corpus uses a distinct artifact ID and version from the credential-bound corpus. It retains an exact predecessor reference to the `0.5.0` credential corpus and adds exact revocation-policy and ledger references.

This avoids reusing one append-only artifact ID for different canonical bytes.

## Consequences

### Positive

- Past experiments remain reproducible after later credential changes.
- Suspension, revocation, and reinstatement remain inspectable as separate events.
- Corrections do not erase prior issuer statements.
- Experiment-time status is deterministic and independent of the current date.
- Revoked credentials stop the lifecycle before review or analyzer work.
- The system can distinguish malformed provenance from a valid abstention.

### Costs

- Event and ledger artifacts add another provenance layer.
- Issuers must publish explicit superseding events instead of editing status.
- Linear supersession rejects ambiguous or parallel event histories.
- A ledger snapshot must be frozen and referenced by each governed corpus.

## Non-claims

A verified revocation decision does not establish:

- real-world reviewer identity;
- external issuer trustworthiness;
- cryptographic signature authenticity;
- live or globally current revocation status;
- that no unpublished event exists;
- reviewer competence, independence, or correctness;
- extraction or analyzer accuracy;
- content quality;
- any aggregate CTRT score.

It establishes only that the exact stored issuer, policy, credential, event, and ledger artifacts were evaluated deterministically under the declared rules and timestamp.

## Deferred work

The following remain out of scope:

- live revocation services;
- digital signatures and issuer key rotation;
- multiple revocation authorities;
- branched event histories and conflict adjudication;
- retroactive-event publication policy;
- transparency-log inclusion proofs;
- private identity attributes;
- real reviewers, models, extractors, or datasets;
- API, frontend, deployment, retries, or distributed execution.
