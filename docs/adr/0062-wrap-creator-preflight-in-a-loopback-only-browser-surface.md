# ADR-0062: Wrap creator preflight in a loopback-only browser surface

- **Status:** Accepted
- **Date:** 2026-08-05
- **Phase:** 1B application shell

## Context

ADR-0061 established a local command-line creator preflight that runs one raw-text draft through the authorized source, extraction, and extracted-content artifact graph. It closed by naming the next question: whether the human presentation is understandable, and which details belong behind disclosure controls.

That question cannot be answered from a terminal. A creator reading Markdown in a shell is not the reader the presentation is for.

The risk in adding a browser is not technical. It is that a rendered page reads as a judgement. A colored badge, a check mark, a summary line, or a prominently placed status turns a preserved measurement into a verdict without any code claiming to produce one. The interface layer is where constitutional non-prescription is most easily lost.

A second risk is that a web layer quietly becomes a second analysis path — re-deriving evidence, caching results, or reformatting measurements in ways that drift from the canonical artifacts.

## Decision

Add `src/ctrt/creator_preflight_web.py`: a loopback-only browser surface that **wraps** the merged execution path and adds no analysis of its own.

The module is layered so the boundary is structural rather than conventional:

1. **Pure rendering** — `render_creator_form_html` and `render_creator_preflight_html` are pure functions over an already-built `CreatorPreflightView`.
2. **Pure request/response core** — frozen `WebRequest`, `WebResponse`, and `CreatorPreflightWebApp.handle` perform routing, limits, decoding, and error mapping with no socket involved.
3. **Thin HTTP adapter** — a `BaseHTTPRequestHandler` subclass that only translates HTTP into the core and back.
4. **`main`** — argument parsing, loopback validation, bind, print URL, serve.

The POST branch performs exactly one substantive action:

```python
result = run_local_creator_preflight(preflight_request)
```

Extraction, method eligibility, analyzer execution, canonical persistence, read-time rehashing, completion verification, and evidence reconstruction are **never** reimplemented, re-entered, or bypassed by the web layer.

The interface is invoked without an added runtime dependency:

```bash
python -m ctrt.creator_preflight_web
```

## Why the standard library is sufficient

The bounded task is a single-user, single-page, loopback form with no sessions, no uploads, no routing tree, and no asynchronous work. `http.server`, `urllib.parse.parse_qs`, `html.escape`, and `ipaddress` cover it completely.

Adding Flask, FastAPI, Django, a template engine, or a JavaScript framework would enlarge the dependency surface, the attack surface, and the review surface while adding no capability this task needs. The repository's dependency-free posture is a governance property, not an aesthetic one, so the standard library is used.

Embedded CSS is included. JavaScript is not required and none is served.

## Trust boundaries

| Boundary | What crosses | Enforcement |
| --- | --- | --- |
| HTTP client → web layer | Raw request bytes | Method allowlist, single-path allowlist, required `Content-Length`, `MAX_REQUEST_BYTES`, media-type check, bounded field count, per-field length limits, guarded UTF-8 decode |
| Web layer → preflight core | `draft_text` and `CreatorProvidedContext` only | The core independently revalidates draft emptiness and run-token path safety |
| Preflight core → artifact store | Unchanged | The web layer never reads or writes the store |
| View → HTML | Every dynamic string | `html.escape(..., quote=True)` at every insertion point |
| Creator context → canonical evidence | **Never crosses** | Context stays in `CreatorProvidedContext`, outside the artifact store |
| Process → network | Nothing outbound | Loopback-only bind; no external scripts, fonts, images, or analytics |

## Neutral presentation

The rendered page carries the same substantive sections as the Markdown presentation:

1. the submitted draft;
2. creator-provided context, visibly labeled as not verified evidence;
3. separate instrument observations;
4. comparison, disagreement, abstention, uncertainty, and limitations;
5. reflection questions;
6. neutral creator-controlled actions;
7. interpretation boundaries; and
8. immutable evidence references, inside a disclosure element.

Every observation, reflection prompt, neutral action, notice, and evidence reference represented by the structured view is preserved. A test walks the view element-for-element to prove it.

**No styling is derived from any analytical outcome.** There is no status color, no badge, no icon, no glyph, and no ordering that implies rank. Agreement, disagreement, and abstention render in identical neutral cards. This is enforced by a test that renders an agreeing draft and a disagreeing draft and asserts both pages use the identical set of CSS classes.

The stated rule is carried in the page itself:

```text
Agreement between instruments is not approval. Disagreement is not a warning or a
failure. A verified lifecycle describes artifact integrity, not analytical correctness.
```

## Security properties of the local surface

The server:

- binds only to a validated loopback address, and refuses any other host;
- sets `Content-Type: text/html; charset=utf-8` and `Cache-Control: no-store`;
- sets a restrictive `Content-Security-Policy` of `default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`;
- sets `X-Content-Type-Options`, `Referrer-Policy`, and `X-Frame-Options`;
- serves no external script, font, image, analytics, or network resource;
- retains no mutable analytical state between requests;
- writes each run to its own append-only artifact workspace; and
- keeps no request log.

Explicit limits are declared rather than implied: `MAX_REQUEST_BYTES`, `MAX_FORM_FIELDS`, `MAX_DRAFT_CHARACTERS`, `MAX_INTENT_CHARACTERS`, `MAX_AUDIENCE_CHARACTERS`, `MAX_CONCERNS_CHARACTERS`, and `MAX_CONCERNS`.

The browser is not opened automatically. Doing so would take an action the creator did not ask for, on a surface whose whole purpose is leaving decisions with the creator, and it is not needed to print a URL.

## Failure semantics

The surface fails visibly and without inventing a result:

- unsupported method → `405` with an `Allow` header;
- unknown path → `404`;
- missing or non-integer `Content-Length` → `411` or `400`;
- oversized body → `413`;
- non-form media type → `415`;
- undecodable body, excess fields, or repeated fields → `400`;
- field-limit, duplicate-concern, empty-draft, or empty-intent violations → `400` with the form re-rendered and the creator's input preserved and escaped; and
- any failure inside the verified execution path → `500` naming the reported cause and showing no evidence.

Analyzer or comparison abstention is **not** a failure. It renders as a preserved analytical outcome.

## Scope and non-claims

This ADR does not introduce:

- a real extractor or a real analyzer;
- an overall CTRT score, overall sentiment or tone, or scalar or aggregate confidence;
- safe/unsafe, good/bad, approved/prohibited, or publish-ready labels;
- a recommendation to publish, revise, block, restrict, or suppress;
- an automatic rewrite or suggested revision;
- inferred creator intent, or a creator or audience profile;
- a new canonical preflight or creator-context artifact;
- authentication, authorization, multi-user isolation, or access control;
- remote deployment, hosting, or durability;
- ambient monitoring, telemetry, or request logging;
- production packaging or a production-readiness claim; or
- any reopening of the completed Phase 1A governance kernel.

The surface has **no authentication of any kind**. Any process able to reach loopback on this machine can use it. It is a local research and presentation-evaluation tool.

## Consequences

### Positive

- The presentation question raised by ADR-0061 can now be evaluated with real readers.
- Provenance stays accessible behind a disclosure element without crowding the primary reading path.
- The wrapping boundary is structural: the web layer holds no pipeline logic to drift.
- The interface remains standard-library-only and offline.

### Costs

- Each submission runs a full three-item experiment and writes a new artifact workspace, so repeated use accumulates local storage.
- The synthetic fixtures remain too narrow for real content interpretation, which may be less obvious in a polished page than in a terminal.
- A rendered page invites a reading of authority that the underlying evidence does not support; the neutrality constraints are load-bearing and must be re-checked whenever the presentation changes.

## Reopening criterion

Revisit this decision only when one of the following becomes concrete:

- reader evaluation shows that a section is misread as a verdict despite the neutrality constraints;
- a real analyzer or extractor is admitted through pinned evaluation records;
- the surface is proposed for any non-loopback binding, which would require authentication, authorization, and a separate threat model;
- a single-content experiment contract removes the need for control items; or
- constitutional tests identify a presentation regression not represented here.
