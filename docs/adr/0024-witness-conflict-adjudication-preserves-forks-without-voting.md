# ADR-0024: Witness conflict adjudication preserves forks without voting

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0023 introduced immutable named-witness observations of a credential-revocation checkpoint head. The witness gate intentionally abstains whenever any required witness reports a conflicting head. That rule prevents a larger group of matching witnesses from outvoting a smaller conflicting group, but it leaves a governance question unanswered:

> What happens after a structurally valid witness conflict is preserved?

Treating the conflict as permanently terminal would make witness evidence impossible to govern. Treating the matching witness count as a verdict would violate CTRT's prohibition on majority-vote truth claims. Replacing the original witness decision would erase evidence about the fork.

CTRT therefore needs a separate adjudication layer that can record an authorized governance decision while preserving the original witness abstention, every conflicting observation, the adjudicator's rationale, and any dissent that remains after resolution.

## Decision

CTRT will represent witness-conflict adjudication as a separate immutable evidence layer above checkpoint witness attestations.

The layer introduces:

- a frozen adjudicator registry;
- a frozen fail-closed adjudication policy;
- an immutable adjudication record;
- an append-only adjudication-bound corpus successor;
- a run-specific adjudication decision;
- an execution wrapper that either abstains or delegates the existing checkpoint-gated lifecycle.

### Separate outcomes

The system preserves at least three distinct claims:

1. `witness_outcome`: what the named witness observations require under the witness policy;
2. `adjudication_outcome`: whether authorized adjudication permits downstream execution;
3. downstream revocation and terminal outcomes, if execution is permitted.

A resolved conflict therefore may legitimately produce:

```text
witness_outcome      = abstain
adjudication_outcome = execute
```

The original witness abstention is not rewritten. The later authorization is a new governance artifact with its own authority, rationale, limitations, and evidence.

### Resolution states

Each adjudication record has exactly one status:

- `not_required`: no conflicting witness observation exists;
- `pending`: conflict exists but no adjudicator decision is claimed;
- `resolved`: an authorized adjudicator selected the independently verified declared checkpoint head;
- `unresolved`: an authorized adjudicator examined the conflict but did not select a head.

The initial policy fails closed:

- `pending` abstains;
- `unresolved` abstains;
- only `not_required` or `resolved` may proceed.

### Authorized adjudicator identity

A decided record binds:

- adjudicator ID;
- immutable identity revision;
- authorized role;
- exact adjudicator registry;
- exact adjudication policy;
- decision time;
- rationale.

The current layer verifies registry-bound identity and role only. It does not establish real-world identity, competence, independence, honesty, or cryptographic authorship.

### Fork evidence and dissent

Every conflicting witness observation is reconstructed from the existing witness decision and bound into the adjudication record as exact fork evidence:

- witness ID;
- witness-attestation reference;
- expected checkpoint head;
- observed conflicting head.

A decided record must preserve one dissent entry for every conflict. The dissent must bind the same witness, attestation, and observed head as the corresponding fork evidence.

Resolution therefore never deletes, replaces, or minimizes the conflicting claim.

### Permitted selected head

A resolved adjudication may select only the checkpoint head already bound by the frozen checkpoint log and independently verified checkpoint chain.

It may not:

- select the conflicting observed head;
- invent a third head;
- reconcile or mutate either head;
- treat adjudicator authority as proof that no external fork exists.

This is deliberately conservative. The adjudicator governs whether the already verified declared head may proceed; the adjudicator does not create checkpoint integrity.

### No vote aggregation

The policy requires `forbid_vote_aggregation = true`.

The decision never contains:

- vote counts;
- majority flags;
- consensus percentages;
- quorum scores;
- aggregate confidence;
- winner or losing-side labels.

Two matching witnesses and one conflicting witness do not become a two-to-one result. The witness layer abstains. The adjudication layer may later authorize execution only through a separately governed decision.

### Publication boundary

The adjudicator registry, policy, witness attestations, and adjudication record are persisted and reverified before the adjudication-bound corpus manifest is written last.

An unknown or unauthorized adjudicator cannot publish a valid adjudication-bound corpus. This is a structural publication failure, not a governed abstention.

### Execution boundary

The adjudicated runner performs these stages in order:

1. preflight exact plan and corpus binding;
2. storage-backed evidence loading;
3. checkpoint-chain reverification and report persistence;
4. witness validation and witness-decision persistence;
5. adjudication validation and adjudication-decision persistence;
6. terminal abstention for pending or unresolved conflict, or delegation to the existing checkpoint-gated runner;
7. final artifact persistence;
8. full storage-backed verification.

If adjudication abstains, no revocation, credential, review, quality, analyzer, or experiment-completion artifact is created.

If later execution fails, checkpoint, witness, adjudication, and any earlier verified content evidence remain preserved without a final adjudication-completion claim.

## Append-only corpus evolution

The witness-bound `0.8.0` corpus remains immutable.

The adjudication-bound successor is:

```text
corpus.synthetic-three-items.witness-adjudication-bound@0.9.0
```

It preserves the complete inherited governance graph and adds exact references to:

- the `0.8.0` predecessor;
- the adjudicator registry;
- the adjudication policy;
- the ordered witness-attestation population, including the conflicting observation;
- the adjudication record.

The `0.8.0` and `0.9.0` artifacts use distinct identities and coexist in append-only storage.

## Structural failure versus governed abstention

Structural failure includes:

- unknown adjudicator;
- identity-revision or role drift;
- substituted registry, policy, corpus, checkpoint, witness, or adjudication reference;
- conflict evidence differing from the witness decision;
- missing dissent for a decided conflict;
- dissent that does not bind the exact conflicting attestation and head;
- resolved selection of any head other than the declared verified head;
- decision timestamp after evaluation;
- malformed lifecycle fields;
- unsupported vote or aggregate fields;
- missing or tampered stored evidence.

Governed abstention includes a structurally valid adjudication with status `pending` or `unresolved`.

## Meaning of verified

For this layer, `verified` means that CTRT checked and reverified from append-only storage:

- the exact plan and adjudication-bound corpus;
- the checkpoint chain and declared head;
- the witness registry, policy, and attestations;
- the original witness decision;
- the adjudicator registry, policy, identity revision, and role;
- the exact fork evidence and preserved dissent;
- the adjudication status, selected head, rationale, and timestamps;
- the separation among witness, adjudication, revocation, and terminal outcomes;
- the final artifact relationships.

It does not mean:

- the adjudicator is correct, honest, independent, or competent;
- the selected checkpoint head is globally unique;
- all witnesses, forks, checkpoints, or revocation events were disclosed;
- the conflicting witness was mistaken or dishonest;
- the observation channel or time source is trustworthy;
- the artifacts are cryptographically signed;
- global transparency-log consistency was established;
- extraction, review, analyzer, or content quality was established;
- an aggregate CTRT score exists.

## Consequences

### Positive

- Witness conflicts become governable without becoming vote totals.
- The original abstention and later authorization remain independently inspectable.
- Fork evidence and dissent survive resolution.
- Unauthorized adjudication fails before a complete corpus can be published.
- Pending and unresolved cases remain fail closed.
- Downstream execution reuses the already verified checkpoint lifecycle.

### Costs

- The governance graph gains another immutable registry, policy, record, corpus version, run decision, and final artifact.
- Authorized adjudication remains a trust input rather than an objective proof.
- Real identity, signatures, fork reconciliation, and global consistency remain unsolved.

## Alternatives rejected

### Majority vote among witnesses

Rejected because witness count is not a truth instrument and would erase minority conflict evidence.

### Replace the witness abstention after resolution

Rejected because it would rewrite history and obscure the distinction between observation policy and later governance.

### Allow an adjudicator to choose any observed head

Rejected because adjudication must not substitute for checkpoint-chain verification.

### Permanently block every conflicting case

Rejected because preserved evidence still requires an explicit governance path.

### Resolve forks through a live network in this phase

Rejected because signatures, gossip, inclusion proofs, consistency proofs, identity, network retrieval, and operational trust are outside this dependency-free bounded slice.

## Follow-on work

A later bounded layer may attest and revoke adjudicator credentials independently of the adjudication record. That work must not introduce private identity data, real identity providers, signatures, or vote-based authorization into this phase.
