# ADR-0071: Serve human-reference annotation through a blinded loopback surface

- **Status:** Accepted
- **Date:** 2026-08-06
- **Phase:** 1B empirical operations

## Context

ADR-0065 built the blinded, append-only human-reference collection contract. ADR-0066 built descriptive synthesis over multiple collections. ADR-0069 and ADR-0070 froze and then executed the candidate-to-human-reference evaluation.

The machinery is now complete enough to run a genuine evaluation, and the bottleneck is no longer machinery. It is that **no real annotator has ever used the collection path**, because no surface exposes it usably.

Inspecting the merged contract shows the gap precisely. `AnnotationSession` fully supports eight response fields plus correction. The only operator surface — the terminal loop in `run_collection_session` — collects **five** of them:

| Field | Terminal surface | Contract |
| --- | --- | --- |
| valence label | yes | yes |
| abstention reason | yes | yes |
| context sufficiency | yes | yes |
| perceived ambiguity | yes | yes |
| rationale | yes | yes |
| **self-reported certainty** | **no** | yes |
| **supporting spans** | **no** | yes |
| **correction (supersession)** | **no** | yes |

So a real annotator today cannot record their certainty, cannot point at the words they responded to, and — most seriously — **cannot correct a mistake**, even though the storage layer has first-class support for all three. Completion is also only reachable as a side effect of `--report`.

The missing piece is an operator surface, not a lifecycle.

## Decision

Add `ctrt.human_reference_annotation_web`: a loopback-only, standard-library, JavaScript-free browser surface that exposes the **existing** collection contract completely.

```bash
python -m ctrt.human_reference_annotation_web \
  --annotator-id rater-001 \
  --workspace .ctrt/human-reference
```

It delegates every substantive operation unchanged:

| Surface action | Delegated to |
| --- | --- |
| create or resume an assignment | `open_assignment` |
| show one item | `AnnotationSession.next_packet` / `packet_for` |
| record a response | `AnnotationSession.record` |
| correct a response | `AnnotationSession.supersede` |
| progress and resumption | `answered_item_ids` / `unanswered_item_ids` / `counts` |
| completion | `AnnotationSession.complete` |
| receipt | `verify_collection` |

**No second collection lifecycle exists.** The surface owns no storage logic, no response shape, and no validation rule of its own.

## Blinding by construction

The surface is blinded because it has no structure capable of carrying a leak: no import of any candidate, characterization, evaluation, or synthesis module; no field, route, or template that could hold a candidate identity or output; and no path that reads another annotator's store.

This is verified behaviorally rather than by scanning prose. One test walks the entire surface — progress, item, record, correction form, correction, completion, receipt — and asserts no page contains any leak term. Another asserts that a completed assignment writes no artifact ID containing `synthesis`, `evaluation`, `candidate`, or `vader`. A third asserts a second annotator sees nothing of the first.

## Not linked from the product launcher

`local_browser_launcher` links the two **product doors**, whose result pages display analyzer identities and outputs. Annotation is a blinded research instrument for a different audience.

Linking it from that landing page would put a blinding leak one click away from an annotator and would blur a research instrument into a product. The annotation surface therefore runs as its own command on its own port, and a test asserts the launcher does not import it.

## Two idempotency defects found and fixed in the new surface

Both were found by running the surface, not by reading it, and both are in the new module — no merged contract was changed.

1. **Assignment persistence.** `open_assignment` stamps a fresh `created_at` on every call, so persisting collection inputs on every request tried to bind a second hash to an append-only artifact ID and raised `ArtifactConflictError` on the second page load. Fixed by persisting once and reusing the first stored assignment; item order is derived deterministically and reverified by `verify_against`, so nothing analytical depends on the timestamp.
2. **Completion.** `complete()` likewise re-stamps `completed_at`, so viewing a receipt twice conflicted. Fixed by writing the completion once and rereading it afterward. Viewing a receipt must not rewrite the record it reports.

Both are properties of a request/response surface that the one-shot CLI never exercised.

## One narrow pre-existing test fix

`tests/test_candidate_reference_evaluation.py::test_production_entry_point_refuses_fixture_collections` fails on `main` at `432b7b2` with `AttributeError`. PR #70 moved the lifecycle — and `load_vader_sentiment_adapter` with it — into `_candidate_reference_evaluation_lifecycle`, but the test still patches the public module, so it dies at setup.

The production behavior is correct: patching the loader where it now lives confirms fixtures are rejected and the loader is never called. But the test proving that was inert, leaving the fixture boundary unverified and the suite red.

Fixed by repointing the patch at the module that actually resolves the name, and adding an explicit assertion that the loader was never invoked. No production contract changed.

## Privacy

The annotator ID is a locally chosen pseudonymous label validated against the existing narrow format. **It is not a login, not authentication, and not identity verification**, and the surface says so on every page. No personal-information field exists; a test asserts the app carries no field named for a person and the form offers no email, name, or password input.

Local artifact storage is unencrypted, the server has no accounts or encryption, and none of it is production software. All of that is stated in the interface itself, not only in documentation.

## Fixture boundary

Tests generate fixtures at runtime through the real collection mechanics in temporary directories. Nothing invented is committed, and the PR #64 and PR #70 fixture checks are untouched and still enforced.

## Consequences

### Positive

- All eight response fields and correction are reachable by an actual annotator for the first time.
- Blinding is a structural property of the module, checked by walking the real surface.
- Two append-only idempotency defects were caught before any real annotator hit them.
- The suite is green again, and the fixture-boundary property is verified rather than merely asserted.

### Costs

- A third local server exists, deliberately not discoverable from the launcher, so operators must be told about it.
- A terminal path and a browser path now both exist over one contract; the terminal path remains narrower.

## Reopening criterion

Revisit when real annotators report the surface is unusable in a specific way, when a recruitment or consent process requires anything this ADR forbids collecting, or when multiple annotators need coordinating beyond one independent assignment each.
