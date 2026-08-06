# ADR-0066: Synthesize human-reference collections descriptively

- **Status:** Accepted
- **Date:** 2026-08-05
- **Phase:** 1B empirical preparation

## Context

ADR-0065 built a blinded, append-only path for collecting independent human judgments and deliberately computed nothing. It closed by naming the missing piece: a protocol for combining multiple collections, made deliberately rather than as a side effect.

That is this decision. It is the point of maximum temptation in the whole sequence. Multiple annotators have now judged the same items; the obvious next move is to vote, average, or adjudicate them into one answer per item and call the result ground truth. Every one of those moves discards the most informative part of the data — where competent readers diverged, where context was missing, where someone responsibly declined.

**Human-reference synthesis describes the judgments collected under a declared protocol. It does not convert those judgments into truth.**

**Disagreement is a result to preserve. It is not automatically a defect requiring majority rule or adjudication.**

## Terminology

This capability is *synthesis*, or a *descriptive human-reference summary*. It is not "ground-truth aggregation", and that phrase does not appear in the protocol, the code, or the report. The wording matters because the name would license the behavior.

## Decision

Add a frozen, preregistered synthesis protocol and a research-only path that combines multiple verified collection receipts into a descriptive record while preserving every independent judgment.

### Minimum coverage: three distinct completed assignments

Three is the smallest coverage at which an item can show a *split* rather than only a match or a mismatch. With two references, every item is either identical or different, which cannot distinguish an isolated reading from a genuine division. Three makes disagreement visible.

It is a pilot floor chosen for that reason, **not** a power calculation, and it supports no inferential claim.

Items below the threshold are retained and reported as `insufficient_reference_coverage`. Missing responses are never estimated, imputed, or interpolated, and low-coverage items are never silently dropped.

### Input eligibility

Only verified collection receipts binding the identical annotation protocol (id, version, hash), evaluation corpus (id, version, hash), response scale, content identities and hashes, and extraction provenance are admitted. Everything is reloaded and rehashed from canonical storage; nothing is trusted from memory.

Rejected: duplicate annotator IDs, IDs outside the safe pseudonymous format, incompatible protocol or corpus references, incomplete assignment receipts, reordered or missing corpus membership, branching or broken supersession ancestry, responses not belonging to the exact assignment, tampered bytes, candidate or analyzer fields inside human-reference artifacts, and anything that cannot be reverified.

No mapping from pseudonymous ID to a real person is created, requested, inferred, or stored.

### Supersession

The effective response is resolved only through an exact append-only chain beginning at sequence zero, where each later record names its immediate predecessor and carries a reason, and the final record matches the reference the assignment completion bound.

A chain with a branch, a gap, or a missing predecessor is **rejected rather than repaired**. A record appended after completion also invalidates the receipt, because the completion no longer describes the store. Every superseded record is preserved, reported, and never hidden.

## Permitted descriptive measures

Per item: a count for **every** response option including options with zero observations; abstention count with preserved reasons; unanswered count; context-sufficiency, ambiguity, and certainty counts across all options; rationale-presence and span-presence counts; distinct annotator count; explicit coverage status; and immutable source response references.

Abstention remains its own category, retains its reasons, and is never numerically encoded.

### Concordance, denominator-preserving

This is the explicit protocol in which limited human–human concordance descriptions are introduced. Two are permitted, reported separately and never merged:

1. **Pairwise exact-category concordance including abstention** — abstention counts as its own category; numerator and denominator both preserved.
2. **Pairwise exact-category concordance among non-abstaining pairs** — a separate numerator and denominator.

Neither may be called accuracy; the `ConcordancePair` contract rejects a label containing that word.

3. **Ordinal-distance histogram** over exact buckets 0–4 for non-abstaining pairs. Ordinal positions are a serialization convenience for computing a distance between two categorical responses. They are not interval-scale truth, and no mean response label is derived from them anywhere.

Preserving numerator and denominator separately is what keeps these descriptive: a bare rate invites reading as a score, while "1 of 3 pairs" cannot be mistaken for one.

## Prohibited in this PR

Majority labels, modes presented as answers, medians, means, mean ordinal responses, consensus labels, adjudicated labels, gold answers, "correct" labels, merged human scores, annotator rankings or quality scores, candidate metrics, Krippendorff's alpha, Cohen's kappa, Fleiss' kappa, any other named reliability coefficient, significance testing, and inferential population claims.

Named reliability statistics carry real assumptions about scale type and about what disagreement means. Letting one in accidentally, as a convenience, would import those assumptions unexamined. They require their own methodology decision.

This is enforced structurally rather than by prose: tests assert no public API name and no dataclass field matches any forbidden concept, that every synthesized quantity is an integer count with no float anywhere, and — behaviorally — that when two annotators agree and one differs, nothing in the record or the stored artifact marks the pair as the answer.

## Test fixtures are not evidence

No invented annotation responses are committed. Tests generate clearly labeled fixtures at runtime through the **real** collection path, and mark them with a separate marker artifact declaring `synthetic_test_fixture: true` and `not_human_research_evidence: true`.

A marker artifact was chosen over new fields on `AnnotationResponse` because that record is an existing collection contract this PR must not alter. Production synthesis scans every included store and refuses any marked collection; only an explicit test-only entry point accepts them. Repository documentation reports no fixture distribution as an empirical result.

## Candidate lifecycle and licensing unchanged

The candidate remains `eligible_for_evaluation`; licensing remains `provisionally_verified`. Nothing here runs, imports, names, reveals, compares against, evaluates, or selects any analyzer. The registry is untouched and records nothing about this synthesis.

## Required later work

Before binding human-reference synthesis to a blinded analyzer evaluation:

1. an accepted adjudication protocol, if adjudication is ever wanted, that preserves rather than erases disagreement;
2. an explicit methodology decision admitting any named reliability coefficient, with its scale assumptions stated;
3. a declared empirical metric set and an analysis plan preregistered before any analyzer output is placed beside these judgments;
4. a blinding procedure for the comparison step itself;
5. subgroup and identity-term bias analysis;
6. a corpus and annotator pool large enough to support the claims made from them;
7. resolution of both open candidate licensing questions; and
8. a separate accepted, domain-bounded selection record.

## Consequences

### Positive

- Multiple collections can now be combined without any of them losing their identity.
- Disagreement, abstention, ambiguity, and insufficient context survive combination intact.
- Concordance is available for method development while remaining structurally unable to become an accuracy claim.
- The fixture boundary keeps synthetic test data from ever being reported as human evidence.

### Costs

- Preserving everything makes the record larger and harder to summarize than a single label per item — which is the point, and also genuinely more work for whatever consumes it.
- Anyone wanting a familiar reliability coefficient must first make an explicit methodology decision, which is friction by design.
- Three-reference coverage on a 48-item corpus is a pilot, not a study.

## Reopening criterion

Revisit when an adjudication or reliability-coefficient methodology is proposed, when real collections reveal a contract defect, when coverage must scale beyond a pilot, or when the analyzer-comparison step is designed and needs synthesis output bound to it.
