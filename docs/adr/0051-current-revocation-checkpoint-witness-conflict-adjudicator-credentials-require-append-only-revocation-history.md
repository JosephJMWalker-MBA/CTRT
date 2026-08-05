# ADR-0051: Current revocation-checkpoint conflict-adjudicator credentials require append-only revocation history

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0050 added an issuer-bound credential for the exact adjudicator identity revision and `witness_conflict_adjudicator` role used by the immutable `1.24.0` current revocation-checkpoint witness conflict adjudication.

The resulting `1.25.0` layer establishes that the credential was structurally valid and eligible at a declared evaluation time. It does not establish that no later issuer-authored suspension or revocation exists.

Treating the credential document's embedded status as permanent would collapse two independently testable claims:

1. an accepted issuer issued a structurally valid credential;
2. the accepted append-only status history leaves that credential operational at a particular time.

A later status event must not rewrite the credential, adjudication, witness conflict, selected checkpoint head, or any inherited artifact.

## Decision

CTRT will publish an append-only `1.26.0` revocation layer over the exact immutable `1.25.0` credential graph.

The layer will:

1. preserve `1.25.0` unchanged as the revocation predecessor;
2. bind an accepted fail-closed revocation policy;
3. require issuer-authored events for the exact credential, adjudicator, issuer, and issuer revision;
4. preserve event recording time separately from event effective time;
5. require monotonic effective time and linear supersession;
6. bind an ordered frozen event ledger to the exact `1.25.0` credential corpus and issuer registry;
7. evaluate effective status as of a declared time;
8. keep future-effective events visible without applying them early;
9. abstain when the effective status is `suspended` or `revoked`;
10. treat predecessor, authority, credential, event, ledger, order, chronology, storage, and serialization drift as structural failure;
11. persist the revocation decision before any `1.25.0` execution;
12. narrow the exact plan from `1.26.0` to `1.25.0` only after revocation execution;
13. preserve the revocation result and every delegated result separately.

## Exact predecessor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-bound@1.25.0
sha256:b43a185d7b21879b3a234fe84233f324ae66a07a034b9ae3b7cd3577c226dca0
```

The predecessor preserves:

- the accepted credential issuer registry;
- the exact credential policy;
- the exact credential attestation;
- the exact adjudicator ID and identity revision;
- the `witness_conflict_adjudicator` role;
- the complete `1.24.0` conflict adjudication;
- the original required witness outcome of `abstain`;
- gamma's conflicting observation;
- fork evidence and preserved dissent;
- the selected exact `1.22.0` checkpoint head;
- every lower and inherited governance artifact.

None of those records is modified.

## Fixed revocation graph

```text
revocation policy = sha256:e46213a13225814e673fdba2824a036dfb0030fd4f4bc11c91bfedbd52a00739
future suspension = sha256:0d634c690052226e9461268afedbc02d479465d9509246528e4d19b7ff780b63
frozen ledger     = sha256:98a2bdddc91074042cd84b6ec79145eee4bf9da0f47119b0912f26edbb042919
successor 1.26.0  = sha256:05c322ff072be8b63868d7b8aad77aa69752ce92eef5e66ab88d169156e515f8
```

## Exact event target

```text
credential:
  adjudicator-credential:credential.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator.v0.1.0

adjudicator:
  adjudicator.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork

issuer:
  issuer.synthetic.current-revocation-checkpoint-witness-conflict-governance

issuer revision:
  synthetic-current-revocation-checkpoint-witness-conflict-governance@0.1.0

effect: suspended
recorded_at: 2026-08-03T19:58:43Z
effective_at: 2027-02-01T00:00:00Z
```

The event is present in the frozen history before its effect applies. Evaluation before the effective boundary remains active. Evaluation at the exact boundary abstains.

## Semantic separation

Before the suspension boundary:

```text
new revocation outcome = execute
new credential outcome = execute
```

At or after the suspension boundary:

```text
new revocation outcome = abstain
all PR #47 outcomes    = null
terminal outcome       = abstain
```

A revocation abstention does not erase or retroactively alter credential issuance, adjudication, witness observations, or prior execution decisions. It withholds authorization through this new boundary.

## Publication order

Publication is manifest-last:

1. accepted revocation policy;
2. immutable issuer-authored status events;
3. frozen ordered event ledger;
4. compact `1.26.0` successor manifest;
5. exact-hash reread of the successor, predecessor, policy, ledger, events, credential authorities, credential, and adjudication.

Required chronology is:

```text
1.25.0 published
<= policy created
<= event recorded
<= ledger frozen
<= 1.26.0 published
<= revocation evaluated
<= credential evaluated
<= delegated witness evaluation
<= delegated completion
<= outer completion
```

Event effective time remains independent from event recording time.

## Execution order

```text
load exact 1.26.0 revocation graph
  -> load exact preserved 1.25.0 credential evidence
  -> validate as-of revocation status
  -> persist revocation decision
  -> revocation abstention or exact 1.25.0 plan derivation
  -> unchanged PR #47 lifecycle under the same run ID
  -> outer finalization
  -> complete storage reread
```

## Failure semantics

Structural failures include:

- predecessor substitution;
- content-order drift;
- policy or ledger substitution;
- credential or adjudicator substitution;
- issuer or issuer-revision substitution;
- event-reference or event-payload drift;
- non-monotonic effective time;
- broken linear supersession;
- event recording after ledger freeze;
- publication or evaluation chronology drift;
- run-identity mismatch;
- stored-artifact drift;
- noncanonical serialization.

A valid effective `suspended` or `revoked` status is a governed abstention, not a structural failure.

## Trust boundary

This layer does not establish:

- ledger completeness;
- absence of undisclosed events or alternate histories;
- trusted external time;
- cryptographic authorship, signatures, or private-key possession;
- legal or real-world identity;
- issuer or adjudicator independence, competence, honesty, or correctness;
- correctness of the selected checkpoint head;
- majority support, quorum, consensus, confidence, reputation, or aggregate trust scoring;
- analytical accuracy;
- deployment;
- an aggregate CTRT score.

It establishes only the effective status of the exact credential under the accepted frozen history and policy at a declared evaluation time.

## Consequences

### Positive

- credential issuance and operational status remain independent claims;
- future-effective events remain visible without applying early;
- revocation cannot rewrite prior evidence;
- execution remains fail-closed and reconstructable;
- every delegated outcome remains separately inspectable.

### Costs

- another immutable graph member and decision artifact are required;
- event ordering and chronology require explicit validation;
- a frozen ledger does not prove global completeness;
- long public names remain necessary to prevent authority-layer ambiguity.

## Intentionally deferred

A later bounded layer may checkpoint this exact `1.26.0` ledger. Such a layer must preserve the complete `1.26.0` graph, the exact `1.25.0` credential graph, the complete `1.24.0` adjudication graph, and every inherited artifact unchanged.
