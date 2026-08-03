# ADR-0020: Reviewer credentials require immutable attestations

- **Status:** Accepted
- **Date:** 2026-08-03
- **Decision owners:** CTRT constitutional and research foundations

## Context

ADR-0019 introduced stable reviewer identifiers, authorized review roles, explicit disagreement, adjudication, preserved dissent, and governed abstention. Those records answer which repository identity performed a review role, but they do not independently record who authorized that identity revision to perform the role or whether the authorization was valid at execution time.

Treating an active reviewer-registry entry as sufficient credential evidence would collapse identity registration, role authorization, validity, and revocation into one mutable-looking flag. It would also make later review evidence difficult to audit after an authorization expires or is withdrawn.

This repository does not yet integrate a real identity provider, credential authority, cryptographic signature system, or live revocation service. The next bounded step therefore needs to establish the artifact and lifecycle contracts without pretending to solve external identity verification.

## Decision

Each reviewer identity revision used by governed review is bound to one immutable reviewer-credential attestation.

An attestation records only:

- a stable attestation ID and credential type;
- reviewer ID and exact identity revision;
- a derived subject reference;
- issuer ID and immutable issuer revision;
- exact authorized reviewer roles;
- attestation status;
- issuance and validity timestamps;
- revocation timestamp and reason when revoked.

The attestation deliberately excludes names, addresses, government identifiers, biometric data, private credential payloads, and unrelated personal information.

### Issuer registry

Credential issuers are authorized through a frozen registry that binds:

- issuer ID;
- immutable issuer revision;
- permitted credential types;
- active status.

An attestation from an absent issuer, a different issuer revision, or an issuer not authorized for the credential type fails structural validation.

### Credential policy

A frozen credential policy declares the accepted credential type and requires:

- exact role equality between the attestation and reviewer registry;
- abstention before the validity window opens;
- abstention after the validity window closes;
- abstention for suspended attestations;
- abstention for revoked attestations.

The initial policy does not permit partial role overlap or discretionary continuation after invalidity.

### Structural failure versus governed abstention

The layer distinguishes two classes of outcome.

Structural provenance defects fail validation:

- reviewer or identity revision mismatch;
- issuer or issuer revision mismatch;
- credential-type mismatch;
- role mismatch;
- missing or corrupted canonical artifacts;
- corpus or policy reference drift.

Valid evidence that is presently ineligible produces a verified credential abstention:

- reviewer registry entry inactive;
- issuer inactive;
- attestation not yet valid;
- attestation expired;
- attestation suspended;
- attestation revoked.

A verified credential abstention persists the credential decision and terminal marker but invokes no review-adjudication runner, quality gate, analyzer, governed session, or experiment completion.

### Append-only corpus identity

The credential-bound corpus uses a distinct artifact ID from its review-bound predecessor. The append-only store permits one immutable hash per artifact ID, so `0.4.0` and `0.5.0` cannot coexist under the same ID.

The credential-bound corpus therefore:

- uses `corpus.synthetic-three-items.credential-bound`;
- references the exact `0.4.0` review-bound corpus as its predecessor;
- preserves the complete ordered content and review graph;
- adds the exact issuer-registry and credential-policy references;
- adds one attestation reference per reviewer identity revision;
- is published only after all credential artifacts exist.

### Completion semantics

The run-specific credential decision is stored as:

```text
<experiment-run-id>:reviewer-credential-decision
```

The final marker is:

```text
<experiment-run-id>:credential-attested-completion
```

when credential authorization permits the existing adjudicated lifecycle and that lifecycle executes, or:

```text
<experiment-run-id>:credential-attestation-abstention
```

when credential evidence or a later governed layer abstains.

The final record preserves both credential outcome and downstream terminal outcome. Credential authorization does not force review adjudication, extraction quality, or analyzers to succeed.

## Consequences

### Positive

- Reviewer role authorization becomes independently inspectable and immutable.
- Validity and revocation are evaluated at an explicit run timestamp.
- Expired or revoked authorization cannot silently inherit an earlier active state.
- Credential abstention occurs before review or analyzer work.
- Private identity information is excluded by both parser and schema.
- The predecessor and successor corpora coexist without violating append-only IDs.

### Costs

- The synthetic path adds issuer, policy, attestation, decision, and completion artifacts.
- Real identity assurance remains unresolved.
- Revocation is represented inside immutable synthetic attestations rather than a separate event ledger.
- Cryptographic authenticity is not established.

## Rejected alternatives

### Treat the reviewer registry `active` flag as credential proof

Rejected because registration and issuer-backed authorization are different claims.

### Store legal names or government identifiers

Rejected because the research contract requires stable role authorization, not unnecessary private identity data.

### Continue execution after expiration or revocation with a warning

Rejected because invalid authorization must stop before review evidence can authorize analysis.

### Rewrite the `0.4.0` corpus in place

Rejected because accepted artifacts are immutable and append-only.

### Reuse the same corpus artifact ID for `0.5.0`

Rejected because the artifact store intentionally permits one hash per artifact ID; the predecessor and successor must coexist.

## Limitations

This decision does not establish:

- real-world reviewer identity;
- credential issuer trustworthiness outside the frozen registry;
- cryptographic signatures;
- live revocation checks;
- credential non-transferability;
- reviewer expertise, independence, or correctness;
- extraction accuracy;
- analyzer validity;
- any aggregate CTRT score or content verdict.
