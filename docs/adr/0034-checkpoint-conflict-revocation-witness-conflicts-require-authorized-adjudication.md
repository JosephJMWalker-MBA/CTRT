# ADR-0034: Checkpoint-conflict revocation witness conflicts require authorized adjudication

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0033 bound immutable named-witness observations to the exact `1.7.0` checkpoint protecting the revocation ledger for the credential of a checkpoint-conflict adjudicator.

That layer intentionally abstains when any policy-required witness reports a conflicting checkpoint head. It preserves every observation separately and forbids majority vote, quorum, reputation weighting, confidence percentages, and other numerical aggregation.

A witness abstention is therefore valid evidence that the required observation population did not uniformly report the same checkpoint head. It is not a determination that the checkpoint is invalid, that the conflicting witness is correct, or that the other witnesses are correct.

The next bounded question is:

> Did the exact accepted adjudicator and policy resolve the preserved witness conflict by selecting the independently verified checkpoint head?

This question must remain separate from:

- whether the checkpoint itself is structurally valid;
- what each named witness reported;
- whether the adjudicator has a valid external credential;
- whether the selected result is correct in the real world;
- whether any witness population forms a majority or consensus.

## Decision

CTRT will add a distinct authorized conflict-adjudication layer over the exact immutable `1.8.0` witness-bound corpus.

The layer will:

1. use a frozen registry of stable pseudonymous adjudicator IDs, immutable identity revisions, and the declared `witness_conflict_adjudicator` role;
2. use an accepted fail-closed policy requiring the exact adjudicator population and order;
3. bind one immutable adjudication record to the exact witness predecessor corpus, witness registry, witness policy, checkpoint head, adjudicator registry, and adjudication policy;
4. preserve the original witness decision without changing `execute` or `abstain`;
5. preserve every conflicting observation as fork evidence;
6. preserve dissent after a decision rather than deleting or recasting it;
7. distinguish `not_required`, `pending`, `resolved`, and `unresolved` states;
8. permit downstream checkpoint execution only for `not_required` or a structurally valid `resolved` decision;
9. require a `resolved` decision to select the independently verified checkpoint head;
10. require `pending` and `unresolved` decisions to terminate in governed abstention;
11. persist the adjudication decision before any lower checkpoint execution;
12. forbid witness counts, majority vote, quorum, confidence, reputation, or consensus from acting as authority.

A resolved adjudication does not rewrite the prior witness abstention. It adds a narrower operational claim:

> An accepted adjudication authority selected the independently verified checkpoint head while preserving the original fork and dissent.

## Canonical fixed graph

The published canonical `1.8.0` witness graph contains three matching observations. Its canonical adjudication state is therefore `not_required`.

The canonical record exists to prove that the adjudication layer can preserve a clean witness outcome without manufacturing a conflict or changing the lower execution path.

`pending`, `unresolved`, and `resolved` conflicts are generated as immutable test variants. Those variants bind their adjudication records to the exact dynamically conflicted `1.8.0` predecessor used by the preserved witness receipt.

This distinction prevents a conflict adjudication from claiming authority over a different witness graph merely because the witness IDs and checkpoint head appear similar.

## Successor-manifest boundary

The adjudication-bound corpus is a compact successor manifest:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound@1.9.0
```

It binds:

- the exact immutable `1.8.0` witness-bound predecessor;
- the exact accepted conflict-adjudicator registry;
- the exact accepted adjudication policy;
- the exact immutable adjudication record;
- the unchanged ordered witness authority and attestation population;
- the unchanged ordered content population.

Publication remains manifest-last:

1. conflict-adjudicator registry;
2. adjudication policy;
3. immutable adjudication record;
4. compact `1.9.0` successor manifest.

No `1.8.0`, `1.7.0`, witness, checkpoint, revocation, credential, or content artifact is edited.

## State semantics

### `not_required`

All required named witnesses reported the independently verified checkpoint head.

The original witness outcome remains `execute`. The adjudication outcome is separately `execute`, and the already verified PR #30 checkpoint receipt is reused without rerunning or rewriting the witness layer.

### `pending`

A structurally valid witness conflict exists, but no authorized adjudication decision has been completed.

The original witness outcome remains `abstain`. The adjudication outcome is `abstain`, and no lower checkpoint execution is permitted.

### `unresolved`

An accepted adjudicator reviewed the preserved conflict but did not authorize a selected head.

The original witness outcome remains `abstain`. Fork evidence and dissent remain visible. The adjudication outcome is `abstain`, and no lower checkpoint execution is permitted.

### `resolved`

An accepted adjudicator selected the independently verified checkpoint head under the accepted policy.

The original witness outcome remains `abstain`. Fork evidence and dissent remain visible. The adjudication outcome is separately `execute`, allowing the exact lower checkpoint lifecycle to run.

The selected head may not be substituted with a conflicting observed head or an undeclared artifact.

## Receipt-preservation boundary

The outer adjudication runner consumes a verified PR #30 witness receipt as immutable input evidence.

It does not rerun PR #30 to obtain a more convenient witness result. It revalidates:

- the exact `1.8.0` witness predecessor;
- the exact attestation population and order;
- the stored witness decision;
- the stored witness final;
- the exact witness outcome;
- the exact experiment identity and content order.

For `not_required`, the runner reuses the lower checkpoint receipt already contained in the PR #30 receipt.

For a valid `resolved` conflict, the PR #30 receipt has no lower checkpoint receipt because the witness layer correctly abstained. The runner may then invoke an explicit typed checkpoint executor with a plan narrowed to the exact immutable `1.7.0` checkpoint predecessor.

## Explicit plan-scope transition

The complete scope transition is:

```text
1.9.0 plan -> adjudication validation, decision persistence, outer finalization
1.8.0 receipt -> immutable original witness outcome and attestations
1.7.0 derived plan -> lower checkpoint, revocation, and downstream lifecycle
```

Experiment identity, version, content IDs, content order, candidate population, analyzer population, execution windows, and every prior governance artifact remain unchanged.

Only the corpus reference is explicitly narrowed when a valid resolved adjudication authorizes the lower checkpoint lifecycle.

## Failure and abstention boundaries

Structural failure includes:

- non-frozen or mismatched experiment plans;
- substituted `1.8.0` predecessor references;
- witness-receipt run, experiment, version, content, or artifact drift;
- altered witness decisions or finals;
- substituted adjudicator registries, policies, or records;
- adjudication bound to a different witness predecessor;
- fork evidence that differs from the preserved witness observations;
- missing or altered dissent;
- unknown adjudicator ID, identity-revision drift, or role drift;
- a resolved decision selecting anything other than the verified checkpoint head;
- impossible witness, adjudication, or completion chronology;
- append, reread, serialization, or storage-integrity failure;
- a delegated checkpoint receipt with different experiment scope.

Governed abstention includes:

- `pending` conflict adjudication;
- `unresolved` conflict adjudication;
- any later lower-layer abstention after a valid `not_required` or `resolved` adjudication.

An adjudication abstention is terminal. The lower checkpoint lifecycle, revocation evaluation, credential evaluation, earlier adjudication layers, reviewer governance, and analyzers must not run afterward.

A later lower-layer abstention remains separate from an adjudication `execute` decision.

## Consequences

### Positive

- witness disagreement remains visible after authorized resolution;
- operational authorization no longer depends on numerical witness agreement;
- a resolved case can proceed without pretending the witnesses agreed;
- `pending`, `unresolved`, and `resolved` become inspectable lifecycle states;
- exact predecessor binding prevents adjudication from drifting to a different witness graph;
- the existing generic conflict-adjudication grammar is reused rather than forked;
- `1.9.0`, `1.8.0`, and `1.7.0` plan and receipt scopes remain explicit and testable.

### Costs

- callers must carry another registry, policy, adjudication record, evaluation boundary, and successor manifest;
- a resolved conflict requires an explicit lower checkpoint executor because PR #30 correctly stopped before that stage;
- stable pseudonymous JSON identities do not prove legal identity, competence, independence, or authorship;
- accepted adjudication authority can permit execution despite a preserved witness conflict, so its credential status requires separate governance.

## Non-claims

Verification does not establish:

- legal or real-world adjudicator identity;
- adjudicator credential validity, non-revocation, independence, competence, honesty, or correctness;
- witness identity, independence, truthfulness, or competence;
- cryptographic authorship;
- trusted external time;
- public availability or global checkpoint uniqueness;
- that the dissenting witness was wrong;
- that matching witnesses were correct;
- majority support, quorum, consensus, confidence, or reputation;
- complete real-world event disclosure;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred work

The next bounded layer may attest that the exact pseudonymous identity revision resolving a `1.9.0` conflict was authorized for the exact role at the declared time.

Credential revocation, credential checkpoints, credential witnesses, signatures, keys, identity providers, external timestamp authorities, and live transparency services remain separate future decisions.
