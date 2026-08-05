# ADR-0065: Collect blinded human-reference annotations without fabricating ground truth

- **Status:** Accepted
- **Date:** 2026-08-05
- **Phase:** 1B empirical preparation

## Context

ADR-0063 admitted VADER for evaluation. ADR-0064 recorded what the implementation does on frozen probes and was explicit that doing so establishes nothing about correctness. Both ADRs closed by naming the same missing ingredient: human-referenced data collected under a declared protocol.

The `sentiment_valence` dimension record has required this from the beginning. Its `validation_requirements` list opens with:

```text
Human annotation agreement under written instructions.
```

So this is not a new demand invented to justify work. It is a standing, declared prerequisite that has never been met.

The danger in meeting it is specific and well understood. The moment humans supply labels, there is enormous pressure to treat those labels as truth — to average them, vote on them, adjudicate them into a single answer, and then measure an analyzer against that answer as though the answer were correct. Every one of those steps discards evidence, and the discarded evidence is exactly the part that matters: where competent readers disagreed, where context was missing, and where a responsible reader declined to answer at all.

## Decision

Build a blinded, append-only human-reference collection path that preserves independent judgments and **computes nothing**.

**Human-reference annotations preserve independent judgments under a declared protocol. They do not become ground truth merely because humans supplied them.**

**Disagreement, ambiguity, insufficient context, and abstention are evidence to preserve, not errors to erase.**

### What this PR does not do

It does not run VADER, reveal VADER to annotators, compare annotations with analyzer results, compute accuracy or agreement or calibration or ranking, produce a consensus label, select VADER for anything, change the candidate lifecycle, or expose VADER through any creator surface. The candidate remains `eligible_for_evaluation`.

## A separate corpus, deliberately

The behavioral-characterization corpus was **not** reused. Its probes were written to exercise documented implementation rules — several exist only as metamorphic base/variant pairs differing by one token. Handing those to a human reader would produce judgments about artificial minimal pairs, not about language anyone would write.

`docs/corpora/human-reference-sentiment.v0.1.0.json` is a separate frozen corpus of 48 original CTRT-authored short-form English items across 16 design categories. No scraped content, no external dataset, no personal information, no population claim.

### Design categories are not answers

Categories name **linguistic constructions**, not expected responses: `negation_construction`, `contrastive_construction`, `intensifier_present`, `underspecified_reference`, `irony_or_sarcasm_risk`, and so on. Each item carries a neutral `includes_condition` description and `not_an_expected_response: true`.

This is enforced, not merely intended. The parser rejects any item carrying an answer-shaped key (`label`, `gold_label`, `ground_truth`, `expected_response`, `valence`, `score`, …), and the corpus contract rejects any design category whose name matches a response option.

Fourteen items are tagged `plausible_abstention` or `underspecified_reference` precisely so that abstention is a realistic outcome rather than a theoretical one.

## Annotation scale

One versioned, ordered categorical scale with a first-class abstention option:

```text
strongly_unfavorable
somewhat_unfavorable
neither_clearly_favorable_nor_unfavorable
somewhat_favorable
strongly_favorable
cannot_determine_responsibly
```

The categorical value is preserved exactly as entered. An `ordinal_position` exists in the protocol document, and the protocol says plainly what it is:

> The ordinal_position field exists only as a declared serialization convenience for storage and display ordering. It is NOT an interval measurement. Distances between adjacent positions are not equal, not meaningful, and must never be averaged, summed, or treated as a numeric score.

The abstention option carries `ordinal_position: null` so it cannot silently become a number at all.

### Separate fields stay separate

Valence judgment, context sufficiency, perceived ambiguity, abstention state and reason, optional rationale, optional supporting spans, self-reported certainty, and protocol acknowledgment are all recorded independently. None is derived from another. An annotator may record a strong valence judgment *and* insufficient context *and* high ambiguity; that combination is informative and the contract permits it.

`abstained` must be true exactly when the label is the abstention option — never inferred from anything else. An abstention requires a reason; a valence judgment may not carry one.

**Self-reported certainty is a statement about a person.** It is never analyzer confidence, and the response record has no confidence, calibration, or instrument-probability field for it to leak into.

## Blinding

An annotation packet has **no field** capable of carrying a candidate name, package identity, analyzer output, characterization outcome, expectation result, or registry status. Blinding is a property of the data structure, not a promise in prose.

Tests verify this behaviorally: they serialize every packet in a full assignment and assert the absence of candidate identity, and they assert stored annotation artifacts contain none of the forbidden keys.

## Pseudonymity and its honest limit

Annotator identity is a locally chosen pseudonymous ID matching `^[a-z][a-z0-9-]{2,31}$` — a format deliberately too narrow to hold an email address, a phone number, an account handle, or a path fragment. No legal names, contact details, account identifiers, IP addresses, or demographic profiles are collected.

The limit is stated rather than glossed: **a pseudonymous ID is still linkable if whoever distributes the study keeps a separate mapping.** CTRT does not create, request, or store such a mapping, and cannot prevent someone else from keeping one.

## Deterministic assignment

Each annotator receives a deterministic permutation derived by SHA-256 from the method identity, corpus hash, and annotator ID — **not** from Python's process-randomized `hash()`. A rotation offset plus a stride co-prime with the item count guarantees a full permutation, so different annotators see different orders while the corpus identity is unchanged.

The assignment binds corpus identity and hash, protocol identity and hash, the pseudonymous ID, exact item IDs and order, generation method and version, and creation time. It refuses to verify when any of those drifts.

## Append-only, never overwritten

Responses are content-addressed canonical artifacts at `{assignment}:{item}:response:{sequence}`. Recording twice is refused. A correction is a **new** superseding record at the next sequence, naming its exact predecessor and carrying a reason; the original stays in the store, unchanged and readable.

An item's history is reconstructed from storage by walking the sequence, so a partially completed assignment resumes exactly with no mutable index to corrupt. "Never answered" and "explicitly abstained" are distinct states throughout.

Completion is written only when every assigned item carries a judgment or an explicit abstention, and everything is re-read and rehashed before a receipt or report is trusted.

## No aggregation, by construction

This PR computes no majority, average, median, consensus, adjudicated label, inter-annotator agreement statistic, merged human score, or gold answer. The protocol document sets `aggregation_permitted: false` and the parser refuses to load a protocol claiming otherwise. A test asserts no public name in either module contains `majority`, `consensus`, `average`, `median`, `adjudicat`, `agreement`, `gold`, or `merge`.

Aggregation and adjudication are genuinely hard design problems — how to weight abstentions, whether disagreement indicates item ambiguity or annotator variation, what an "agreement" statistic even means when abstention is a valid response. They deserve their own protocol and their own ADR, made deliberately rather than as a side effect of collection.

## Required later work

Before any empirical comparison or selection:

1. an accepted aggregation and adjudication protocol that preserves rather than erases disagreement;
2. a declared empirical metric set with stated assumptions about the ordinal scale;
3. multiple independent annotators per item, and a stated recruitment and eligibility policy;
4. an analysis plan preregistered before any analyzer output is placed beside these annotations;
5. subgroup and identity-term bias analysis;
6. a corpus large and varied enough to support the claims made from it;
7. resolution of both open licensing questions; and
8. a separate accepted, domain-bounded selection record.

The candidate lifecycle stays `eligible_for_evaluation` and licensing stays `provisionally_verified` until all of that exists.

## Consequences

### Positive

- A standing `sentiment_valence` validation requirement now has a real collection path.
- Abstention, ambiguity, and insufficient context are first-class recorded evidence rather than missing data.
- Corrections are auditable: the original judgment and the reason for changing it both survive.
- Blinding and answer-freeness are structural properties enforced by parsers and dataclass shapes, not conventions.

### Costs

- The corpus is small and repository-authored, so it supports method development rather than population claims.
- A terminal workflow limits how many annotators can realistically participate.
- Preserving every independent judgment means the eventual aggregation protocol inherits a harder problem than "average the numbers" — which is the point, and also genuinely more work.

## Reopening criterion

Revisit when an aggregation and adjudication protocol is proposed, when multiple annotators have completed assignments and the collected evidence reveals a contract defect, when the corpus must grow beyond a pilot, or when a recruitment policy requires collecting anything this ADR currently forbids.
