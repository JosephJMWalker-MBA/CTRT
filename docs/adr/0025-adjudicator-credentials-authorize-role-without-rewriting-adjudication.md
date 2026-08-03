# ADR-0025: Adjudicator credentials authorize a role without rewriting adjudication

- Status: Accepted
- Date: 2026-08-03
- Decision owners: CTRT maintainers
- Scope: Phase 1A witness-conflict governance

## Context

CTRT already preserves conflicting checkpoint-witness observations and allows a separately authorized adjudicator to decide whether the independently verified checkpoint head may proceed.

That adjudication layer binds a pseudonymous adjudicator identity revision and role through a frozen registry. Registry membership alone, however, does not answer whether a separate issuer authorized that identity revision to exercise the role at the time of an experiment.

The missing governance question is:

> Was the exact adjudicator identity revision authorized by an accepted issuer to exercise the declared role at the stated evaluation time?

This question must remain separate from whether the adjudication was correct.

A credential can establish an issuer-bound authorization claim. It cannot establish:

- the adjudicator's real-world identity;
- the adjudicator's honesty, independence, competence, or correctness;
- the truth or uniqueness of the selected checkpoint head;
- the completeness of witness or fork disclosure;
- cryptographic authorship;
- external time accuracy;
- consensus;
- content quality;
- an aggregate CTRT score.

The original adjudication artifact is append-only evidence. Later credential evaluation must not edit, erase, replace, or retroactively rewrite that record.

## Decision

CTRT will add a separate adjudicator credential-attestation layer above witness-conflict adjudication.

The layer will:

1. preserve an immutable issuer registry;
2. preserve a frozen credential policy;
3. preserve immutable credential attestations;
4. bind each attestation to an exact adjudicator ID and identity revision;
5. bind the attestation to the exact role declared by the adjudicator registry;
6. bind the issuer ID and immutable issuer revision;
7. evaluate status and validity at an explicit experiment timestamp;
8. persist and reverify a run-specific credential decision before adjudication can authorize downstream work;
9. abstain before checkpoint, witness, adjudication-decision, or analyzer execution when a structurally valid credential is inactive;
10. leave the preserved adjudication record unchanged regardless of credential outcome.

## Credential contents

The initial credential contains only:

- credential artifact ID;
- attestation ID;
- credential type;
- pseudonymous adjudicator ID;
- adjudicator identity revision;
- deterministic subject reference;
- issuer ID;
- issuer revision;
- authorized role;
- status;
- issuance time;
- validity start;
- validity end;
- optional revocation time and reason.

The initial contract excludes:

- legal names;
- postal or email addresses;
- government identifiers;
- biometric information;
- account credentials;
- private credential payloads;
- authentication secrets;
- public keys or signatures.

## Exact identity and role binding

The credential subject reference is deterministic:

```text
witness-conflict-adjudicator:<adjudicator-id>@<identity-revision>
```

The identity revision must exactly match the frozen adjudicator registry.

The credential's authorized roles must exactly equal the role declared by that registry. The initial policy does not permit implied, inherited, broader, or partially matching roles.

A credential issued for another identity revision or role is a structural provenance failure, not a weak credential and not an abstention.

## Issuer binding

The frozen credential policy binds:

- one exact issuer registry reference;
- one exact adjudicator registry reference;
- one exact credential type.

The attestation's issuer ID must exist in the accepted issuer registry. Its issuer revision must match exactly, and the issuer must be authorized to issue the credential type.

An absent issuer, substituted issuer revision, unsupported credential type, or mismatched registry reference is a structural failure.

An accepted but inactive issuer produces a governed credential abstention.

Issuer inclusion is not a claim that the issuer is trustworthy in the real world. CTRT verifies only the internal relationship among the supplied frozen artifacts.

## Status and time evaluation

The initial statuses are:

- `active`;
- `suspended`;
- `revoked`.

Every credential includes a half-open validity interval:

```text
valid_from <= evaluated_at < valid_until
```

A credential decision abstains when the credential is:

- not yet valid;
- expired;
- suspended;
- revoked;
- issued by an inactive issuer.

Evaluation uses the explicit experiment timestamp supplied to the gate. It does not use ambient wall-clock state or a network service.

The original attestation is immutable. A later revocation-ledger layer may add append-only status events, but it must not mutate this attestation.

## Structural failure versus governed abstention

CTRT distinguishes malformed or substituted provenance from valid evidence that denies permission.

### Structural failure

Examples include:

- plan and corpus mismatch;
- predecessor corpus mismatch;
- substituted adjudicator registry;
- substituted issuer registry or policy;
- identity-revision mismatch;
- role mismatch;
- absent issuer;
- issuer-revision mismatch;
- unauthorized credential type;
- malformed timestamps;
- invalid subject reference;
- missing or altered stored artifacts;
- unsupported fields in closed credential, policy, or issuer documents;
- non-canonical or hash-mismatched artifacts.

Structural failure creates no verified terminal receipt.

### Governed abstention

A structurally valid credential produces a verified abstention when its eligibility state is inactive at the declared evaluation time.

A verified credential abstention is a successful governance outcome. It means the system preserved and reverified the evidence explaining why execution did not proceed.

It does not mean the adjudication artifact was deleted, disproven, or retroactively invalidated.

## Execution ordering

The credentialed runner performs:

1. exact preflight binding;
2. storage-backed credential evidence loading;
3. credential validation at the declared time;
4. run-specific credential-decision persistence and reread verification;
5. either terminal credential abstention or delegation to the existing adjudicated witness runner;
6. final artifact persistence;
7. complete storage-backed verification.

When credentials abstain, the runner creates no new:

- checkpoint-verification report;
- checkpoint-witness decision;
- witness-conflict adjudication decision;
- credential-revocation decision;
- governed analysis session;
- analyzer result;
- downstream completion artifact.

The pre-existing adjudication artifact remains stored and referenceable because it is part of the predecessor corpus graph.

## Separate outcomes

The final artifact preserves separate fields for:

- adjudicator credential outcome;
- witness outcome, when downstream execution occurs;
- witness-conflict adjudication outcome, when downstream execution occurs;
- reviewer-credential revocation outcome, when downstream execution occurs;
- terminal review or analysis outcome.

A credential outcome never overwrites an adjudication outcome.

For example, an eligible credential may permit the existing adjudication layer to run, while that layer or a later layer may still abstain for an independent reason.

## Append-only corpus evolution

The witness-conflict adjudication corpus remains immutable:

```text
corpus.synthetic-three-items.witness-adjudication-bound@0.9.0
```

The successor is a distinct artifact:

```text
corpus.synthetic-three-items.adjudicator-credential-bound@1.0.0
```

It preserves the complete inherited governance graph and adds exact references to:

- the `0.9.0` predecessor;
- adjudicator credential issuer registry;
- adjudicator credential policy;
- ordered adjudicator credential population.

Credential graph members are persisted and reverified before the `1.0.0` manifest is appended last.

The version transition to `1.0.0` marks completion of the initial synthetic provenance chain from source extraction through credentialed witness-conflict adjudication. It does not imply production readiness or stable public API compatibility.

## Verification meaning

For this layer, `verified` means:

- the exact supplied plan and corpus were bound;
- the exact predecessor adjudication graph remained available;
- issuer, policy, adjudicator registry, and credential references matched;
- identity revision and role matched exactly;
- status and validity were evaluated at the declared time;
- credential decisions and final relationships were persisted and reverified from append-only storage.

It does not mean:

- the adjudicator exists as a verified natural person;
- the issuer is externally trusted;
- the credential was cryptographically signed;
- the adjudicator made a correct decision;
- the checkpoint head is globally unique;
- every fork or witness was disclosed;
- the extraction, review, or analyzer output is accurate;
- content is good or bad;
- consensus exists;
- CTRT produced an aggregate score.

## Consequences

### Positive

- adjudicator authority becomes independently inspectable;
- credential status is evaluated before adjudication authorization affects execution;
- inactive credentials produce evidence-preserving abstention;
- identity, role, issuer, and time are separately auditable;
- prior adjudication evidence remains immutable;
- no personal identity information is required;
- no majority or aggregate mechanism is introduced.

### Costs

- the artifact graph gains another registry, policy, attestation, corpus, decision, and final layer;
- experiment callers must provide another explicit evaluation timestamp;
- repeated storage verification adds implementation complexity;
- synthetic issuer authority remains a declared governance assumption rather than external proof.

## Alternatives rejected

### Treat registry membership as sufficient credentialing

Rejected because registry authorization and issuer attestation are different claims.

### Embed credential status inside the adjudication artifact

Rejected because later credential changes would require mutation or would conflate adjudication evidence with authorization evidence.

### Delete or invalidate the adjudication artifact after credential expiry

Rejected because expiry changes permission at a time; it does not erase historical evidence.

### Use a scalar trust or credential score

Rejected because it would collapse identity, role, issuer, status, time, and uncertainty into an opaque aggregate.

### Use current wall-clock time

Rejected because experiment decisions must be reproducible from an explicit timestamp.

### Integrate a live identity or revocation provider

Rejected for this bounded phase. External systems would introduce network state, authentication, privacy, and operational dependencies before the local governance contract is stable.

## Intentionally deferred

- append-only adjudicator credential revocation events;
- issuer revocation and supersession ledgers;
- signatures and key management;
- external identity proofing;
- live status retrieval;
- transparency services;
- privacy-preserving credential presentations;
- credential delegation chains;
- real adjudicators or issuers;
- network APIs, frontend, deployment, retries, or distributed execution.
