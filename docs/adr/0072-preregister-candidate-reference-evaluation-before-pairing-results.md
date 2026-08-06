# ADR-0072: Preregister candidate-reference evaluation before pairing results

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision scope:** Phase 1B research protocol

## Context

CTRT now has two independently produced evidence streams for the
`sentiment_valence` dimension:

1. `vader.sentiment` has been admitted as an exact packaged candidate at
   `eligible_for_evaluation` and behaviorally characterized on frozen probes.
2. Independent human-reference judgments have been collected under written,
   blinded instructions and descriptively synthesized without majority vote,
   adjudication, or a gold answer.

The next obvious operation is to place candidate outputs beside the human
synthesis. That operation is methodologically dangerous if the comparison rules
are chosen after seeing the results. Thresholds can be adjusted, measures can be
selected, and exclusions can be introduced until the candidate appears stronger
than it did under the original plan.

The human-reference synthesis protocol therefore required a declared empirical
metric set and analysis plan before any analyzer output was placed beside the
judgments.

## Decision

CTRT will freeze a separate candidate-reference evaluation protocol before any
candidate result is paired with a human-reference synthesis.

The accepted protocol is:

```text
docs/protocols/vader-human-reference-evaluation.v0.1.0.json
```

The protocol binds:

- the exact real-candidate registry identity and version;
- candidate `vader.sentiment`;
- analyzer `vader.sentiment.polarity`;
- `vaderSentiment==3.3.2`;
- adapter revision `ctrt-vader-adapter@0.1.0`;
- the admitted configuration hash;
- the exact annotation protocol;
- the exact human-reference synthesis protocol;
- the exact 48-item repository-authored corpus;
- the shared `sentiment_valence@0.1.0` dimension; and
- the human synthesis coverage status required for item-level comparison.

This ADR accepts the protocol contract only. It does not execute VADER, load a
human collection, create an evaluation plan, create an evaluation result, or
advance a candidate lifecycle.

## Directional mapping

All four VADER outputs remain preserved. The protocol uses `compound` only for a
three-way directional alignment because the upstream project publishes typical
thresholds:

```text
compound <= -0.05       unfavorable
-0.05 < compound < 0.05 neutral
compound >= 0.05        favorable
```

These thresholds are frozen without tuning. `compound` remains a lexicon-and-rule
composite, not confidence, probability, calibration, correctness, or an overall
CTRT score.

The five non-abstaining human categories are mapped only for the bounded
three-way alignment:

```text
strongly_unfavorable + somewhat_unfavorable -> unfavorable
neither_clearly_favorable_nor_unfavorable   -> neutral
somewhat_favorable + strongly_favorable     -> favorable
cannot_determine_responsibly                -> abstention
```

The original six-option human distribution remains mandatory and controlling.
The derived directional counts never replace it. Abstention remains outside the
non-abstaining directional denominator.

## Permitted description

The later implementation may preserve and describe:

- exact candidate status and all four outputs per item;
- the candidate's frozen directional bucket;
- the full original human distribution;
- derived unfavorable, neutral, favorable, and abstention counts;
- same-direction counts with numerator and denominator preserved;
- every different-direction count separately;
- human abstention separately;
- candidate abstention and failure separately;
- insufficient human coverage separately;
- a corpus-level three-by-three contingency table of counts; and
- exact provenance and inclusion identities.

The phrase **same-direction correspondence** is deliberate. It is not accuracy.

## Prohibited conclusions

The protocol prohibits:

- accuracy, precision, recall, F1, specificity, or sensitivity;
- correlation, error averages, calibration error, or area-under-curve measures;
- significance tests or confidence intervals;
- majority, mode-as-answer, median, mean, consensus, adjudicated, gold, or
  correct human labels;
- a merged human score or aggregate candidate score;
- threshold tuning or post-result measure selection;
- candidate ranking or selection;
- candidate lifecycle advancement;
- creator-facing authorization; and
- population generalization.

These prohibitions are parsed and tested, not left as informal documentation.

## Blinding and ordering

The protocol must be frozen before candidate outputs are paired with the human
synthesis. Candidate execution must remain independent of human responses.
Human collection artifacts may never contain candidate identity or output.
Pairing may occur only by exact frozen item identity and content hash.

Every frozen corpus item must remain visible in the evaluation lifecycle.
Missing items, hash drift, or incompatible identities reject the evaluation.
Insufficient coverage, candidate abstention, and candidate failure are explicit
states rather than silent exclusions.

## Candidate lifecycle

Candidate status is `eligible_for_evaluation` before and after this protocol.
No selection record is created. Creator-facing execution remains forbidden.
The two unresolved licensing questions remain unresolved. Production readiness
is not claimed.

## Consequences

### Positive

- The analysis plan exists before outcomes can influence it.
- The exact candidate and human evidence identities are mechanically bound.
- VADER's published thresholds are used without corpus-specific tuning.
- Human disagreement and abstention remain visible.
- Candidate abstention and failure remain distinct from human outcomes.
- The future implementation has a narrow, testable contract.

### Costs

- The protocol deliberately refuses common headline metrics.
- A three-way alignment loses the intensity distinction between strong and
  somewhat favorable or unfavorable responses, so the original distribution
  must always remain present.
- The pilot corpus and participating annotators support only exact local
  description, not population inference.
- A later implementation must preserve substantial provenance and lifecycle
  detail rather than emitting one convenient number.

## Rejected alternatives

### Compare VADER with a majority human label

Rejected because the human synthesis intentionally produces no majority answer.
Creating one here would erase disagreement and contradict the collection and
synthesis protocols.

### Tune VADER thresholds on the 48 items

Rejected because tuning on the evaluation corpus would turn the same evidence
into both fitting and evaluation data.

### Use the human ordinal positions as interval numbers

Rejected because the annotation protocol explicitly declares that adjacent
positions are not equal distances and must not be averaged.

### Report accuracy against every individual human response

Rejected because human responses are independent judgments, not correct labels.
A same-direction count may be described only with its denominator and non-claim.

### Run the comparison immediately and document methods afterward

Rejected because that would permit undisclosed post-result choices.

## Follow-up boundary

The next bounded capability is an append-only evaluation runner that consumes:

1. this frozen protocol;
2. one verified human-reference synthesis receipt; and
3. independently generated exact VADER results for the same frozen items.

That runner must preserve every item and outcome, reverify every input from
canonical storage, emit descriptive records only, leave candidate status
unchanged, and remain research-only.
