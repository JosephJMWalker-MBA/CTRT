# Phase 1B: VADER behavioral characterization

> **Behavioral characterization records what the admitted implementation does on frozen probes. It does not establish that the outputs are correct, calibrated, fair, or suitable for creator-facing use.**

This guide covers CTRT's first research-only execution of the admitted VADER candidate.

See [ADR-0064](adr/0064-record-single-candidate-behavioral-characterization-separately-from-comparison.md) for the decision record, and [ADR-0063](adr/0063-admit-vader-as-the-first-real-analyzer-candidate.md) for the admission it builds on.

## Installation and command

The optional candidate dependency must be installed explicitly:

```bash
pip install "ctrt-framework[dev,vader]"
```

Then run the research characterization:

```bash
python -m ctrt.vader_characterization --workspace .ctrt/vader-characterization
```

Write the report to a file instead of standard output:

```bash
python -m ctrt.vader_characterization --workspace .ctrt/vader-characterization --output characterization.md
```

Use a reproducible run token:

```bash
python -m ctrt.vader_characterization --run-token research-run-0001
```

Without the optional dependency the command fails clearly and does nothing else:

```text
vader characterization failed: optional candidate dependency vaderSentiment==3.3.2
is not installed; install it with `pip install "ctrt-framework[vader]"`
```

It never installs a dependency, downloads a resource, accesses the network, or opens a browser.

## What this is not

This is **not** analytical validation, candidate selection, calibration, or creator-facing use. The report is a research artifact, not a creator-preflight screen. It is produced by a command that no creator-facing surface imports.

## Characterization is not comparison

CTRT now has two experiment types. Confusing them would be the easiest way to turn this run into a claim it cannot support.

| | Inter-instrument comparison | Behavioral characterization |
| --- | --- | --- |
| Question | Do independent instruments agree about this content? | What does this one admitted implementation do on these frozen inputs? |
| Minimum instruments | Two — one is meaningless | Exactly one — a second would be fabricated |
| Subject | The content | The implementation |
| Primary evidence | Agreement, disagreement, abstention | Preserved outputs per probe |

Every inherited comparison contract requires at least two analyzers, at five independent levels. Those invariants are correct and were **not** weakened. Rather than fake a second analyzer, this work adds a separate single-candidate record whose plan carries the inverse invariant: exactly one instrument.

Specifically, this run does **not**:

- register a fake comparator;
- compare VADER against the synthetic fixtures and call that validation;
- duplicate VADER under two identities; or
- fabricate agreement.

Comparing VADER to the `good`/`bad` fixtures would establish nothing about sentiment, and presenting it as validation would be a false claim.

## Characterization is not analytical validity

Executing an implementation and recording its outputs tells you what the implementation does. It does not tell you whether what it does is right.

Analytical validity would require human-referenced data, a preregistered protocol, agreement analysis, calibration, and bias evaluation — none of which exist here. Every number in the report is an observation about software behavior on 24 sentences the CTRT project wrote.

## Probe corpus design

`docs/corpora/vader-behavioral-probes.v0.1.0.json` — frozen, 24 probes, repository-authored.

| Property | Value |
| --- | --- |
| Authorship | Written specifically for CTRT |
| External dataset | none |
| Scraped content | none |
| Network retrieval | none |
| Human ground-truth labels | **none** |

The parser refuses to load a corpus declaring any of the first four as present.

### Categories

`plainly_positive`, `plainly_negative`, `neutral`, `mixed_polarity`, `contrastive_conjunction`, `negation`, `degree_modifier`, `capitalization_emphasis`, `punctuation_emphasis`, `emoticon_emoji`, `informal_shortform`, `context_dependent_risk`, `unsupported_language`.

### No correct answers

Each probe carries a `probes` description and `not_a_ground_truth_label: true`.

A description says what the item is designed to exercise. It is **not** a claim about what the item's sentiment truly is. There is no annotation, no gold label, and no correct answer anywhere in this corpus.

### Metamorphic pairs

Several probes exist in base/variant pairs differing by exactly one documented feature — `and` versus `but`, with and without `not`, with and without a degree modifier, with and without capitalization or exclamation points. This lets an expectation be stated as a relation between the implementation's own two outputs, which needs no ground truth to evaluate.

## Behavioral expectations

Eight narrow expectations: six metamorphic, two implementation facts. Each declares a `basis` (`upstream_documented_rule` or `shipped_lexicon_contents`), a `basis_detail`, and `not_a_correctness_claim: true`.

Permitted form — a narrow, directional, documented relation:

```text
adding "extremely" before the lexicon token does not decrease compound
```

Forbidden forms, none of which appear:

```text
this text is truly positive
VADER should match human judgment
this output is accurate
this item proves sentiment understanding
```

Expectations are stored as **separate artifacts beside** the results. They are never merged into a result, and no observation carries an expectation field.

**An unsatisfied expectation means only that the observed implementation did not satisfy that exact probe.** It is not a content verdict, not an accuracy measure, and not a global candidate score.

**No overall expectation rate is computed.** A "6 of 8 passed" figure would be read as a quality score within seconds, so it does not exist.

## Execution path

```text
frozen probe corpus  (repository authored, no labels)
    ↓
raw-text source artifact
identity-extraction manifest      ← authorized method registry
extracted-content artifact
    ↓
method-bound extraction corpus  →  extraction-method eligibility
    ↓
candidate eligibility gate        ← same rules as the comparison path
    ↓
exact vaderSentiment==3.3.2 + pinned adapter + exact configuration hash
    ↓
append-only canonical artifact store
    ↓
read-time rehashing and completion verification
    ↓
deterministic Markdown research report
```

The candidate gate uses `candidate_authorization_reasons`, the same function the multi-instrument comparison path uses, so the single-candidate path cannot drift into a weaker gate. Method eligibility likewise shares `authorize_extraction_methods`.

Execution fails closed when the installed package version, the configuration hash, the registry lifecycle status, or any stored artifact hash does not match.

## What is preserved per probe

Exact content and extraction identity; candidate, package, adapter, taxonomy, and configuration identity; raw `neg`, `neu`, `pos`, `compound`; each normalized measurement with its own bounds; evidence-support unavailability; zero evidence spans; calibration status; applicability status and reasons; extraction-quality evidence reference; ambiguity and limitations; abstention when triggered; and immutable artifact references.

`compound` remains one preserved output with its own `[-1, 1]` bounds. It is not a confidence value, and no VADER number enters any confidence field.

## Report sections

1. Run and candidate identity
2. Corpus and provenance
3. Per-probe observations — exact text and the four separate outputs
4. Narrow behavioral expectations and observed outcomes
5. Abstentions and structural failures
6. Immutable artifact references
7. Interpretation boundary and non-claims

The report is rendered only after every stored artifact has been re-read and rehashed.

## Lifecycle counts are not quality

The report preserves completed, abstained, and structurally failed counts, with this note attached inline:

> Lifecycle information only. These counts describe execution outcomes and are not a pass rate, an accuracy measure, or any statement of analytical quality.

An abstention is a correct outcome, not a failure. The corpus deliberately includes an item with declared French metadata to exercise the adapter's declared-domain abstention.

## Candidate lifecycle is unchanged

```text
vader.sentiment → eligible_for_evaluation
```

Still **not** `evaluated` and **not** `selected_for_domain`.

The registry record was not edited, and it records nothing about this run. The run record is separate from the lifecycle decision by design, and the completion artifact refuses to serialize any other lifecycle status.

## Licensing boundary is unchanged

License review remains **`provisionally_verified`**. Running the package does not resolve either open question: the bundled `vader_lexicon.txt` and `emoji_utf8_lexicon.txt` still carry no separate stated terms, and `requests` is still a declared transitive dependency. Both must be resolved before production distribution or selection.

## Explicit non-claims

This run does not produce:

- an overall CTRT score;
- a mean sentiment score;
- an overall positive, negative, or neutral classification;
- a pass percentage presented as analytical quality;
- scalar or aggregate confidence;
- a candidate ranking;
- a selection recommendation; or
- any creator-facing output.

It does not establish accuracy, calibration, fairness, reliability, robustness, or production readiness, and it does not modify the Phase 1A governance closure or paper.

## Required before evaluation and selection

1. a preregistered evaluation protocol and a declared corpus;
2. human annotation under written instructions, with inter-annotator agreement;
3. calibration analysis, or an explicit statement that calibration remains unknown;
4. quoted-speech, negation, irony, dialect, and reclaimed-language tests at scale;
5. subgroup and identity-term bias analysis;
6. domain-shift evaluation before any domain-valid claim;
7. resolution of both open licensing questions; and
8. a separate accepted, domain-bounded selection record.

Until all of those exist, VADER remains eligible for evaluation and nowhere near a creator.

## Validating both dependency states

```bash
python -m pytest tests/test_vader_characterization.py -q
```

Without the optional dependency the execution tests skip and the structural tests still run — corpus freezing, provenance, label-freeness, lifecycle status, fail-closed behavior, and creator-facing disconnection. With it installed, all tests run. Both states must be green.
