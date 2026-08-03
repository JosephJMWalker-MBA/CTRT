# Phase 1A Reviewer Credential Attestation

This slice adds an immutable credential gate before the existing review-adjudicated extraction lifecycle.

It does not integrate a real identity provider. It establishes the artifact graph and fail-closed behavior required before external credentials can be considered.

## Research boundary

The layer asks a narrow question:

> Was this exact reviewer identity revision authorized by an accepted issuer for these exact roles, and was that authorization valid at the stated evaluation time?

It does not ask whether the reviewer is correct, unbiased, qualified in every relevant domain, or the real-world person someone claims to be.

## Artifact graph

The synthetic graph is:

```text
review-bound corpus 0.4.0
        |
        +-- reviewer registry
        +-- review policy
        +-- review adjudication records
        |
credential issuer registry
reviewer credential policy
reviewer credential attestations
        |
credential-bound corpus 0.5.0
        |
run-specific credential decision
        |
        +-- credential abstention, or
        +-- existing adjudicated extraction lifecycle
                |
credential-attested final marker
```

The credential-bound corpus has a distinct artifact ID so it can coexist with its append-only predecessor.

## Credential issuer registry

The accepted synthetic issuer registry contains one first-party fixture issuer:

```text
issuer.synthetic-reviewer-credentials
synthetic-issuer@0.1.0
```

The issuer may issue only:

```text
ctrt.reviewer-role-attestation
```

The registry is a research fixture. Inclusion does not imply external accreditation or institutional endorsement.

## Reviewer credential policy

The initial policy requires:

- exact credential type;
- exact role equality with the reviewer registry;
- abstention before `valid_from`;
- abstention at or after `valid_until`;
- abstention when suspended;
- abstention when revoked.

No warning-only continuation path exists.

## Attestation contract

Each attestation binds:

- attestation and credential type;
- reviewer ID;
- immutable reviewer identity revision;
- derived subject reference;
- issuer ID and immutable issuer revision;
- exact authorized roles;
- active, suspended, or revoked status;
- issue, validity, and revocation timestamps;
- revocation reason when applicable.

The public schema and parser reject additional fields. The synthetic contract intentionally excludes private identity information such as legal names, addresses, government identifiers, biometrics, and private source credentials.

## Evaluation outcomes

### Structural validation failure

Execution fails closed when the graph is malformed or substituted, including:

- identity revision drift;
- reviewer role drift;
- issuer revision drift;
- unauthorized credential type;
- missing credential artifact;
- artifact hash mismatch;
- policy or registry reference mismatch;
- corpus population mismatch.

These are invalid provenance records, not research abstentions.

### Verified credential abstention

A structurally valid record may be ineligible at runtime because it is:

- not yet valid;
- expired;
- suspended;
- revoked;
- attached to an inactive reviewer registry entry;
- issued by an inactive issuer.

The runner then:

1. persists and reverifies the run-specific credential decision;
2. writes and reverifies a credential-attestation abstention marker;
3. does not invoke review adjudication;
4. does not invoke extraction-quality evaluation;
5. does not invoke analyzers;
6. creates no governed session or experiment completion.

This is a successful governance outcome, not an execution error.

### Credential-permitted execution

When every credential is valid, the wrapper delegates the existing `AdjudicatedExtractionExperimentRunner` unchanged.

The delegated lifecycle may still:

- abstain on unresolved review disagreement;
- abstain on extraction-quality evidence;
- preserve analyzer abstention or disagreement;
- fail during later execution or persistence.

The credential decision remains preserved even if a later stage fails.

## Run artifacts

The detailed credential decision is written as:

```text
<experiment-run-id>:reviewer-credential-decision
```

A deterministic plan-level index remains available for discovery.

The final artifact is one of:

```text
<experiment-run-id>:credential-attested-completion
<experiment-run-id>:credential-attestation-abstention
```

The final artifact preserves:

- credential corpus reference;
- reviewer registry reference;
- credential issuer registry reference;
- credential policy reference;
- every credential attestation reference;
- run-specific credential decision reference;
- downstream adjudicated final reference when present;
- credential outcome;
- downstream terminal outcome.

## Synthetic fixtures

The frozen fixture set includes:

- one accepted issuer registry;
- one accepted credential policy;
- three role-specific attestations;
- primary, secondary, and adjudicator reviewer roles;
- one-year validity windows;
- no private identity fields;
- credential-bound corpus `0.5.0` referencing review-bound `0.4.0`.

## Tested failure boundaries

The executable suite covers:

- exact successful execution;
- idempotent ingestion and rerun;
- not-yet-valid abstention;
- expiration abstention;
- suspension abstention;
- revocation abstention with reason preservation;
- identity-revision mismatch;
- role mismatch;
- private-field rejection;
- missing stored attestation;
- later analyzer failure with preserved credential decision and prior receipt;
- final persistence failure;
- exact storage reconstruction;
- JSON Schema validation for every new canonical surface.

## What `verified` means

A verified receipt means:

- exact credential artifacts were loaded;
- issuer and reviewer identity revisions matched;
- authorized roles matched;
- validity and revocation were evaluated at the declared time;
- the credential decision was stored and reverified;
- the final lifecycle marker was stored and reverified.

It does not mean:

- the reviewer’s external identity was proven;
- the issuer is trustworthy outside the frozen registry;
- a digital signature was verified;
- revocation was checked against a live service;
- the reviewer was correct;
- extraction or analysis was accurate;
- content was good or bad;
- any aggregate CTRT score is valid.

## Deferred work

Future bounded layers may add:

- append-only revocation event ledgers;
- cryptographic signature envelopes;
- issuer key rotation;
- selective disclosure;
- conflict-of-interest attestations;
- external identity-provider adapters.

Those layers must preserve the current privacy and abstention boundaries rather than replacing them with implicit trust.
