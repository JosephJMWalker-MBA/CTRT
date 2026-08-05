# Phase 1B: human-reference annotation protocol and operating guide

> **Human-reference annotations preserve independent judgments under a declared protocol. They do not become ground truth merely because humans supplied them.**
>
> **Disagreement, ambiguity, insufficient context, and abstention are evidence to preserve — not errors to erase.**

This guide covers CTRT's first blinded human-reference collection path.

See [ADR-0065](adr/0065-collect-blinded-human-reference-annotations-without-fabricating-ground-truth.md) for the decision record.

## What this is and is not

This collects independent human judgments about one declared dimension. It does **not** run, name, reveal, or compare against any analyzer. No accuracy, agreement, calibration, consensus, or ranking is computed anywhere in this path.

The candidate lifecycle is unchanged: `vader.sentiment` remains `eligible_for_evaluation`. Licensing remains `provisionally_verified`.

## Running a session

No optional dependency is required. This works in the ordinary dependency-free environment:

```bash
pip install -e ".[dev]"
```

Start or resume an annotator's assignment:

```bash
python -m ctrt.human_reference_annotation \
  --annotator-id rater-001 \
  --workspace .ctrt/human-reference
```

Limit one sitting to a fixed number of items:

```bash
python -m ctrt.human_reference_annotation \
  --annotator-id rater-001 \
  --workspace .ctrt/human-reference \
  --limit 10
```

Render the collection report for a completed assignment:

```bash
python -m ctrt.human_reference_annotation \
  --annotator-id rater-001 \
  --workspace .ctrt/human-reference \
  --report collection-rater-001.md
```

Stopping mid-assignment is expected. Re-running the same command resumes from stored artifacts at the exact next unanswered item.

## Corpus design

`docs/corpora/human-reference-sentiment.v0.1.0.json` — frozen, **48 items**, 16 design categories, original CTRT-authored short-form English.

| Property | Value |
| --- | --- |
| Authorship | Written specifically for CTRT |
| External dataset | none |
| Scraped social media or published posts | none |
| Personal information | none |
| Expected responses / gold labels | **none** |
| Population claim | **none** |

### Why a separate corpus

The behavioral-characterization corpus was **not** reused. Its probes exercise documented implementation rules, and several exist only as metamorphic base/variant pairs differing by a single token. Asking a human to judge artificial minimal pairs would produce judgments about the test design rather than about language. Behavioral probes and human-reference items serve different purposes and are kept apart.

### Categories describe design, never the answer

Categories name linguistic constructions:

`capitalization_emphasis`, `context_dependent_reference`, `contrastive_construction`, `conventionally_favorable_vocabulary`, `conventionally_unfavorable_vocabulary`, `diminisher_present`, `emoticon_or_emoji`, `intensifier_present`, `irony_or_sarcasm_risk`, `mixed_valence_vocabulary`, `negation_construction`, `plausible_abstention`, `primarily_factual_wording`, `punctuation_emphasis`, `slang_or_informal`, `underspecified_reference`

Each item also carries a neutral `includes_condition` description and `not_an_expected_response: true`.

This is enforced by the parser, not just intended: an item carrying `label`, `gold_label`, `ground_truth`, `expected_response`, `valence`, `score`, or similar is rejected outright, and a design category may not be named after a response option.

Items tagged `plausible_abstention` and `underspecified_reference` exist so that declining to answer is a realistic outcome, not a theoretical one.

## Annotation scale

Scale `scale.sentiment-valence-favorability` @ `0.1.0`, an ordered categorical scale with a first-class abstention option:

| Value | Ordinal position |
| --- | --- |
| `strongly_unfavorable` | 0 |
| `somewhat_unfavorable` | 1 |
| `neither_clearly_favorable_nor_unfavorable` | 2 |
| `somewhat_favorable` | 3 |
| `strongly_favorable` | 4 |
| `cannot_determine_responsibly` | **null** |

The categorical value is preserved exactly as entered.

> `ordinal_position` exists only as a declared serialization convenience for storage and display ordering. It is **not** an interval measurement. Distances between adjacent positions are not equal, not meaningful, and must never be averaged, summed, or treated as a numeric score.

The abstention option has no ordinal position at all, so it cannot quietly become a number.

## Response fields

Each is recorded separately and none is derived from another:

| Field | Required | Notes |
| --- | --- | --- |
| `valence_label` | yes | One exact scale value |
| `abstained` | yes | True exactly when the label is the abstention option |
| `abstention_reason` | when abstained | Required on abstention, forbidden otherwise |
| `context_sufficiency` | yes | `sufficient` / `insufficient` / `unsure` |
| `perceived_ambiguity` | yes | `none` / `some` / `high` |
| `self_reported_certainty` | no | `low` / `medium` / `high` |
| `rationale` | no | Free text |
| `supporting_spans` | no | Must fall inside the exact item text |
| `protocol_acknowledgment` | yes | Exact protocol ID, version, and hash |

A strong valence judgment can coexist with insufficient context and high ambiguity. That combination is informative and the contract permits it.

### Certainty is not confidence

**Self-reported annotator certainty is a statement about a person.** It is never analyzer confidence, never calibrated, and never populates any CTRT instrument-confidence field. The response record has no confidence, calibration, or instrument-probability field for it to leak into.

### Abstention is a real answer

Annotators may always abstain. Missing context is never coerced into a valence label. "Not yet answered" and "explicitly abstained" are distinct states everywhere in the system, including the completion check and the lifecycle counts.

## Blinding rules

An annotation packet contains no candidate name, package identity, analyzer identity, analyzer output, characterization outcome, expectation result, registry status, model comparison, or hint that a particular response is expected.

This is structural: the packet dataclass has **no field** capable of holding any of it. Tests verify blinding behaviorally by serializing every packet in a full assignment and by scanning stored artifacts — not by grepping documentation.

## Privacy and pseudonymity

Annotator identity is a locally chosen pseudonymous ID matching:

```text
^[a-z][a-z0-9-]{2,31}$
```

The format is deliberately too narrow to hold an email address, a phone number, an account handle, or a path fragment. `person@example.com`, `Jane Doe`, `+15555550123`, and `../escape` are all rejected.

CTRT does **not** collect legal names, email addresses, phone numbers, account identifiers, IP addresses, demographic profiles, or unrelated personal information.

### The honest limit

**A pseudonymous ID is still linkable if whoever distributes the study keeps a separate mapping from IDs to people.** CTRT does not create, request, or store such a mapping, and cannot prevent someone else from keeping one. Anyone running a study with real annotators is responsible for that risk, for informed consent, and for any applicable review requirements. None of that is provided here.

Annotation text is written to disk unencrypted in the workspace and is not cleaned up.

## Assignment

Each annotator receives a deterministic permutation of the frozen corpus, derived by SHA-256 from the method identity, corpus hash, and annotator ID — **not** from Python's process-randomized `hash()`, which differs between runs.

A rotation offset plus a stride co-prime with the item count guarantees a full permutation. Different annotators receive different orders; the corpus identity is unchanged by reordering.

The assignment binds corpus identity and hash, protocol identity and hash, the pseudonymous ID, exact item IDs and order, generation method and version, creation time, and completion state. It refuses to verify if any of those drift.

## Append-only correction and supersession

Responses are stored as content-addressed canonical artifacts:

```text
{assignment_id}:{item_id}:response:{sequence}
```

Recording a second response for the same item is **refused**. Nothing is ever mutated or deleted.

To correct a submitted annotation, record a **superseding** response:

- it is appended at the next sequence number;
- it names the exact predecessor `response_id`;
- it carries a required reason; and
- the original remains in the store, unchanged and readable.

The report shows the full ancestry chain, marking the original and the reason for each correction.

## Artifact graph

```text
annotation protocol        (frozen, aggregation forbidden)
evaluation corpus          (frozen, answer-free, repo-authored)
annotator assignment       (deterministic, immutable)
    ↓
annotation response :0     ← one per item, append-only
annotation response :1     ← optional supersession, names its predecessor
    ↓
assignment completion      ← only when nothing is unanswered
    ↓
verified collection receipt ← after read-time rehashing
    ↓
deterministic Markdown report
```

The human-readable report is **never** the controlling artifact. It is rendered only from reverified stored records.

## Validation rules

Rejected: malformed or identifying annotator IDs; corpus or protocol hash mismatch; assignment item reordering; an item outside the frozen corpus; a response outside the versioned scale; a valence label combined with an incompatible abstention state; evidence spans outside the exact text; duplicate record identity with different content; supersession without an exact predecessor; completion with unanswered items; tampered stored bytes; candidate or analyzer fields inside annotation artifacts; and any attempt to overwrite an existing response.

## Human reference is not infallible ground truth

A human judgment is evidence about how one reader, under one written protocol, read one passage. It is not a fact about the passage.

Competent readers disagree about sentiment, especially with irony, quotation, domain vocabulary, and underspecified reference — several corpus items exist specifically to surface that. When they disagree, the disagreement is the finding. Averaging it away would destroy the most informative part of the data and replace it with a number that no annotator actually asserted.

## No aggregation in this PR

This collection computes **no** majority, average, median, consensus, adjudicated label, inter-annotator agreement statistic, merged human score, or gold answer.

The protocol document sets `aggregation_permitted: false`, and the parser refuses to load a protocol claiming otherwise.

Aggregation and adjudication are hard design problems in their own right — how to weight abstentions, whether disagreement reflects item ambiguity or annotator variation, what "agreement" means when abstention is valid. They require a separate, later, explicitly accepted protocol and their own ADR.

## Required later work

Before any empirical comparison, metric, or selection:

1. an accepted aggregation and adjudication protocol that preserves rather than erases disagreement;
2. a declared empirical metric set with stated assumptions about the ordinal scale;
3. multiple independent annotators per item, with a stated recruitment and eligibility policy;
4. an analysis plan preregistered before any analyzer output is placed beside these annotations;
5. subgroup and identity-term bias analysis;
6. a corpus large and varied enough to support the claims made from it;
7. resolution of both open licensing questions; and
8. a separate accepted, domain-bounded selection record.

## Validating both dependency states

The annotation path behaves identically with and without the optional VADER dependency, and never imports it:

```bash
python -m pytest tests/test_human_reference_annotation.py -q
```

All tests run and pass in both environments — nothing in this path is skipped when VADER is absent.
