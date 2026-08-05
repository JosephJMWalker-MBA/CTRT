# Phase 1B browser creator preflight

This guide describes the local browser surface for **Check before I publish**.

It is a thin wrapper around the existing local creator preflight. It renders HTML and nothing else.

> **Synthetic only.** The two analyzers recognize the fixture words `good` and `bad`. They are not real tone, sentiment, or quality instruments. Nothing this page displays is evidence about real-world content.
>
> **Local only.** The server binds to loopback, has no accounts, no authentication, no remote storage, and no monitoring. Anyone able to run code on this machine can reach it.

## Run it

From the repository root:

```bash
python -m ctrt.creator_preflight_web
```

It prints the local URL and the artifact workspace, then waits:

```text
CTRT local creator preflight (synthetic demonstration) at http://127.0.0.1:8765/
Artifact workspace: .ctrt/creator-preflight-web-runs
This server is loopback-only and has no authentication. Press Ctrl+C to stop.
```

Open that URL yourself. The command deliberately does not open a browser for you.

Choose a different loopback port, or let the operating system pick one:

```bash
python -m ctrt.creator_preflight_web --port 0
```

Put the per-run artifact stores somewhere specific:

```bash
python -m ctrt.creator_preflight_web --workspace /tmp/ctrt-preflight-runs
```

A non-loopback `--host` is refused before the socket is bound:

```bash
python -m ctrt.creator_preflight_web --host 0.0.0.0
```

```text
creator preflight web surface failed: host must be a loopback address, not '0.0.0.0'
```

Stop the server with `Ctrl+C`.

## The page

One page, four inputs:

| Field | Required | Limit |
| --- | --- | --- |
| Your draft | yes | 20,000 characters |
| What you intend this draft to communicate | yes | 2,000 characters |
| Intended audience | no | 500 characters |
| Your concerns, one per line | no | 4,000 characters, 20 concerns, each distinct |

Submitting runs one preflight and renders its result. JavaScript is not required and none is served.

## Relationship to the existing pipeline

The browser layer adds **no analysis path**. It calls the merged one:

```text
browser form
    ↓  (draft text + creator context only)
run_local_creator_preflight          ← src/ctrt/creator_preflight_local.py
    ↓
raw-text source artifact
identity-extraction manifest
extracted-content artifact
    ↓
method-bound extraction corpus  →  method eligibility
    ↓
EligibleExtractionExperimentRunner  →  append-only artifact store
    ↓
build_eligible_extraction_evidence_view   (read-time rehashing)
    ↓
CreatorPreflightView
    ↓
render_creator_preflight_html        ← src/ctrt/creator_preflight_web.py
```

Everything above the last arrow is unchanged by this module. The web layer does not extract, authorize, measure, persist, verify, or reconstruct anything. It receives a `CreatorPreflightView` that has already survived the full verification sequence, and escapes it into HTML.

Each submission is a complete run: three content items (the submitted draft plus the two required synthetic controls), its own append-only artifact store under the workspace, and full completion verification. The controls never appear on the creator-facing page.

Creator context — intent, audience, concerns — is used only to shape reflection questions. It is never written into the canonical artifact store.

## What the page shows

1. **Your draft** — the exact stored extracted content.
2. **Your context** — visibly labeled as not verified evidence.
3. **What each instrument recorded separately** — one card per analyzer, with status, normalized measurements, exact excerpts and coordinates, abstention, calibration, applicability, and extraction quality.
4. **Comparison, disagreement, abstention, uncertainty, and limitations** — the separate comparison artifact, with preserved disagreements and preserved abstention reasons.
5. **Questions for you** — the deterministic condition-triggered reflection prompts.
6. **Your decision remains yours** — the neutral, unranked creator-controlled actions.
7. **Interpretation boundary** — the fixed constitutional notices.
8. **Immutable evidence references** — role, artifact ID, and SHA-256 for every supporting artifact, inside a collapsed disclosure element.

Every observation, prompt, action, notice, and evidence reference carried by the structured view is preserved in the HTML.

## How neutrality is enforced

No styling is derived from any analytical outcome. There is no status color, badge, icon, glyph, or ranking. Agreement, disagreement, and abstention render in identical neutral cards.

This is not only a convention. A test renders an agreeing draft and a disagreeing draft and asserts both pages use the identical set of CSS classes, so the outcome cannot be encoded in presentation.

```text
Agreement is not approval.
Disagreement is not a warning or a failure.
Abstention is not evidence that the draft lacks meaningful tone.
A verified lifecycle describes artifact integrity, not analytical correctness.
```

## Security properties

The server:

- binds only to a validated loopback address and refuses any other host;
- accepts only `GET` and `POST`, on exactly one path;
- requires `Content-Length` and enforces a 65,536-byte request limit;
- accepts only `application/x-www-form-urlencoded`, with a 16-field cap;
- escapes every submitted and evidence-derived string before insertion;
- sends `Content-Type: text/html; charset=utf-8` and `Cache-Control: no-store`;
- sends `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`;
- sends `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`;
- loads no external script, font, image, stylesheet, or analytics;
- retains no mutable analytical state between requests; and
- writes no request log.

### Limitations you must not misread

- **There is no authentication.** Any process on this machine that can reach loopback can submit drafts and read results. Do not run it on a shared or multi-user host you do not control.
- **There is no CSRF token.** The surface is stateless and unauthenticated, so there is no session for a forged request to ride, but the absence of a token is a reason not to expose it beyond loopback rather than a defense.
- **Drafts are written to disk** in the artifact workspace, unencrypted, and are not cleaned up. Choose the workspace accordingly and delete it when finished.
- **`http://` is unencrypted.** This is acceptable only because traffic never leaves the loopback interface.
- **This is not production software** and carries no production-readiness claim.

## Failure responses

| Situation | Status |
| --- | --- |
| Unsupported method | `405` with `Allow: GET, POST` |
| Unknown path | `404` |
| Missing `Content-Length` | `411` |
| Non-integer or negative `Content-Length` | `400` |
| Body over the request limit | `413` |
| Non-form media type | `415` |
| Undecodable body, too many fields, repeated field | `400` |
| Field-limit, duplicate-concern, empty-draft, or empty-intent violation | `400`, form re-rendered with the input preserved |
| Failure inside the verified execution path | `500`, no evidence shown |

Field-level failures re-render the form with what the creator typed, escaped, so nothing is lost to a validation error.

Analyzer or comparison abstention is not a failure. It is a preserved analytical outcome and renders as one.

## Deliberate non-features

This surface does not provide:

- an overall CTRT score, overall sentiment or tone, or scalar or aggregate confidence;
- a safe/unsafe, good/bad, approved/prohibited, or publish-ready label;
- a recommendation to publish, revise, block, restrict, or suppress;
- an automatic rewrite or suggested revision;
- inferred creator intent, or a creator or audience profile;
- a real analyzer or extractor;
- accounts, authentication, authorization, or multi-user isolation;
- remote deployment, hosting, or durable storage;
- ambient monitoring, telemetry, or request logging;
- a new canonical preflight artifact; or
- a production-readiness claim.

## Next bounded step

The purpose of this surface is to answer the presentation questions ADR-0061 left open:

- Which details help a creator reflect, and which are noise?
- Is the disclosure element the right home for provenance, or does it hide something creators need?
- Are disagreement and abstention understood without technical vocabulary?
- Does the page read as neutral to someone who did not write it?

Those findings should be recorded before any real analyzer is admitted.
