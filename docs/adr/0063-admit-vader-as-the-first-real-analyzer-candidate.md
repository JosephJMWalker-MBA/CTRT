# ADR-0063: Admit VADER as the first real analyzer candidate

- **Status:** Accepted
- **Date:** 2026-08-05
- **Phase:** 1B candidate admission

## Context

Every analyzer CTRT has executed so far is a deterministic fixture that recognizes the tokens `good` and `bad`. The fixtures proved the orchestration, provenance, and presentation contracts, but they cannot test whether those contracts survive contact with a real packaged instrument whose behavior CTRT does not control.

Admitting a real candidate is the point at which several constitutional pressures become concrete at once: a third-party dependency enters the tree, a package version becomes part of measurement identity, an analyzer appears that cannot explain which words produced its output, and a numeric value appears that looks like a confidence score and is not one.

The question this ADR answers is narrow: can a real analyzer be admitted for **evaluation** without any of that leaking into a claim, a score, or a creator-facing surface?

## Decision

Admit `vaderSentiment==3.3.2` as CTRT's first real analyzer candidate, at status `eligible_for_evaluation` and no further.

VADER was chosen because it is the lowest-risk possible first real candidate:

- it is small, deterministic, and fully offline;
- it downloads nothing at runtime — the lexicons ship inside the wheel;
- it is permissively licensed;
- its declared purpose is narrow and stated plainly by its own authors; and
- its rule-and-lexicon behavior is inspectable rather than opaque.

Nothing about that list is evidence that VADER measures sentiment well. It is evidence that VADER is a safe subject for finding out.

### What is added

1. `docs/candidates/real-registry.v0.1.0.json` — a **separate** accepted registry. The frozen synthetic registry is not modified, replaced, or extended.
2. `schemas/candidate-registry.schema.json` — five **optional** candidate properties for facts the existing contract cannot express.
3. `src/ctrt/real_candidate_registry.py` — parses only those additional binding facts.
4. `src/ctrt/vader_adapter.py` — one provider-neutral `Analyzer`.
5. A `vader` optional-dependency extra in `pyproject.toml`.

`validate_candidate_eligibility` remains the **only** execution gate. This ADR introduces no second eligibility path and no new governance recursion.

## Why new schema fields were necessary

The existing candidate record could already express identity, dimensions, authorized analyzer IDs, domain and language claims, license review, revision pinning, risks, and rationale. It could not express five concrete facts a real distribution must pin:

| New optional field | Fact it records | Why the existing contract could not carry it |
| --- | --- | --- |
| `package_binding` | Distribution, version, import name, extra | `revision_policy.pinned_revision` pins the **adapter**, not the package; both must be pinned separately |
| `taxonomy` | Taxonomy ID and version | The dimension record requires a declared taxonomy; the registry had nowhere to state it |
| `configuration_hash` | Canonical hash of the complete execution configuration | Nothing bound a candidate to an exact configuration |
| `evidence_localization` | Whether outputs can be traced to spans | No field distinguished "produced no spans" from "cannot produce spans" |
| `execution_boundary` | Explicit prohibition on user-facing execution | Prose in `notes` is not checkable |

All five are optional, so every existing registry validates unchanged. Because `CandidateRegistrySnapshot` hashes the entire document, these facts are bound into the registry artifact hash without any change to the Phase 1A hashing path.

## Dimension fit

`sentiment_valence` is used because it is contract-correct, not because it was convenient:

- its `expected_output.kind` is `distribution` with required keys `positive`, `neutral`, `negative` — VADER's `pos`, `neu`, `neg` correspond exactly;
- its `evidence_requirement` is `span_preferred`, **not** required, so unavailable evidence is legitimate rather than a workaround;
- its `instrument_requirements` demand a declared taxonomy, preserved raw values, declared language and domain limits, and abstention outside supported conditions — all of which the adapter satisfies.

The dimension was not redefined to fit VADER.

## Output preservation

The adapter preserves four values, each with its own key and its own declared bounds:

```text
neg       [0, 1]
neu       [0, 1]
pos       [0, 1]
compound  [-1, 1]
```

They are never combined. No fifth aggregate value is produced. The complete mapping returned by the pinned package is preserved verbatim as `raw_output`.

`compound` is the sharpest hazard in this ADR. It is a single number in `[-1, 1]` that reads like an overall sentiment verdict or a confidence score. It is neither. It is a lexicon-and-rule composite computed by VADER, and CTRT treats it as one more preserved output with declared bounds. It is never mapped into `instrument_probability`, never described as confidence, and never used to rank, summarize, or gate anything.

## Evidence localization

VADER returns document-level scores. It does not report which passage produced any value.

The adapter therefore always emits `EvidenceSupportStatus.UNAVAILABLE` with **zero** evidence spans, and records the absence as a preserved uncertainty. No token-level provenance is invented, and no creator-facing surface can imply that VADER quoted a passage — because there is no span for one to render.

## Confidence at admission

Each confidence dimension is set from evidence, not convenience:

- **calibration** — `unknown`. No empirical calibration artifact has been admitted.
- **applicability** — `unknown` on the success path, with reasons naming the declared domain and stating that no CTRT evaluation has placed the item inside it. It is never `in-domain`, because nothing has established that.
- **extraction quality** — `clean`, referencing the content item's exact canonical extraction identity.
- **inter-instrument agreement** — `single-instrument`, one participant, no metric, no value.
- **ambiguity budget** — `preserved`, listing the known limitations.
- **system abstention** — used rather than guessing.

No scalar or aggregate confidence value exists anywhere in this PR.

## Declared domain and abstention

The declared domain is English short-form, social-media-like text, taken from the upstream project's own stated purpose. No claim of universal English sentiment understanding is made.

The adapter abstains, rather than measuring, when:

- declared language metadata is not `en`;
- **no** language is declared — language is never inferred from the text; or
- content exceeds a deliberate 10,000-character short-form limit.

Abstention carries `out-of-domain` and preserves the reason. It never fabricates a measurement.

The adapter also fails closed, with no measurement, if the pinned package ever returns a missing key, a non-finite value, or a value outside its declared bounds.

## Dependency boundary

`vaderSentiment` is an optional extra, never a core runtime dependency:

```bash
pip install "ctrt-framework[vader]"
```

The distribution is imported lazily through `importlib.import_module` inside the adapter. Nothing in `ctrt`, `ctrt.synthetic`, `ctrt.workbench`, `ctrt.creator_preflight`, `ctrt.creator_preflight_local`, or `ctrt.creator_preflight_web` imports it, and the default synthetic path runs unchanged when it is absent. When it is absent and explicitly requested, the adapter raises `VaderDependencyError` naming the exact install command.

The adapter reads the **installed** distribution version via `importlib.metadata` and fails closed if it is not `3.3.2`, and its configuration hash must match the registry record. Package revision and adapter revision are recorded separately.

The analysis path performs no network access and no runtime lexicon download. `vaderSentiment` declares a hard `requests` dependency, but `requests` is imported only inside its interactive `__main__` translation demo; `polarity_scores` never touches it. This is asserted behaviorally, not assumed.

## Licensing evidence and review boundary

License review state: **`provisionally_verified`**, deliberately not `verified`.

Verified by direct inspection of the installed distribution:

- `vaderSentiment-3.3.2.dist-info/LICENSE.txt` contains verbatim MIT License text, Copyright (c) 2016 C.J. Hutto;
- sha256 `74cfe41cdbf7f6925aeb4c18c148ec8db042540edb6739fd81069aa4e3c8b118`;
- the module header directs readers to that file.

Two questions remain open, and they are why the state is not `verified`:

1. **Bundled resources carry no separate terms.** `vader_lexicon.txt` (434 KB of empirically derived ratings) and `emoji_utf8_lexicon.txt` (122 KB) contain no embedded license or attribution notice. Whether MIT's grant over "the Software and associated documentation files" unambiguously covers that derived data is not stated by the package itself. The repository's own candidate README requires distinguishing lexicon and bundled-resource terms from source-code terms.
2. **A declared transitive obligation exists.** `requests` is a hard `Requires-Dist` and installs under its own Apache-2.0 terms, even though the analysis path never imports it.

Neither question blocks evaluation. Both must be resolved before production distribution or any selection record.

The package metadata string `License: MIT License` was **not** treated as sufficient evidence for any of this.

## Scope and non-claims

This ADR does not:

- select VADER for any domain;
- add VADER to creator preflight, the local CLI, or the browser surface;
- treat comparison against the synthetic fixtures as evidence of analytical validity;
- claim calibration, accuracy, fairness, reliability, robustness, or production readiness;
- produce an overall sentiment or tone verdict;
- produce a scalar or aggregate confidence value;
- modify the Phase 1A governance closure or the completed Phase 1A paper;
- introduce another governance recursion; or
- admit any second real candidate.

**Candidate admission authorizes evaluation. It does not establish analytical validity and does not authorize creator-facing use.**

## Required later work before selection

Before VADER may be selected for a domain or executed in any creator-facing path:

1. a preregistered evaluation protocol and a declared corpus;
2. human-annotation agreement under written instructions;
3. calibration analysis, or an explicit statement that calibration remains unknown;
4. quoted-speech, negation, irony, and dialect tests;
5. subgroup and identity-term bias analysis;
6. domain-shift evaluation before any domain-valid claim;
7. resolution of both open licensing questions; and
8. a separate accepted, domain-bounded selection record.

## Consequences

### Positive

- CTRT's pinning, evidence-localization, and confidence-separation contracts are now exercised against a real package rather than a fixture.
- The absence of evidence localization is recorded as a first-class fact instead of surfacing as an empty list.
- The dependency-free default path is preserved and behaviorally tested in both dependency states.
- A licensing review reached a conclusion the packaging metadata alone would not have supported.

### Costs

- The repository now has an optional dependency whose absence must be tested for, doubling the validation matrix.
- `compound` will keep inviting misreading as a score, in every surface that ever displays it.
- Admitting a real analyzer creates pressure to use it before evaluation exists; the `execution_boundary` field is the checkable answer to that pressure.

## Reopening criterion

Revisit only when one of the following becomes concrete:

- an admitted empirical evaluation artifact exists for this candidate;
- either open licensing question is resolved;
- upstream publishes a version beyond `3.3.2` that CTRT intends to pin;
- a second real candidate is proposed, requiring the registry to hold more than one; or
- constitutional tests identify a contract defect this admission did not anticipate.
