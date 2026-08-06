# ADR-0070: Wrap content understanding in a loopback-only browser surface

- Status: Accepted
- Date: 2026-08-06
- Decision owners: CTRT maintainers
- Scope: Phase 1B local synthetic demonstration

## Context

ADR-0068 established a content-directed, non-surveillant reflection contract. ADR-0069 added a truthful raw-text execution path for that contract. The remaining usability gap is a browser form for a person who should not need to prepare a file or command line invocation.

The browser must not become another analyzer, evidence reader, artifact store, or moderation system. It must also avoid converting analytical state into approval, warning, risk, or restriction styling.

## Decision

Add `ctrt.content_understanding_web` as a standard-library, loopback-only HTML surface.

The POST path performs one substantive operation:

```text
run_local_content_understanding(request)
```

It does not reconstruct extraction, eligibility, execution, persistence, completion, or evidence verification.

The module contains four layers:

1. pure form and result rendering;
2. frozen request and response values;
3. a stateless request router; and
4. a thin `http.server` adapter and command entry point.

## Accepted inputs

The form accepts only:

- exact submitted content;
- the reader's inspection purpose;
- optional known context; and
- optional distinct questions ending in a question mark.

The form contains no viewer, child, parent, household, audience-profile, risk, restriction, monitoring, or enforcement field.

Reader-provided values remain outside canonical evidence.

## Binding boundary

The server accepts only literal loopback IP addresses. Hostnames and non-loopback addresses are rejected before socket creation.

The default is:

```text
127.0.0.1:8766
```

This is a local development boundary, not authentication. Another process or user on the same machine may be able to access the server.

## HTTP boundary

The surface:

- accepts GET and POST only;
- serves one path;
- requires URL-encoded form data;
- imposes request, field, and repeated-question limits;
- escapes all submitted and evidence-derived text;
- sends `Cache-Control: no-store`;
- sends a restrictive Content Security Policy;
- loads no script, image, font, analytics, or remote resource;
- retains no analytical state between requests; and
- writes only through the append-only workspace owned by the local execution path.

## Presentation neutrality

Agreement, disagreement, abstention, uncertainty, and limitation records use the same card structure and CSS classes. No outcome controls color, iconography, ordering, emphasis, or action wording.

The result preserves:

- exact submitted text;
- reader context, labeled non-evidentiary;
- every instrument result and normalized measurement;
- exact evidence spans when available;
- comparison, disagreement, and abstention;
- calibration, applicability, extraction quality, ambiguity, and uncertainty;
- every reflection prompt;
- every neutral inspection path;
- every interpretation notice; and
- immutable artifact references.

## Explicit non-claims

The browser does not produce:

- a meaning verdict;
- an overall score;
- a safety or risk classification;
- a restriction, blocking, punishment, or reporting recommendation;
- a person or household profile;
- ambient monitoring;
- inferred intent or emotional state;
- automatic enforcement;
- real-candidate creator-facing execution;
- remote deployment; or
- production-readiness.

## Alternatives rejected

### Add a web framework

Rejected because the standard library is sufficient for one bounded loopback form, and a framework would add a dependency and larger attack surface without a required capability.

### Reuse the creator-preflight browser by changing labels

Rejected because the two product doors have different input context, decisions, artifact identities, and interpretation boundaries.

### Open the browser automatically

Rejected because launching another application is an unnecessary action. The command prints the URL and leaves control with the user.

### Add status colors or warning badges

Rejected because presentation would convert descriptive analytical state into an implicit verdict.

## Consequences

A person can run:

```bash
python -m ctrt.content_understanding_web
```

and explicitly submit text in a local browser. The artifact graph and analytical behavior remain controlled by the existing local content-understanding path.

The next bounded work may improve local navigation between the two product doors. It must not combine their context models or analysis identities.
