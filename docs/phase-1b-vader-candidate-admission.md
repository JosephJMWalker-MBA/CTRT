# Phase 1B: VADER candidate admission

> **Candidate admission authorizes evaluation. It does not establish analytical validity and does not authorize creator-facing use.**

This guide covers the admission of `vaderSentiment==3.3.2` as CTRT's first real analyzer candidate.

VADER is **not** selected for any domain, **not** wired into creator preflight, the local CLI, or the browser surface, and **not** claimed to measure sentiment correctly. It is admitted so that it can be evaluated.

See [ADR-0063](adr/0063-admit-vader-as-the-first-real-analyzer-candidate.md) for the decision record.

## Installation

VADER is an optional extra. The default install stays dependency-free.

```bash
pip install "ctrt-framework[vader]"
```

That resolves to exactly:

```text
vaderSentiment==3.3.2
```

Pin it exactly. Do **not** substitute the similarly named `vader-sentiment` distribution — it is a different package.

Everything else in CTRT works without it:

```bash
pip install -e ".[dev]"          # no VADER; all synthetic paths work
python -m ctrt.creator_preflight_local --draft-file draft.txt --intent "..."
python -m ctrt.creator_preflight_web
```

When the extra is absent and the adapter is explicitly requested, it fails closed:

```text
VaderDependencyError: optional candidate dependency vaderSentiment==3.3.2 is not
installed; install it with `pip install "ctrt-framework[vader]"`
```

## Registry status

Recorded in `docs/candidates/real-registry.v0.1.0.json`, a **separate** registry. The frozen synthetic registry is unmodified.

```text
registry_id:  registry.real-candidates
candidate_id: vader.sentiment
status:       eligible_for_evaluation
```

It is **not** `evaluated` and **not** `selected_for_domain`.

| Bound fact | Value |
| --- | --- |
| Analyzer ID | `vader.sentiment.polarity` |
| Provider | `cjhutto.vaderSentiment` |
| Distribution | `vaderSentiment` |
| Package version | `3.3.2` |
| Adapter revision | `ctrt-vader-adapter@0.1.0` |
| Taxonomy | `sentiment.vader.polarity-scores` @ `3.3.2` |
| Dimension | `sentiment_valence` @ `0.1.0` |
| Configuration hash | `sha256:5340cf6874a87273383109a1c591c7f4f32b450c99ae71454927aad480b52e15` |
| Language | `en` |
| Evidence localization | `unavailable` |
| License review | `provisionally_verified` |
| User-facing execution | **not permitted** |

Package revision and adapter revision are pinned **separately**. The adapter verifies the installed distribution version and its own configuration hash against this record and fails closed on any mismatch.

## Licensing evidence

License review state: **`provisionally_verified`** — deliberately not `verified`.

### What was verified by direct inspection

The installed distribution was inspected, not just its metadata:

```text
vaderSentiment-3.3.2.dist-info/LICENSE.txt
  → verbatim MIT License text
  → Copyright (c) 2016 C.J. Hutto
  → sha256 74cfe41cdbf7f6925aeb4c18c148ec8db042540edb6739fd81069aa4e3c8b118
```

The module header of `vaderSentiment.py` directs readers to that file and requests citation of Hutto & Gilbert (2014), ICWSM-14.

### Why it is not `verified`

Two questions remain open. The repository's [candidate README](candidates/README.md) requires distinguishing source-code terms from lexicon and bundled-resource terms and from transitive obligations, so neither is a formality:

1. **Bundled resources carry no separate terms.** `vader_lexicon.txt` (434 KB of empirically derived human ratings) and `emoji_utf8_lexicon.txt` (122 KB) contain **no** embedded license or attribution notice. Whether MIT's grant over "the Software and associated documentation files" unambiguously covers that derived data is not stated by the package itself.
2. **A declared transitive obligation exists.** `requests` is a hard `Requires-Dist` and installs under its own Apache-2.0 terms — even though the analysis path never imports it (see below).

The metadata string `License: MIT License` was **not** treated as sufficient evidence for any of this. A package can declare MIT in metadata and still bundle data under different terms; that is precisely the case this review had to rule on.

Both questions must be resolved before production distribution or any selection record. Neither blocks evaluation.

## Declared domain

```text
English short-form, social-media-like text,
per the upstream project's own stated purpose.
```

No claim of universal English sentiment understanding is made or implied.

The adapter **abstains** rather than measuring when:

- declared language metadata is not `en`;
- **no** language is declared — language is never inferred from the text; or
- content exceeds the deliberate 10,000-character short-form limit.

Abstention preserves an `out-of-domain` reason and emits no measurement. It also fails closed, with no measurement, if the pinned package returns a missing key, a non-finite value, or a value outside its declared bounds.

## What the adapter preserves

Four values, each with its own key and its own declared bounds, never combined:

| Key | Bounds | What it is |
| --- | --- | --- |
| `neg` | `[0, 1]` | Negative proportion |
| `neu` | `[0, 1]` | Neutral proportion |
| `pos` | `[0, 1]` | Positive proportion |
| `compound` | `[-1, 1]` | VADER's lexicon-and-rule composite |

The complete mapping returned by the pinned package is preserved verbatim as `raw_output`. No fifth aggregate value is produced.

### `compound` is not confidence

This is the single most important boundary in this admission.

`compound` is one number in `[-1, 1]`. It looks exactly like an overall sentiment verdict or a confidence score. **It is neither.** It is a composite that VADER computes from its lexicon and rules.

CTRT therefore:

- keeps it as one preserved output with its own bounds;
- never maps it into `instrument_probability`;
- never describes it as confidence, certainty, or strength;
- never uses it to rank, summarize, gate, or recommend; and
- never combines it with `neg`, `neu`, or `pos`.

`instrument_probability.value` is permanently `None` for this candidate.

## Evidence localization limitation

VADER returns document-level scores. **It does not report which passage produced any value.**

The adapter therefore always reports:

```text
evidence_support: unavailable
evidence_spans:   (none)
```

No token-level provenance is invented. The absence is recorded as a preserved uncertainty rather than left as an empty list, so no surface can imply VADER quoted a specific passage — there is no span for one to render.

## Confidence interpretation boundary

Each dimension is set from evidence, and kept separate:

| Dimension | At admission | Why |
| --- | --- | --- |
| Calibration | `unknown` | No empirical calibration artifact has been admitted |
| Applicability | `unknown`, with reasons | Nothing has established that any item is inside the declared domain |
| Extraction quality | `clean`, referencing the exact canonical extraction identity | Inherited from the content artifact |
| Inter-instrument agreement | `single-instrument` | One participant; no metric, no value |
| Ambiguity budget | `preserved` | Limitations are listed, not resolved |
| System abstention | Used, not guessed | Abstention is a valid outcome |

There is **no scalar or aggregate confidence value** anywhere in this admission.

Applicability is never `in-domain`. That would be a claim, and no evaluation supports it.

## Offline and network boundary

The analysis path performs **no network access** and **no runtime model or lexicon download**. The lexicons ship inside the wheel.

`vaderSentiment` declares a hard `requests` dependency, but `requests` is imported only inside its interactive `__main__` translation demo, which calls an external translation API. `polarity_scores` never touches it. A test asserts this behaviorally — it patches socket connection and confirms `requests` is never imported during analysis — rather than assuming it.

## Non-claims

This admission does **not**:

- select VADER for any domain;
- add VADER to creator preflight, the local CLI, or the browser surface;
- treat comparison with the synthetic fixtures as evidence of analytical validity;
- claim calibration, accuracy, fairness, reliability, robustness, or production readiness;
- produce an overall sentiment or tone verdict;
- produce a scalar or aggregate confidence value;
- create an automatic rewrite or recommendation;
- modify the Phase 1A governance closure or the completed Phase 1A paper;
- introduce another governance recursion; or
- admit any second real candidate.

## Required work before selection or user-facing execution

The registry record sets `execution_boundary.user_facing_execution_permitted: false` and `requires_selection_record: true`. Before that can change:

1. a preregistered evaluation protocol and a declared corpus;
2. human-annotation agreement under written instructions;
3. calibration analysis, or an explicit statement that calibration remains unknown;
4. quoted-speech, negation, irony, and dialect tests;
5. subgroup and identity-term bias analysis;
6. domain-shift evaluation before any domain-valid claim;
7. resolution of both open licensing questions; and
8. a separate accepted, domain-bounded selection record.

Until every one of those exists, VADER stays where it is: eligible for evaluation, and nowhere near a creator.

## Validating both dependency states

```bash
python -m pytest tests/test_vader_candidate_admission.py -q
```

Without the extra, the adapter-behavior tests skip and the boundary tests still run — including the ones proving the synthetic path is unaffected and the dependency fails closed. With the extra installed, all tests run.

Both states must be green.
