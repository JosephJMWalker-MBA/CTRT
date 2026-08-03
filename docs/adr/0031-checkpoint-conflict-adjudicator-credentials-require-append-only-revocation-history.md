# ADR-0031: Checkpoint-conflict adjudicator credentials require append-only revocation history

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0030 bound the adjudicator authorized to resolve an adjudicator-checkpoint witness conflict to an exact pseudonymous identity revision, role, issuer revision, credential type, status, and validity interval.

That immutable credential establishes what the issuer declared when the credential was created. It does not answer whether a later issuer-authored suspension, revocation, or reinstatement had become effective at the time a run relied on the credential.

Editing the credential would destroy the historical issuance claim. Reading only its embedded status would ignore later operational history. A mutable current-status field would also make prior experiment results difficult to reconstruct.

The next bounded question is therefore:

> What was the effective operational status of the exact checkpoint-conflict adjudicator credential at the declared evaluation time, according to the exact frozen event ledger?

This question remains independent of whether the adjudicator was correct, whether a witness was truthful, or whether the selected checkpoint head is globally unique.

## Decision

CTRT will represent post-issuance credential status through immutable issuer-authored events collected in a frozen, ordered revocation ledger.

The layer will:

1. preserve the original credential and its base status unchanged;
2. bind every event to the exact credential artifact, adjudicator ID, issuer ID, and immutable issuer revision;
3. permit only policy-declared `active`, `suspended`, and `revoked` effects;
4. require monotonic effective time and linear supersession within each credential history;
5. evaluate the event sequence as of an explicit timestamp;
6. report base status, effective status, applied event IDs, and the effective event separately;
7. abstain when the as-of effective status is policy-ineligible;
8. persist the revocation decision before any credential, witness, conflict-adjudication, reviewer, or analyzer work begins;
9. preserve all prior witness abstention, fork evidence, dissent, selected-head evidence, rationale, and adjudication artifacts unchanged.

A future-effective event is preserved immediately but does not affect an earlier evaluation. At its effective boundary, the operational status changes without modifying the credential or any earlier decision.

## Successor-manifest boundary

The new corpus is a compact manifest:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-bound@1.6.0
```

It binds:

- the exact canonical `1.5.0` credential-bound predecessor;
- the exact revocation policy;
- the exact frozen ledger;
- the unchanged ordered content population.

The outer revocation decision is evaluated against a frozen plan bound to `1.6.0`.

When revocation permits execution, the outer runner derives a narrowly scoped nested plan bound to the exact immutable `1.5.0` predecessor and delegates the unchanged ADR-0030 runner. This is an explicit scope transition, not an implicit substitution:

```text
1.6.0 plan -> revocation decision
1.5.0 derived plan -> unchanged credential and downstream lifecycle
```

The content IDs, order, experiment identity, candidate population, analyzer population, and all execution parameters remain unchanged. Only the corpus reference is narrowed to the predecessor required by the delegated runner.

## Failure and abstention boundaries

Structural failure includes:

- plan or content-order drift;
- substituted policy, ledger, credential, issuer, or artifact references;
- unknown credential references;
- duplicate event IDs;
- issuer identity or revision drift;
- an event effect not permitted by policy;
- non-linear supersession;
- decreasing effective time;
- missing or altered stored artifacts;
- final persistence or reread failure.

Governed abstention includes:

- an as-of effective status of `suspended` or `revoked` under the accepted policy.

A revocation abstention is terminal for the run. No ADR-0030 credential decision, checkpoint-witness evaluation, conflict adjudication, reviewer governance, or analyzer work may occur afterward.

## Append-only publication order

Publication is manifest-last:

1. revocation policy;
2. immutable events;
3. frozen ledger;
4. compact `1.6.0` successor manifest.

No predecessor artifact is edited.

## Consequences

### Positive

- historical issuance and later operational status remain separately inspectable;
- prior decisions are reproducible at their declared timestamps;
- future-effective changes can be published without retroactively changing earlier runs;
- suspension and revocation stop downstream work before the adjudication can affect execution;
- the generic adjudicator revocation grammar is reused rather than duplicated;
- the `1.6.0`/`1.5.0` delegation boundary is explicit and testable.

### Costs

- callers must carry another policy, ledger, event population, and evaluation timestamp;
- the outer runner must preserve two exact plan scopes;
- a frozen ledger is not proof that all real-world events were disclosed;
- issuer-authored JSON does not provide cryptographic authorship or trusted time.

## Non-claims

Verification does not establish:

- legal or real-world identity;
- issuer trustworthiness;
- cryptographic authorship;
- trusted external time;
- complete event disclosure;
- adjudicator honesty, independence, competence, or correctness;
- which witness was truthful;
- global uniqueness of the checkpoint head;
- consensus, quorum, majority support, or reputation;
- content, extraction, model, or analyzer accuracy;
- an aggregate CTRT score.

## Deferred work

The next bounded layer may checkpoint the exact revocation-ledger head. Witnesses, conflict adjudication over checkpoint witnesses, signatures, keys, identity providers, and live transparency services remain separate future decisions.
