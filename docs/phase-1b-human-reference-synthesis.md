# Phase 1B: human-reference synthesis — operating and interpretation guide

> **Human-reference synthesis describes the judgments collected under a declared protocol. It does not convert those judgments into truth.**
>
> **Disagreement is a result to preserve. It is not automatically a defect requiring majority rule or adjudication.**
>
> **This protocol permits descriptive human–human concordance. It does not establish correctness, population validity, or candidate fitness.**

This guide covers CTRT's first preregistered human-reference synthesis.

See [ADR-0066](adr/0066-synthesize-human-reference-collections-descriptively.md) for the decision record and [ADR-0065](adr/0065-collect-blinded-human-reference-annotations-without-fabricating-ground-truth.md) for the collection path it consumes.

## Terminology

This capability is **synthesis**, or a **descriptive human-reference summary**. It is deliberately not called "ground-truth aggregation" — that name would license behavior this protocol forbids.

## Running a synthesis

No optional dependency is required, and no network access occurs:

```bash
pip install -e ".[dev]"
```

Each `--receipt` is a verified collection receipt ID — the assignment completion artifact ID produced when an annotator finished their assignment:

```bash
python -m ctrt.human_reference_synthesis \
  --workspace .ctrt/human-reference \
  --receipt assignment.corpus.human-reference-sentiment.rater-001:completion \
  --receipt assignment.corpus.human-reference-sentiment.rater-002:completion \
  --receipt assignment.corpus.human-reference-sentiment.rater-003:completion
```

Write the report to a file:

```bash
python -m ctrt.human_reference_synthesis \
  --workspace .ctrt/human-reference \
  --receipt <receipt-id> --receipt <receipt-id> --receipt <receipt-id> \
  --output synthesis.md
```

The command locates each receipt across the per-annotator stores under the workspace, reverifies everything from canonical storage, persists append-only synthesis artifacts, and writes the deterministic report. It never displays or requests analyzer information.

## Minimum coverage and why three

```text
minimum_distinct_annotators_per_item = 3
```

Three is the smallest coverage at which an item can show a **split** rather than only a match or a mismatch. With two references, every item is either identical or different, which cannot distinguish one unusual reading from a genuine division among readers.

This is a pilot floor chosen to make disagreement visible. It is **not** a power calculation and supports no inferential claim.

Items below the threshold are retained and reported with explicit status:

```text
insufficient_reference_coverage
```

Missing responses are never estimated, imputed, or interpolated, and low-coverage items are never silently removed.

## Input eligibility

A receipt is admitted only if it binds the identical annotation protocol (id, version, hash), evaluation corpus (id, version, hash), response scale, content identities and hashes, and extraction provenance.

Rejected: duplicate annotator IDs; IDs outside the safe pseudonymous format; incompatible protocol or corpus references; incomplete assignment receipts; reordered or missing corpus membership; branching or broken supersession ancestry; responses not belonging to the exact assignment; tampered stored bytes; candidate or analyzer fields inside human-reference artifacts; and anything that cannot be reverified from canonical storage.

Receipts are ordered deterministically by pseudonymous annotator ID, so the argument order on the command line does not affect the result.

## Permitted descriptive measures

Per item:

- a count for **every** response option, including options with zero observations;
- abstention count, with abstention reasons preserved;
- unanswered count;
- context-sufficiency counts across all options;
- perceived-ambiguity counts across all options;
- self-reported-certainty counts across all options plus `not_provided`;
- rationale-presence count;
- supporting-span-presence count;
- number of distinct annotators;
- exact coverage status; and
- immutable source response references.

Zero-count categories are always shown. Omitting them would quietly imply that nobody could have chosen them.

### Concordance, with denominators preserved

Two concordance descriptions, reported **separately** and never merged:

| Description | Basis |
| --- | --- |
| `pairwise-exact-category-including-abstention` | Abstention counts as its own category |
| `pairwise-exact-category-non-abstaining` | Only pairs where neither reader abstained |

Both preserve numerator **and** denominator — "1 of 3 pairs", never a bare rate. A bare rate invites reading as a score; a preserved fraction cannot be mistaken for one.

Neither may be called accuracy. The contract rejects any concordance label containing that word.

### Ordinal-distance histogram

Exact buckets 0–4, for non-abstaining pairs only:

```text
| Distance | Pairs |
```

Ordinal positions are a **serialization convenience** used only to compute a distance between two categorical responses. They are not interval-scale truth, and **no mean response label is derived from them**. Abstention has no ordinal position and never enters a distance.

## Why the protocol refuses a single consensus label

A vote, average, or adjudicated label replaces several real judgments with one that no annotator actually made. Where readers agreed, the label adds nothing. Where they disagreed — the informative case — it erases exactly the finding.

Competent readers genuinely differ on irony, quotation, domain vocabulary, and underspecified reference. Several corpus items exist specifically to surface that. Collapsing those items would convert the most interesting evidence into the least.

So this protocol produces no majority label, mode-as-answer, median, mean, mean ordinal response, consensus label, adjudicated label, gold answer, "correct" label, merged human score, or annotator ranking — and no named reliability coefficient (Krippendorff's alpha, Cohen's kappa, Fleiss' kappa, or any other).

Named reliability statistics carry real assumptions about scale type and about what disagreement means. Admitting one as a convenience would import those assumptions unexamined. They require a separate, explicit methodology decision.

## How abstention and ambiguity are preserved

Abstention is its own response category. It retains its reasons, is never numerically encoded, never enters a distance calculation, and is never treated as missing data or as a lower-quality response.

Context sufficiency, perceived ambiguity, and self-reported certainty are counted independently of the valence distribution and of each other. None is derived from another.

Self-reported certainty is a statement about a person. It is never analyzer confidence.

## Supersession resolution

The effective response is resolved only through an exact append-only chain:

- the chain begins at sequence zero with no predecessor;
- each later record names its exact immediate predecessor and carries a reason;
- the final record must match the reference the assignment completion bound;
- a branch, gap, or missing predecessor is **rejected rather than repaired**; and
- every superseded record is preserved, reported, and never deleted or hidden.

A record appended *after* completion also invalidates the receipt, because the completion no longer describes the store.

For each synthesized response the record preserves the original reference, every supersession reference in order, the effective reference, the reasons, and proof the chain is unbroken.

## Artifact graph

```text
synthesis protocol            (frozen, preregistered)
synthesis plan                (names exactly which receipts)
ordered receipt manifest
    ↓
effective-response resolution records   (one per annotator per item)
per-item descriptive synthesis records
corpus-level lifecycle summary
    ↓
synthesis completion marker
    ↓
verified synthesis receipt    (after read-time rehashing)
    ↓
deterministic Markdown report
```

The human-readable report is **derived presentation**. The canonical stored artifacts remain controlling. Every stored input is rehashed before the synthesis or the report is trusted.

## Privacy and pseudonymity limits

Synthesis reads locally chosen pseudonymous annotator IDs only, and requires them to be distinct.

It does **not** create, request, infer, or store any mapping from a pseudonymous ID to a real person.

**A pseudonymous ID may still be linkable if whoever distributed the study keeps such a mapping separately.** CTRT cannot prevent that and does not participate in it.

## Fixture versus real evidence

No invented annotation responses are committed to this repository, and no distribution shown in any documentation is an empirical result.

Tests generate clearly labeled fixtures at runtime through the **real** collection path and mark them with a separate marker artifact:

```text
synthetic_test_fixture: true
not_human_research_evidence: true
```

A marker artifact is used rather than new fields on the annotation response, because that record is an existing collection contract this work must not alter.

**Production synthesis refuses any collection carrying that marker.** Only an explicit test-only entry point accepts them.

## Candidate lifecycle and licensing

```text
vader.sentiment → eligible_for_evaluation
```

Unchanged. Licensing remains `provisionally_verified`. Nothing in this path runs, imports, names, reveals, compares against, evaluates, or selects any analyzer, and the registry records nothing about this synthesis.

## Required later work

Before binding human-reference synthesis to a blinded analyzer evaluation:

1. an accepted adjudication protocol, if adjudication is ever wanted, that preserves rather than erases disagreement;
2. an explicit methodology decision admitting any named reliability coefficient, with its scale assumptions stated;
3. a declared empirical metric set and an analysis plan preregistered before any analyzer output is placed beside these judgments;
4. a blinding procedure for the comparison step itself;
5. subgroup and identity-term bias analysis;
6. a corpus and annotator pool large and varied enough to support the claims made from them;
7. resolution of both open candidate licensing questions; and
8. a separate accepted, domain-bounded selection record.

Until all of that exists, this synthesis remains a descriptive research record and nothing more.
