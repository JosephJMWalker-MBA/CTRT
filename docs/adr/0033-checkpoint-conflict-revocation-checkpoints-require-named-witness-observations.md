# ADR-0033: Checkpoint-conflict revocation checkpoints require named witness observations

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0032 introduced an immutable checkpoint over the exact frozen revocation-ledger head used to determine the operational status of the credential authorizing a checkpoint-conflict adjudicator.

That checkpoint proves an internally consistent publication claim under the accepted checkpoint policy. It does not show whether any separately named observer reported seeing the same checkpoint head.

Treating witness reports as a vote would collapse distinct claims:

- a witness can report a matching head;
- another witness can report a conflicting head;
- the checkpoint can remain structurally valid while the observation population conflicts;
- numerical agreement does not identify which observation is correct.

The next bounded question is therefore:

> Did every policy-required named witness report the exact independently verified checkpoint head?

## Decision

CTRT will bind immutable named-witness attestations to the exact `1.7.0` checkpoint corpus, frozen checkpoint log, and checkpoint head.

The layer will:

1. use a frozen registry of stable pseudonymous witness IDs, immutable identity revisions, and declared roles;
2. require the exact witness population and order declared by policy;
3. bind every attestation to the exact checkpoint corpus, log, expected head, observed head, observation kind, observation time, and receipt time;
4. reject identity revision drift, population drift, reference drift, impossible chronology, observation before checkpoint publication, and unsupported fields as structural failure;
5. preserve every named observation separately;
6. execute only when every required observation is `matches_head`;
7. abstain when any required observation reports a conflicting head;
8. forbid majority vote, quorum, confidence percentages, reputation weighting, and other aggregation;
9. persist checkpoint verification and the witness decision before any delegated revocation or downstream work;
10. preserve a valid witness abstention as a terminal outcome without modifying the checkpoint or any attestation.

A witness conflict does not invalidate the underlying checkpoint artifact. It establishes that the required observation population did not uniformly report that exact head.

## Successor-manifest boundary

The witness-bound corpus is a compact successor manifest:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.8.0
```

It binds:

- the exact canonical `1.7.0` checkpoint-bound predecessor;
- the exact accepted witness registry;
- the exact accepted witness policy;
- the exact ordered immutable attestation population;
- the unchanged ordered content population.

Publication is manifest-last:

1. witness registry;
2. witness policy;
3. immutable attestations;
4. compact `1.8.0` successor manifest.

No predecessor artifact is edited.

## Explicit plan-scope delegation

The outer witness runner receives a frozen plan bound to `1.8.0`.

It independently reloads and revalidates the exact `1.7.0` checkpoint evidence before evaluating witness observations.

When every required witness matches, it derives a narrowly scoped nested plan bound to the exact immutable `1.7.0` predecessor and invokes the unchanged ADR-0032 runner:

```text
1.8.0 plan -> checkpoint reverification, witness decision, outer finalization
1.7.0 derived plan -> unchanged checkpoint, revocation, and downstream lifecycle
```

Experiment identity, version, content IDs, content order, candidate population, analyzer population, execution windows, and prior governance evidence remain unchanged. Only the corpus reference is explicitly narrowed to the predecessor required by the delegated runner.

## Failure and abstention boundaries

Structural failure includes:

- plan or content-order drift;
- substituted registry, policy, corpus, log, checkpoint, or attestation references;
- missing, duplicate, reordered, or unknown witnesses;
- identity revision drift;
- inconsistent observation kind and observed head;
- observation before checkpoint publication;
- receipt before observation;
- evaluation before receipt;
- missing or altered stored artifacts;
- persistence or reread failure.

Governed abstention includes:

- any structurally valid policy-required attestation reporting a conflicting checkpoint head.

A current-layer witness abstention is terminal. The ADR-0032 runner, revocation decision, credential evaluation, earlier witness and adjudication layers, reviewer governance, and analyzers must not run afterward.

If every current witness matches but a later delegated layer abstains, the current witness decision remains `execute` and the later abstention remains separately visible.

## Consequences

### Positive

- externally oriented observations become inspectable without being mistaken for checkpoint validity;
- disagreement is preserved by witness identity rather than collapsed into a count;
- one conflict cannot be outvoted by two matches;
- checkpoint verification, witness observation, revocation status, credential authorization, adjudication, and analytical execution remain separate claims;
- exact `1.8.0`/`1.7.0` plan scope is explicit and testable;
- the established witness grammar is reused rather than forked.

### Costs

- callers must carry another registry, policy, attestation population, evaluation timestamp, and successor manifest;
- the outer runner must preserve both witness and delegated checkpoint outcomes;
- named JSON attestations do not prove legal identity, independence, authorship, or real-world observation;
- a required conflicting witness causes abstention even when every other witness matches.

## Non-claims

Verification does not establish:

- legal or real-world witness identity;
- witness independence, honesty, competence, or trustworthiness;
- cryptographic authorship;
- trusted external time;
- public availability or global checkpoint uniqueness;
- which conflicting witness is correct;
- majority support, quorum, consensus, confidence, or reputation;
- complete real-world event disclosure;
- adjudicator correctness;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred work

A future bounded layer may authorize an adjudicator to resolve a conflict among these exact witness observations while preserving the original witness decision and every dissenting attestation. Signatures, keys, identity providers, external timestamp authorities, and live transparency services remain separate future decisions.
