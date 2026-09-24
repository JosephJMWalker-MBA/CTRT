# Phase 1B: human-reference annotation surface — operating guide

> This surface collects independent human judgments under the frozen annotation protocol. It shows no instrument, model, candidate, expected answer, or other annotator's work.
>
> **A pseudonymous annotator ID is not a login, not authentication, and not identity verification.**

See [ADR-0071](adr/0071-serve-human-reference-annotation-through-a-blinded-loopback-surface.md) for the decision record, and [ADR-0065](adr/0065-collect-blinded-human-reference-annotations-without-fabricating-ground-truth.md) for the collection contract it exposes.

## What this adds

The collection contract has supported eight response fields plus correction since PR #63. The terminal path collected five of them. This surface exposes the whole contract:

| Field | Terminal path | This surface |
| --- | --- | --- |
| Valence label | yes | yes |
| Abstention reason | yes | yes |
| Context sufficiency | yes | yes |
| Perceived ambiguity | yes | yes |
| Rationale | yes | yes |
| Self-reported certainty | **no** | **yes** |
| Supporting spans | **no** | **yes** |
| Correction (supersession) | **no** | **yes** |

It creates no second collection lifecycle. Every action delegates to `AnnotationSession`.

## Running it

No optional dependency is required, and no network access occurs:

```bash
pip install -e ".[dev]"
```

Start a session for one annotator:

```bash
python -m ctrt.human_reference_annotation_web \
  --annotator-id rater-001 \
  --workspace .ctrt/human-reference
```

It prints the loopback URL and waits. Open it yourself — the command deliberately does not open a browser.

Each annotator gets their own command, their own port if run concurrently, and their own append-only store:

```bash
python -m ctrt.human_reference_annotation_web --annotator-id rater-002 --port 8768
python -m ctrt.human_reference_annotation_web --annotator-id rater-003 --port 8769
```

A non-loopback `--host` is refused before the socket is bound:

```bash
python -m ctrt.human_reference_annotation_web --annotator-id rater-001 --host 0.0.0.0
```

```text
annotation surface failed: host must be a literal loopback address, not '0.0.0.0'
```

Only literal loopback addresses are accepted. `localhost` is refused too, because it is a name that resolution could point elsewhere.

## The annotator's flow

| Path | Purpose |
| --- | --- |
| `/` | Your own progress, and the list of items you may correct |
| `/annotate` | The next unanswered item |
| `/correct?item=<id>` | Record a correction to one item you already answered |
| `/complete` | Mark the assignment complete |
| `/receipt` | Your verified completion receipt |

One item is shown at a time, with the exact response options from the frozen protocol. Stopping and returning later resumes from stored artifacts at the next unanswered item.

## Response fields

All eight are on one form and none is derived from another. A strong judgement can sit beside insufficient context and high ambiguity; that combination is informative.

**Supporting spans** are entered one per line as character offsets, for example `0-12`. Offsets must fall inside the passage shown. Malformed or out-of-range spans are refused with the reason, and nothing is recorded.

**Self-reported certainty is optional and is a statement about you**, not a measurement of the text. It never becomes instrument confidence.

**Abstention is a real answer.** Choosing `cannot_determine_responsibly` requires a reason and is recorded as a first-class response. "Not yet answered" and "explicitly abstained" stay distinct everywhere, including your progress counts.

## Corrections never overwrite

A recorded response is never edited or deleted. Submitting a second response for the same item is **refused**.

To correct one, use the correction link from your progress page. That records a **new** response which names the original and carries your reason. The original stays stored and readable, and your progress page counts the correction.

## Completion and receipt

Completion requires every assigned item to carry a judgement or an explicit abstention. Marking complete verifies every stored response by exact hash and shows an immutable receipt identifier.

Give that receipt identifier to whoever is running the study. This surface combines nothing with any other annotator's responses — synthesis is a separate, later step under its own protocol.

Marking complete and viewing the receipt are the same idempotent operation. Viewing a receipt does not rewrite the record it reports.

## Blinding

You are not shown, and the surface cannot reach, any instrument, model, candidate identity, candidate output, characterization, evaluation protocol, evaluation result, or any majority, consensus, gold, or expected label. There is no import, field, route, or template capable of carrying one.

You also see nothing about any other annotator. Disagreement between annotators is a result the study preserves, not an error to avoid.

This surface is **not** linked from `ctrt.local_browser_launcher`. That launcher opens the two product doors, whose pages display analyzer output; a blinded research instrument must not sit one click away from them.

## Privacy and its limits

The annotator ID is a locally chosen pseudonymous label matching `^[a-z][a-z0-9-]{2,31}$` — too narrow to hold an email address, phone number, or account handle. `person@example.com`, `Jane Doe`, and `../escape` are all refused.

No personal-information field exists. No name, email, phone number, account identifier, IP address, or demographic profile is collected.

**The honest limits:**

- A pseudonymous ID is still linkable if whoever distributes the study keeps a separate mapping. CTRT neither creates nor stores such a mapping and cannot prevent one.
- **Local artifact storage is unencrypted.** Responses are written to disk in the workspace as plain JSON.
- There is no authentication and no encryption. Anyone able to run code on this machine may be able to reach the server.
- `http://` on loopback is unencrypted, which is acceptable only because traffic never leaves the machine.
- This is **not** production software and carries no production-readiness or remote-deployment claim.

Anyone running a study with real annotators is responsible for consent, for any applicable review requirements, and for the pseudonym mapping if they keep one. None of that is provided here.

## Security properties

Binds only a validated literal loopback address; accepts only `GET` and `POST`; requires `Content-Length`; enforces a 65,536-byte request limit and a 16-field cap; accepts only `application/x-www-form-urlencoded`; escapes every submitted and stored string; sends `no-store`, a restrictive CSP, `nosniff`, `no-referrer`, and `DENY`; loads no external script, font, image, or stylesheet; uses no JavaScript; and writes no request log.

## Fixture boundary

Tests generate fixtures at runtime through the real collection mechanics in temporary directories. No invented annotation and no result count is committed to this repository, and no example in this guide is empirical.

The fixture checks from the synthesis and evaluation work are untouched and still refuse marked fixtures in production paths.
