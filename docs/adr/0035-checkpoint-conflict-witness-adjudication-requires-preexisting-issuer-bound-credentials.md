# ADR-0035: Checkpoint-conflict witness adjudication requires preexisting issuer-bound credentials

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0034 introduced authorized adjudication over the immutable `1.8.0` named-witness evidence protecting the revocation checkpoint for a checkpoint-conflict adjudicator's credential.

That layer deliberately preserves two distinct outcomes when a conflict is resolved:

```text
checkpoint_witness_outcome = abstain
adjudication_outcome = execute
```

The witness outcome records that the required named witnesses did not uniformly report one checkpoint head. The adjudication outcome records that accepted governance authority selected the independently verified head under policy.

The accepted adjudicator registry in ADR-0034 contains a stable pseudonymous adjudicator ID, an immutable identity revision, and the declared `witness_conflict_adjudicator` role. Those declarations establish the identity used by the governance graph, but they do not establish that an issuer had authorized that exact identity revision for that exact role when the adjudication occurred.

The next bounded question is therefore:

> Was the exact pseudonymous identity revision authorized for the exact `witness_conflict_adjudicator` role at the declared time?

This question must remain separate from:

- what each witness reported;
- whether the witnesses agreed;
- whether the independently verified checkpoint is correct in the real world;
- whether the adjudicator's selected head was correct;
- whether the adjudicator is legally identifiable, competent, independent, or honest;
- whether the credential was later revoked;
- whether an external trust or timestamp service exists.

## Decision

CTRT will add a distinct issuer-bound credential-attestation layer over the exact immutable `1.9.0` adjudication-bound corpus.

The layer will:

1. use an accepted immutable issuer registry containing stable issuer IDs, immutable issuer revisions, supported credential types, and active status;
2. use an accepted fail-closed credential policy bound to the exact issuer registry and exact `1.9.0` adjudicator registry;
3. bind one immutable credential attestation to the exact adjudicator ID, identity revision, subject reference, issuer ID, issuer revision, credential type, authorized role, status, issuance time, validity window, and optional revocation fields;
4. require the exact `witness_conflict_adjudicator` role declared by the adjudicator registry;
5. require the exact immutable identity revision declared by the adjudicator registry;
6. evaluate validity at an explicit declared time before the adjudication evaluation time;
7. produce governed abstention for a credential that is not yet valid, expired, suspended, or revoked when the graph is otherwise structurally coherent;
8. produce structural failure for identity, issuer, role, credential-type, reference, population, chronology, serialization, or storage-integrity drift;
9. persist the run-specific credential decision before invoking the adjudication lifecycle;
10. invoke the exact unchanged PR #31 adjudication runner only after credential authorization;
11. preserve the original witness outcome, fork evidence, dissent, rationale, selected checkpoint head, and adjudication record without modification;
12. keep credential, adjudication, witness, checkpoint, revocation, reviewer, and analyzer outcomes separately inspectable.

An eligible credential adds only the narrower operational claim:

> The exact pseudonymous identity revision was issuer-authorized for the exact conflict-adjudicator role at the declared pre-adjudication time.

It does not establish that the adjudication was correct.

## Fixed canonical authority

The canonical credential graph binds:

```text
adjudicator_id = adjudicator.synthetic.checkpoint-conflict-revocation-checkpoint-witness-conflict
identity_revision = synthetic-checkpoint-conflict-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
role = witness_conflict_adjudicator
credential_type = ctrt.checkpoint-conflict-revocation-witness-conflict-adjudicator-role
```

The fixed issuer authority is:

```text
issuer_id = issuer.synthetic.checkpoint-conflict-revocation-witness-conflict-governance
issuer_revision = synthetic-checkpoint-conflict-revocation-witness-conflict-governance@0.1.0
```

The canonical credential chronology is:

```text
issuer registry created   = 2026-08-03T19:54:05Z
credential policy created = 2026-08-03T19:54:15Z
credential issued         = 2026-08-03T19:54:25Z
credential valid from     = 2026-08-03T19:54:30Z
credential evaluated      = 2026-08-03T19:55:00Z
adjudication evaluated    = 2026-08-03T19:55:30Z
credential valid until    = 2027-08-03T19:54:30Z
```

The validity interval is half-open:

```text
valid_from <= evaluated_at < valid_until
```

The credential evaluation must not occur after the adjudication it authorizes.

## Successor-manifest boundary

The credential-bound corpus is a compact successor manifest:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-bound@1.10.0
```

It binds:

- the exact immutable `1.9.0` adjudication-bound predecessor;
- the unchanged `1.8.0` witness predecessor reference;
- the unchanged `1.7.0` checkpoint predecessor reference;
- the exact conflict-adjudicator registry;
- the exact adjudication policy and adjudication record;
- the unchanged witness registry, witness policy, and ordered witness attestations;
- the exact issuer registry;
- the exact credential policy;
- the exact ordered credential population;
- the unchanged ordered content population.

Publication remains manifest-last:

1. issuer registry;
2. credential policy;
3. immutable credential attestation;
4. compact `1.10.0` successor manifest.

No `1.9.0`, `1.8.0`, `1.7.0`, witness, adjudication, checkpoint, revocation, reviewer, analyzer, or content artifact is edited.

## Three-outcome separation

The layer preserves three independent facts:

```text
witness outcome       -> what the required named witnesses reported
adjudication outcome  -> what accepted adjudication authority selected
credential outcome    -> whether that authority was eligible to act then
```

A credential `execute` decision does not replace the adjudication decision. An adjudication `execute` decision does not replace a witness `abstain` decision. Each result remains bound to its own evidence and question.

For the canonical no-conflict graph:

```text
credential_outcome        = execute
checkpoint_witness_outcome = execute
resolution_status          = not_required
adjudication_outcome       = execute
terminal_outcome           = execute
```

For an ineligible credential:

```text
credential_outcome        = abstain
checkpoint_witness_outcome = null
resolution_status          = null
adjudication_outcome       = null
terminal_outcome           = abstain
```

No PR #31 adjudication decision or final is created after credential abstention.

## Explicit scope transition

The complete scope transition is:

```text
1.10.0 plan -> credential validation, decision persistence, outer finalization
1.9.0 plan  -> unchanged PR #31 adjudication lifecycle
1.8.0 receipt -> immutable original witness outcome and attestations
1.7.0 plan or receipt -> lower checkpoint, revocation, and downstream lifecycle
```

Experiment identity, version, content IDs, content order, candidate population, analyzer population, execution windows, and every prior governance artifact remain unchanged.

Only the corpus reference is explicitly narrowed after the credential decision authorizes the next immutable layer.

## Runner ordering

The credential-gated runner performs:

1. exact frozen-plan, corpus, authority, run, content-order, and chronology preflight;
2. storage-backed loading and hash verification of the complete credential graph;
3. exact credential evaluation at the declared pre-adjudication time;
4. run-specific credential-decision persistence and reread verification;
5. terminal credential abstention or delegation to the unchanged PR #31 runner;
6. outer final-manifest persistence;
7. storage-backed reread of the final, corpus, issuer, policy, credential, adjudication record, credential decision, predecessor corpus, and optional delegated adjudication final.

A credential abstention terminates before PR #31's adjudication decision, adjudication final, lower checkpoint execution, revocation evaluation, reviewer governance, or analyzers.

## Failure and abstention boundaries

Structural failure includes:

- a non-frozen or mismatched experiment plan;
- a substituted `1.9.0` predecessor;
- drift in the preserved `1.9.0`, `1.8.0`, or `1.7.0` authority graph;
- substituted adjudicator, issuer, policy, adjudication, or credential references;
- altered credential population or order;
- unknown adjudicator or issuer IDs;
- adjudicator identity-revision drift;
- issuer-revision drift;
- role or credential-type mismatch;
- subject-reference mismatch;
- duplicate credential subjects;
- impossible witness, credential, adjudication, or completion chronology;
- credential evaluation after adjudication;
- append, reread, serialization, or storage-integrity failure;
- delegated PR #31 receipt drift.

Structural failure produces no governed credential decision.

Governed abstention includes:

- credential not yet valid at the declared evaluation time;
- credential expired at the declared evaluation time;
- credential status suspended;
- credential status revoked;
- inactive issuer when the declared graph remains structurally coherent and policy requires abstention;
- any later PR #31 or lower-layer abstention after credential authorization.

A later adjudication or lower-layer abstention remains separate from credential `execute`.

## Consequences

### Positive

- conflict-adjudication authority is no longer implied merely by registry membership;
- exact identity revision, role, issuer, credential type, and validity window are independently inspectable;
- temporal authorization is checked before the decision it authorizes;
- an expired or not-yet-valid credential prevents adjudication execution without rewriting any preserved evidence;
- the existing generic adjudicator credential grammar and engine are reused rather than forked;
- `1.10.0`, `1.9.0`, `1.8.0`, and `1.7.0` scopes remain explicit and testable;
- witness disagreement and adjudication dissent remain visible after credential authorization.

### Costs

- callers must carry another issuer registry, policy, credential population, evaluation time, decision artifact, and successor manifest;
- the graph proves only declared issuer-bound authorization, not legal identity or trustworthiness;
- credential revocation history is not yet append-only or independently checkpointed;
- exact chronology becomes another fail-closed integration boundary.

## Non-claims

Verification does not establish:

- legal or real-world adjudicator identity;
- legal or real-world issuer identity;
- cryptographic authorship or possession of a private key;
- trusted external time;
- issuer trustworthiness, authority, independence, or competence;
- adjudicator independence, competence, honesty, or correctness;
- that the adjudicator's selected checkpoint head was correct in the real world;
- that any witness was correct or incorrect;
- witness identity, independence, competence, or truthfulness;
- credential non-revocation outside the attestation's declared status;
- public availability or global checkpoint uniqueness;
- majority support, quorum, consensus, confidence, or reputation;
- complete real-world event disclosure;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred work

The next bounded layer may add an append-only, time-relative revocation ledger for this exact credential and authority without changing the credential, adjudication, witness abstention, fork evidence, dissent, rationale, or selected checkpoint head.

Credential checkpoints, credential witnesses, credential-conflict adjudication, signatures, keys, identity providers, external timestamp authorities, and live transparency services remain separate future decisions.
