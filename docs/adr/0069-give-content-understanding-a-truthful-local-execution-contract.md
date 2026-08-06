# ADR-0069: Give content understanding a truthful local execution contract

- Status: Accepted for Phase 1B implementation
- Date: 2026-08-06
- Decision scope: local synthetic intake for the `Understand this content` product door

## Context

ADR-0068 established a content-directed reflection over exact verified stored evidence. The next useful step is to let a person explicitly submit local raw text and receive that reflection.

The repository already contains a local raw-text execution shell for creator preflight. Reusing that shell unchanged would create artifacts whose protocol, experiment, corpus, environment, source, and run identities all claim creator-preflight purpose. That would be operationally convenient but evidentially false.

Copying the entire extraction and execution stack would create a second analysis pipeline and allow provenance or eligibility behavior to drift.

## Decision

Add `ctrt.content_understanding_local` as a separate local interface with its own truthful identities while reusing the exact merged mechanics for:

- raw-text source and content hashing;
- identity-extraction manifest construction;
- exact coordinate maps;
- candidate and extraction-method registry loading;
- fixed synthetic analyzer construction;
- analyzer registry wiring;
- execution windows;
- eligible-extraction execution; and
- extraction-backed evidence verification.

The local content-understanding contract is:

```text
ctrt-local-content-understanding@0.1.0
```

Its evidence graph is:

```text
explicitly submitted raw text
    ↓
authorized synthetic identity extraction
    ↓
frozen three-item synthetic experiment
    ↓
verified eligible-extraction evidence
    ↓
noncanonical content-understanding reflection
```

The experiment contains:

1. the submitted content;
2. the fixed material-disagreement control; and
3. the fixed no-signal abstention control.

Only the submitted content is rendered. Controls remain experiment controls, not reader-facing evidence.

## Truthful identity boundary

The new interface has distinct:

- interface version;
- protocol artifact identity;
- experiment identity;
- corpus identity;
- environment identity;
- submitted-content and source identities;
- experiment-run identity; and
- workspace path.

No canonical artifact claims that the run was creator preflight.

## Reader context

The intake accepts:

- inspection purpose;
- optional known context; and
- optional explicit questions.

These values remain non-evidentiary reader context. They are used only after verified evidence is reconstructed. They do not amend canonical artifacts or infer a viewer, child, parent, household, audience, intent, emotional state, or risk profile.

## Analysis boundary

This remains a synthetic demonstration. It executes only the two accepted synthetic fixtures through the accepted identity-text extraction method.

It does not:

- execute VADER or another real candidate;
- select or rank an analyzer;
- create a score, verdict, or safety label;
- recommend restriction, blocking, punishment, or reporting;
- monitor a person or device;
- persist the reader-facing view as controlling evidence; or
- claim production readiness.

## Consequences

### Positive

- A person can submit exact local text through the second original product door.
- Artifact identities describe the actual content-understanding purpose.
- Existing extraction and eligibility mechanisms remain the source of truth.
- Control outcomes remain available for experiment integrity without leaking into presentation.
- The next browser slice can wrap one bounded function rather than invent execution.

### Cost

The interface currently imports internal reusable mechanics from `creator_preflight_local`. This avoids copying the proven graph builders and runner wiring, but the module ownership is imperfect. A later cleanup may move those mechanics into a neutral internal module only if both public interfaces remain behaviorally unchanged and exact artifact identities are preserved.

That cleanup is not required to establish this bounded capability.

## Rejected alternatives

### Run creator preflight and discard its view

Rejected because the controlling artifacts would misstate the run purpose.

### Duplicate the full local execution module

Rejected because two independent provenance and eligibility paths could drift.

### Admit the real candidate into this interface

Rejected because candidate evaluation and selection remain incomplete and creator- or reader-facing execution is not authorized.

### Add monitoring or person-oriented intake

Rejected because the product door is explicitly content-directed and non-surveillant.

## Validation

The implementation must prove:

- exact source → extraction → content provenance;
- only accepted synthetic analyzers and extraction configuration execute;
- controls are absent from reader-facing Markdown;
- agreement, disagreement, and abstention remain distinct;
- unauthorized configuration fails before execution;
- read-time tampering fails before presentation;
- no legacy `content-item:` identity enters new artifacts;
- no viewer profile, safety label, restriction recommendation, or overall score appears; and
- the complete inherited suite remains green.
