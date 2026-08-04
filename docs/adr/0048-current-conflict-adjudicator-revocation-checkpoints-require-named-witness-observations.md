# ADR-0048: Current conflict-adjudicator revocation checkpoints require named-witness observations

- Status: Accepted
- Date: 2026-08-04
- Scope: Phase 1A synthetic current checkpoint-witness conflict authority chain

## Context

PR #44 added an immutable checkpoint over the exact frozen `1.21.0` revocation ledger governing the credential of the adjudicator that resolved the preserved current checkpoint-witness conflict.

That layer answers:

> Which exact frozen `1.21.0` revocation-ledger head did governed execution rely upon before evaluating the current conflict-adjudicator credential status?

Structural checkpoint verification does not record what independently named observers reported about that exact checkpoint head. A further bounded layer is required to preserve those observations without converting them into consensus, confidence, reputation, or truth.

## Decision

Add a compact `1.23.0` witness-bound successor over the exact immutable `1.22.0` checkpoint corpus.

The successor binds:

- the exact immutable `1.22.0` predecessor;
- one accepted ordered registry of required pseudonymous witnesses;
- one accepted fail-closed witness policy;
- the exact ordered immutable attestation population;
- unchanged ordered content IDs;
- one publication timestamp.

The established provider-neutral adjudicator checkpoint-witness grammar remains authoritative for witness identity revisions, required order, expected and observed heads, observation kinds, chronology, abstention, decision reports, and storage.

The context adapter adds only exact `1.22.0` binding, compact `1.23.0` parsing, and manifest-last publication through the current authority chain.

## Fixed witness graph

### Registry

```text
registry.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:2d0fe7764d111f480fd556b62357725d0ba5997e7abcce5dfa7057b398f18eb9
```

Required order:

```text
alpha
beta
gamma
```

Each entry binds a stable pseudonymous witness ID, the exact identity revision:

```text
synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness@0.1.0
```

and role:

```text
checkpoint_observer
```

### Policy

```text
policy.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:b9f2a86df193ba17900b1c682b5526002ab775a810bbbf704a2c382c3f36fdab
```

The policy requires the complete ordered registry, abstains on any required conflicting head, and forbids vote aggregation.

### Exact checkpoint under observation

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.22.0
sha256:3ef12c528781ddec9976323b8a23670f3592839ce2145afed60cda39170c0304
```

Exact head:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:546847de7b5557ae3a12c9e7b7d222b5bca0212168e793c09ce68363b0029d6b
```

### Canonical observations

```text
alpha = sha256:5971087e0b9cc985b7349f486780c7fbaf1420c2469fa20f0fa8a4d1c19751fc
beta  = sha256:f655cfbeff98550eb8fdbb7516fc5e89246e3547a0ae2c8d2cca95a6b6c15945
gamma = sha256:1d0d661270308e4d7b13e2e42ecaf0bec9124aff309bc35aa36caab1a597ae36
```

Each canonical observation reports `matches_head`. Conflicting observations are introduced as new immutable evidence in tests and future successors; canonical observations are never edited.

### Successor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.23.0
sha256:73cc89c16ebb72c07ec7731ae1b25c3981681eb590005c8fe66c953facca4666
```

## No-majority rule

```text
match + match + match    -> execute
match + match + conflict -> abstain
```

Two matching required witnesses cannot outvote one required conflict. The conflict remains an independently preserved observation rather than becoming a minority label, confidence reduction, weighted vote, or reputation adjustment.

## Chronology

```text
2026-08-03T19:58:21Z  1.22.0 checkpoint successor published
2026-08-03T19:58:22Z  witness registry created
2026-08-03T19:58:23Z  witness policy created
2026-08-03T19:58:24Z  alpha observed
2026-08-03T19:58:25Z  alpha received; beta observed
2026-08-03T19:58:26Z  beta received; gamma observed
2026-08-03T19:58:27Z  gamma received
2026-08-03T19:58:29Z  1.23.0 witness successor published
2026-08-03T19:58:30Z  exact 1.22.0 checkpoint reverified
2026-08-03T19:58:31Z  current witness population evaluated
```

Before delegation, the outer lifecycle requires:

```text
1.23.0.created_at
  <= witness_checkpoint_verified_at
  <= current_witness_evaluated_at
  <= delegated 1.22.0 checkpoint verification
  <= current conflict-adjudicator revocation evaluation
  <= delegated completion
  <= outer completion
```

## Execution order

```text
1.23.0 witness graph loading
  -> exact 1.22.0 checkpoint reverification
  -> checkpoint report persistence
  -> named-witness validation
  -> witness decision persistence
  -> witness abstention or exact 1.22.0 plan derivation
  -> unchanged PR #44 lifecycle
  -> outer finalization
```

The experiment run ID, experiment identity, version, parameters, content order, and inherited evidence remain unchanged.

## Independent claims

This layer preserves separately:

```text
current revocation-checkpoint witness outcome
current conflict-adjudicator revocation outcome
current conflict-adjudicator credential outcome
preserved conflicting witness outcome
current resolution and conflict-adjudication outcomes
resolved current witness outcome
all lower and inherited governance outcomes
terminal outcome
```

No later result rewrites an earlier observation, checkpoint, authority, or status claim.

## Structural failure versus governed abstention

A valid required conflicting observation produces governed abstention. The checkpoint report and witness decision remain stored, and PR #44 is not invoked.

Predecessor, content-order, registry, policy, identity-revision, attestation-order, checkpoint-log, checkpoint-head, chronology, run-identity, stored-artifact, or canonical-serialization drift is structural failure.

## Consequences

### Positive

- execution records what each required named witness reported about the exact `1.22.0` head;
- every observation remains independently inspectable;
- one required disagreement cannot be hidden by aggregation;
- checkpoint verification and witness observation remain separate claims;
- witness execution remains visible if a later revocation boundary abstains;
- the provider-neutral witness grammar is reused rather than forked.

### Costs

- the authority chain adds another compact successor and outer lifecycle;
- real-chain tests require the complete inherited evidence graph;
- chronology must distinguish observation, receipt, checkpoint reverification, witness evaluation, delegated checkpoint verification, and downstream completion.

## Trust boundary

This layer does not establish legal or real-world witness identity, cryptographic authorship, signatures, key possession, trusted external time, witness independence, competence, honesty, or correctness, checkpoint or ledger completeness, absence of undisclosed events or alternate chains, global uniqueness, public availability, external truth, majority support, quorum, consensus, confidence, reputation, analytical accuracy, deployment, or an aggregate CTRT score.

## Deferred work

The next bounded successor may add authorized conflict adjudication over an exact conflicting `1.23.0` witness population.

It must preserve every original observation, the original witness abstention, the exact `1.22.0` checkpoint report and head, the complete `1.21.0` revocation graph, fork evidence, dissent, selected heads, rationale, and every inherited artifact unchanged.
