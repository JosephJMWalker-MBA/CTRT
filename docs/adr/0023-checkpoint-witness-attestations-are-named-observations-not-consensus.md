# ADR-0023: Checkpoint witness attestations are named observations, not consensus

- **Status:** Accepted
- **Date:** 2026-08-03

## Context

ADR-0022 introduced immutable sequential checkpoints for a frozen credential-revocation ledger. Those checkpoints make the supplied publication history internally inspectable and detect omission, reordering, rollback, stale heads, and broken predecessor continuity within that supplied history.

Checkpoint continuity alone does not establish that any independent observer saw the checkpoint. A publisher could present one internally consistent checkpoint history to one consumer and a different internally consistent history elsewhere. CTRT therefore needs a bounded way to preserve claims that identified observers saw a particular checkpoint head.

This layer must not turn witness counts into truth. Three witnesses can all be mistaken, coordinated, or controlled by the same operator. One witness reporting a different head is evidence that must remain visible even when several other witnesses report the declared head.

## Decision

CTRT will represent checkpoint witnessing as immutable, named observations governed by a frozen registry and policy.

Each witness record contains only:

- a stable witness identifier;
- an immutable identity revision;
- an authorized checkpoint-observer role.

Each witness attestation binds:

- the exact checkpoint-bound predecessor corpus;
- the exact checkpoint log;
- the exact declared checkpoint head;
- the exact head the witness claims to have observed;
- the witness identity and identity revision;
- observation and receipt timestamps;
- a human-readable note;
- a derived observation kind: `matches_head` or `conflicting_head`.

The observation kind is not supplied independently of the references. Equal expected and observed head references produce `matches_head`; unequal references produce `conflicting_head`.

The initial accepted witness policy:

- names every required witness explicitly;
- requires one attestation from each named witness in registry order;
- abstains when any structurally valid witness attestation reports a conflicting head;
- forbids vote aggregation.

A single conflicting-head observation therefore produces a governed witness abstention even when multiple other witnesses match the declared head.

## Separation of claims

The witness layer makes a narrower claim than checkpoint validation and a different claim from downstream governance.

Checkpoint validation asks:

> Is the supplied checkpoint history internally continuous and bound to the current supplied ledger?

Witness validation asks:

> What exact checkpoint head does each named witness claim to have observed?

Credential revocation asks:

> What credential status follows from the frozen revocation ledger as of the experiment timestamp?

These claims remain separate artifacts and separate lifecycle stages.

A witness conflict is not checkpoint corruption. The checkpoint chain may be structurally valid while one witness reports another head. That situation yields a verified witness abstention, preserving both the valid checkpoint report and the conflicting witness evidence.

Malformed identity, reference, timestamp, or attestation provenance remains structural failure rather than governed abstention.

## Execution semantics

The witness-gated runner performs these stages in order:

1. preflight exact plan, corpus, policy, and execution-window binding;
2. load and reverify stored witness evidence;
3. load and reverify the stored checkpoint chain;
4. validate and persist the run-specific checkpoint verification report;
5. validate named witness attestations;
6. persist the run-specific witness decision;
7. either abstain or delegate the existing checkpoint-gated lifecycle;
8. persist and reverify the final witness-gated artifact.

The run-specific witness decision is stored at:

```text
<experiment-run-id>:checkpoint-witness-decision
```

A deterministic plan-level index remains available for discovery without replacing the run-specific record.

### Witness abstention

When any required witness reports a conflicting head:

- the checkpoint chain has already been reverified;
- the checkpoint verification report is persisted;
- the witness decision is persisted;
- every matching and conflicting observation remains visible;
- no revocation decision is created;
- no credential, review, quality, or analyzer execution occurs;
- the final artifact is:

```text
<experiment-run-id>:checkpoint-witness-abstention
```

### Witness-permitted execution

When all required witnesses report the declared head, the existing checkpoint-gated lifecycle runs unchanged. It can still independently abstain because of credential revocation or another downstream governance boundary.

Successful downstream execution produces:

```text
<experiment-run-id>:checkpoint-witness-completion
```

Successful witness authorization followed by downstream abstention produces:

```text
<experiment-run-id>:checkpoint-witness-terminal-abstention
```

That terminal artifact does not mean the witness layer abstained. It preserves the witness outcome separately from the downstream terminal outcome.

## Append-only corpus evolution

The checkpoint-bound `0.7.0` corpus and witness-bound `0.8.0` corpus use distinct artifact identities.

The `0.8.0` corpus retains the complete prior governance graph and adds exact references to:

- the `0.7.0` predecessor corpus;
- the witness registry;
- the witness policy;
- the ordered witness-attestation population.

The registry, policy, and attestations are persisted before the `0.8.0` corpus manifest is written last.

A partial witness graph can remain in append-only storage after failure, but it cannot claim a complete witness-bound corpus unless the final manifest exists and reconstructs exactly.

## Privacy boundary

The initial witness records deliberately exclude:

- names;
- addresses;
- government identifiers;
- biometrics;
- private credential material;
- network location;
- organizational secrets.

The witness identifier and revision are governance identities inside the synthetic corpus. They do not establish a person's real-world identity.

## Meaning of verified

`verified` means CTRT checked and rechecked the exact supplied relationships among:

- the experiment plan;
- witness-bound corpus;
- checkpoint policy, log, and head;
- witness registry and policy;
- witness identity revisions;
- witness attestations;
- observation and receipt timestamps;
- run-specific checkpoint and witness reports;
- final execution or abstention artifact.

It does not establish:

- real-world witness identity;
- witness independence;
- witness honesty or competence;
- cryptographic authorship;
- that every witness saw every checkpoint;
- that no other checkpoint fork exists;
- that every checkpoint or revocation event was disclosed;
- global transparency-log consistency;
- trusted external time;
- extraction or analyzer accuracy;
- content quality;
- an aggregate CTRT score.

## Consequences

### Positive

- Conflicting-head evidence is preserved rather than averaged away.
- A single named conflict cannot be outvoted by matching witnesses.
- Witness claims are independently inspectable and append-only.
- Checkpoint continuity and external observation remain separate claims.
- Downstream governance outcomes remain independently attributable.
- The implementation remains dependency-free and testable with synthetic artifacts.

### Negative

- Registry identity is not externally authenticated.
- The system cannot prove witnesses are independent.
- A witness can lie or fail to report a fork.
- The system does not discover witnesses or retrieve observations over a network.
- The initial policy fails closed on any conflicting head and provides no adjudication mechanism.

## Intentionally deferred

- cryptographic signatures;
- issuer and witness key rotation;
- live witness networks or gossip;
- transparency-log inclusion and consistency proofs;
- external timestamp authorities;
- witness independence attestations;
- conflicting-witness adjudication;
- fork reconciliation;
- network publication, monitoring, or alerting;
- real identity providers;
- private identity attributes;
- real reviewers, witnesses, models, extractors, or datasets.
