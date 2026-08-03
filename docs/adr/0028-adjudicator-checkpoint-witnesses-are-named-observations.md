# ADR-0028: Adjudicator checkpoint witnesses are named observations

- Status: Accepted
- Date: 2026-08-03

## Context

ADR-0027 publishes immutable prefix-proof checkpoints over adjudicator credential revocation ledgers. Those checkpoints detect omission, reordering, stale heads, and rollback inside the exact frozen artifact graph.

A checkpoint publisher may still present different heads to different observers. The checkpoint chain alone does not record what independent parties claim to have seen. CTRT therefore needs a separate witness-evidence layer without treating witness counts as truth, rewriting the checkpoint chain, or introducing signatures and a live transparency network.

## Decision

CTRT preserves immutable named witness attestations over the exact adjudicator revocation checkpoint corpus, log, and head.

Each attestation binds:

- a stable pseudonymous witness ID;
- the exact witness identity revision and observer role;
- the exact checkpoint-bound predecessor corpus;
- the exact checkpoint log;
- the expected checkpoint head;
- the head the witness claims to have observed;
- an observation kind derived from exact reference equality;
- observation and receipt timestamps;
- a human-readable note.

An accepted witness policy names every required witness in exact registry order, requires abstention on a conflicting head, and forbids vote aggregation.

Every required witness must provide exactly one structurally valid attestation. The witness decision preserves every named observation separately.

If every observed head equals the independently verified checkpoint head, the witness layer delegates to the unchanged checkpoint-gated adjudicator revocation runner.

If any required witness reports a conflicting head, the result is a verified governed abstention before adjudicator revocation, credential evaluation, earlier witness adjudication, reviewer governance, or analyzer execution.

Two matching witnesses cannot outvote one conflicting witness. The number of matching observations never converts conflict into execution.

The checkpoint chain and all witness attestations remain immutable regardless of the decision.

## Consequences

### Positive

- Named observations are inspectable rather than collapsed into a count.
- Conflicting-head evidence is preserved instead of overwritten.
- Checkpoint verification is re-run and persisted before witness evaluation.
- One conflict fails closed without claiming which witness is correct.
- Clean witness evidence delegates the prior checkpoint lifecycle unchanged.
- Witness, revocation, credential, adjudication, reviewer-revocation, and terminal outcomes remain separate.
- A later downstream abstention does not erase successful witness authorization.

### Costs

- Every checkpoint-witness publication requires a registry, policy, attestations, and successor corpus.
- Consumers must load the complete named attestation population.
- A missing required witness prevents a valid witness decision.
- Witness identity and independence remain artifact claims rather than externally verified facts.

## Non-claims

A verified adjudicator checkpoint witness decision does not establish:

- a witness's legal or real-world identity;
- witness independence, competence, honesty, or availability;
- cryptographic authorship or signature validity;
- trusted external time;
- public or global checkpoint publication;
- universal event or witness completeness;
- which conflicting witness is correct;
- that no alternate checkpoint head or chain exists;
- checkpoint-head uniqueness outside the frozen graph;
- issuer trustworthiness;
- credential truthfulness;
- adjudication correctness;
- extraction, review, or analyzer accuracy;
- content quality;
- consensus, confidence, or an aggregate CTRT score.

## Rejected alternatives

### Count matching witnesses

Rejected because witness count is not evidence that a head is globally correct. One preserved conflict remains operationally significant regardless of how many other observations match.

### Select the majority head

Rejected because majority voting would erase dissent and convert observation quantity into an unsupported truth claim.

### Mutate the checkpoint log after conflict

Rejected because witness evidence and checkpoint publication are separate append-only claims.

### Ignore a conflicting witness after successful checkpoint verification

Rejected because checkpoint-chain consistency does not disprove equivocation outside the supplied graph.

### Permit anonymous unregistered observations

Rejected in this phase because reproducible governance requires stable named pseudonymous identities and exact identity revisions.

### Add signatures or a live witness network now

Deferred. This bounded layer records immutable synthetic observations only.

## Follow-up

A later layer may preserve authorized adjudication of checkpoint-witness conflicts, including rationale, selected head, dissent, and unresolved fork evidence without permitting witness counts to determine the outcome.
