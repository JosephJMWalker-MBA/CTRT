# ADR-0043: Checkpoint-fork adjudicator revocation checkpoints require named witness observations

- Status: Accepted
- Date: 2026-08-04
- Decision owners: CTRT Phase 1A governance
- Predecessor: ADR-0042

## Context

ADR-0042 establishes an immutable checkpoint over the exact frozen `1.16.0`
revocation ledger. That checkpoint proves which declared ledger head a governed
execution relied upon. It does not prove that independent parties observed the
same head.

A checkpoint can be internally valid while different observers receive or
report different heads. Treating publication as universal observation would
collapse two distinct claims:

1. the declared checkpoint chain is structurally valid; and
2. every required named observer reported the same exact checkpoint head.

CTRT must preserve those claims separately.

## Decision

Add an append-only `1.18.0` witness layer over the exact immutable `1.17.0`
checkpoint corpus.

The layer contains:

- an accepted registry of required pseudonymous witnesses and exact identity
  revisions;
- an accepted policy binding that exact registry and required witness order;
- one immutable attestation from every required witness;
- the exact expected checkpoint corpus, checkpoint log, and head references;
- the exact observed head reference reported by each witness;
- separate observation and receipt timestamps;
- a compact witness-bound successor published after all witness artifacts.

The witness decision is derived only after every required observation is loaded
and preserved.

## No-majority rule

The policy requires all named witnesses and forbids vote aggregation.

```text
match + match + match    -> execute
match + match + conflict -> abstain
```

Two matching observations do not outvote one required conflict. A conflict is
not converted into a minority opinion, confidence penalty, reputation score, or
weighted average.

The abstention protects the narrower operational claim: the required witness
population did not uniformly report the exact declared head.

## Observation preservation

Every observation remains independently inspectable, including:

- witness ID;
- witness identity revision;
- expected checkpoint corpus and log;
- expected head;
- observed head;
- observation kind;
- observation time;
- receipt time;
- note;
- immutable artifact reference and hash.

The decision report summarizes the population without replacing or rewriting
any attestation.

## Structural failure versus governed abstention

The layer distinguishes malformed evidence from valid disagreement.

Structural failure includes:

- missing required witnesses;
- duplicate witnesses or attestations;
- witness identity-revision substitution;
- registry, policy, predecessor, log, or attestation-reference drift;
- observation before checkpoint publication;
- receipt before observation;
- canonical serialization or stored-artifact drift.

A valid required witness that reports a different exact head produces governed
abstention rather than structural failure.

## Execution order

The outer lifecycle performs:

1. exact `1.18.0` plan and predecessor preflight;
2. storage-backed witness and checkpoint evidence loading;
3. exact `1.17.0` checkpoint reverification;
4. run-specific checkpoint-report persistence;
5. current named-witness validation;
6. run-specific witness-decision persistence;
7. exact `1.18.0 -> 1.17.0` plan narrowing only after witness execution;
8. unchanged PR #39 execution under the same experiment run ID;
9. outer final persistence and complete storage reread.

A current witness abstention persists the checkpoint report and witness decision
but creates no PR #39 receipt or final artifact.

## Independent outcomes

The final record keeps these claims separate:

```text
current witness outcome
current checkpoint status
current revocation outcome
current credential outcome
current conflict-witness outcome
current conflict adjudication outcome
predecessor witness outcome
inherited checkpoint, revocation, credential, witness, and adjudication outcomes
terminal outcome
```

No later result retrospectively changes an earlier observation or decision.

## Canonical execution

The canonical synthetic population contains three matching observations and
therefore authorizes delegation to exact PR #39.

The conflict path is tested by replacing one immutable gamma observation and the
corresponding exact successor reference. That test proves fail-closed behavior
without embedding disagreement into the canonical all-matching corpus.

## Consequences

### Positive

- observation and checkpoint integrity remain distinct claims;
- every required witness is named and revision-bound;
- disagreement cannot be hidden by majority aggregation;
- checkpoint and witness reports survive downstream abstention;
- exact run identity and plan narrowing remain auditable;
- later conflict adjudication can operate over preserved original evidence.

### Costs

- the authority graph gains another explicit layer;
- every required observation must be stored and reverified;
- one required conflict halts execution until a later governed resolution layer;
- long artifact identities require careful local aliases without weakening public
  names.

## Trust boundary

This decision does not establish:

- legal or real-world witness identity;
- cryptographic authorship, signatures, or key possession;
- trusted external time;
- witness independence, competence, honesty, or correctness;
- that the observed head is externally true or globally unique;
- checkpoint-chain or ledger completeness;
- absence of undisclosed events, alternate ledgers, or alternate checkpoint
  chains;
- majority support, quorum, consensus, confidence, reputation, or trust;
- correctness of any inherited adjudication or selected head;
- extraction, analyzer, model, dataset, or content accuracy;
- an aggregate CTRT score.

## Deferred successor

A later bounded layer may add authorized conflict adjudication over the exact
`1.18.0` witness observations. It must preserve:

- every original attestation;
- the original current-witness abstention;
- the exact `1.17.0` checkpoint report and head;
- the `1.16.0` revocation decision;
- the `1.15.0` credential graph;
- the complete `1.14.0` disagreement and adjudication record;
- all fork evidence, dissent, rationale, selected heads, and inherited artifacts.

Adjudication may authorize a response to disagreement. It may not rewrite the
disagreement itself.
