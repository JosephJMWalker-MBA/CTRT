# Phase 1B: candidate-to-human-reference evaluation execution

> **Human-reference judgments are not ground truth. Candidate correspondence with
> them is not correctness.**
>
> **This lifecycle describes an exact candidate beside an exact verified human
> synthesis under rules frozen before pairing. It does not select the candidate or
> authorize product use.**

This guide covers CTRT's first result-bearing VADER-to-human-reference evaluation path.
It implements the protocol frozen by ADR-0072 and the lifecycle accepted by ADR-0073.

## What this capability does

The evaluator places one exact VADER result beside the complete descriptive
human-reference synthesis for the same frozen item.

It may report:

- all four VADER outputs separately;
- the candidate's preregistered directional bucket;
- the full original six-option human distribution;
- derived human unfavorable, neutral, favorable, and abstention counts;
- same-direction and different-direction counts with the denominator preserved;
- candidate abstention and failure;
- insufficient human-reference coverage;
- a three-by-three candidate-direction by human-direction contingency table;
- lifecycle counts; and
- immutable provenance references.

It does not report accuracy or choose a human answer.

## Prerequisites

Install the optional admitted candidate dependency explicitly:

```bash
pip install "ctrt-framework[dev,vader]"
```

Complete at least three independent human-reference assignments under the existing
annotation workflow. The synthesis protocol currently requires three distinct completed
assignments per item.

## Command

```bash
python -m ctrt.candidate_reference_evaluation \
  --human-workspace .ctrt/human-reference \
  --receipt assignment.corpus.human-reference-sentiment.rater-001:completion \
  --receipt assignment.corpus.human-reference-sentiment.rater-002:completion \
  --receipt assignment.corpus.human-reference-sentiment.rater-003:completion \
  --workspace .ctrt/candidate-reference-evaluation \
  --run-token pilot-run-0001
```

Write the deterministic Markdown report to a file:

```bash
python -m ctrt.candidate_reference_evaluation \
  --human-workspace .ctrt/human-reference \
  --receipt <receipt-id> \
  --receipt <receipt-id> \
  --receipt <receipt-id> \
  --workspace .ctrt/candidate-reference-evaluation \
  --run-token pilot-run-0001 \
  --output evaluation.md
```

The command creates two stores inside the run directory:

```text
.ctrt/candidate-reference-evaluation/pilot-run-0001/
├── human-synthesis-artifacts/
└── artifacts/
```

The synthesis is regenerated from the exact source collection receipts inside the run
boundary. The candidate is loaded only after the synthesis and fixture boundary pass.

## Frozen identities

The evaluator requires the exact identities preregistered in PR #69:

```text
evaluation protocol = protocol.vader-human-reference-evaluation@0.1.0
candidate registry   = registry.real-candidates@0.1.0
candidate            = vader.sentiment
analyzer             = vader.sentiment.polarity
package              = vaderSentiment==3.3.2
adapter               = ctrt-vader-adapter@0.1.0
annotation protocol  = protocol.human-reference-sentiment-valence@0.1.0
synthesis protocol   = protocol.human-reference-synthesis@0.1.0
corpus                = corpus.human-reference-sentiment@0.1.0
dimension             = sentiment_valence@0.1.0
```

A changed registry status, package version, adapter revision, configuration hash,
protocol, corpus, dimension, or item order fails before a completion is written.

## Pre-execution verification order

```text
load frozen evaluation protocol
    ↓
validate exact repository bindings
    ↓
reverify human synthesis completion and every synthesis member
    ↓
locate and rehash each source collection receipt
    ↓
reject any synthetic fixture marker in production
    ↓
load exact optional VADER dependency
    ↓
apply existing candidate-registry eligibility gate
    ↓
write frozen evaluation plan
    ↓
execute candidate
```

The production path does not load VADER before determining that the human evidence is
eligible.

## Human evidence boundary

Automated tests create annotation collections through the real collection API. Those
collections are marked:

```json
{
  "synthetic_test_fixture": true,
  "not_human_research_evidence": true
}
```

Production evaluation refuses them.

The test-only function
`run_candidate_reference_evaluation_with_test_fixtures` requires every included
collection to carry that marker and tags every resulting plan, completion, and report as
synthetic. It is not exposed by the command-line interface.

A mixed population of marked and unmarked collections is rejected.

## Candidate execution

VADER runs on every item in the exact frozen corpus order. The canonical candidate input
uses:

- item ID;
- exact text;
- exact content hash;
- declared `raw_text` source type;
- declared English language; and
- an extraction identity bound to corpus, version, item, and content hash.

For a successful result the evaluator preserves, in order:

```text
neg
neu
pos
compound
```

Each remains within its own declared bounds. The four values are never combined.

`compound` is used only to apply the upstream thresholds frozen by ADR-0072:

```text
compound <= -0.05        unfavorable
-0.05 < compound < 0.05  neutral
compound >= 0.05         favorable
```

No threshold is tuned from the human-reference results.

## Human-reference preservation

Every item retains the exact six-option distribution:

```text
strongly_unfavorable
somewhat_unfavorable
neither_clearly_favorable_nor_unfavorable
somewhat_favorable
strongly_favorable
cannot_determine_responsibly
```

Zero-count options remain present.

A derived directional view is also recorded:

```text
unfavorable = strongly_unfavorable + somewhat_unfavorable
neutral     = neither_clearly_favorable_nor_unfavorable
favorable   = somewhat_favorable + strongly_favorable
abstention  = cannot_determine_responsibly
```

The derived view does not replace the original categories. Human abstention remains
outside the directional denominator.

## Item outcomes

### Described

```text
candidate result = success
human coverage   = meets_declared_minimum_coverage
```

The item receives a candidate direction and denominator-preserving correspondence.

### Candidate abstained

```text
evaluation_status = candidate_abstained
```

The human synthesis remains visible. No candidate direction is invented.

### Candidate failed

```text
evaluation_status = candidate_failed
```

The candidate error and raw failed output remain visible. No correspondence is created.

### Insufficient reference coverage

```text
evaluation_status = insufficient_reference_coverage
```

A successful candidate output may remain visible, but it is not paired into the
contingency table.

Coverage and candidate execution are stored separately, so an item can preserve both
facts without one overwriting the other.

## Reading item correspondence

A described item may say:

```text
candidate direction: favorable
same-direction human responses: 2 of 3
human unfavorable: 0
human neutral: 1
human favorable: 2
human abstention: 1
```

This means two non-abstaining participating readers chose categories mapped to
`favorable`. It does not mean the candidate was 67% accurate. The denominator is
preserved specifically to prevent a bare score from replacing the underlying counts.

## Contingency table

The corpus-level table is:

| Candidate direction | Human unfavorable | Human neutral | Human favorable |
| --- | ---: | ---: | ---: |
| Unfavorable | count | count | count |
| Neutral | count | count | count |
| Favorable | count | count | count |

Cells count human directional responses, not correct items.

Only described items enter the table. The report separately lists:

- candidate abstentions;
- candidate failures;
- insufficient-coverage items; and
- human abstentions.

## Lifecycle information

The report includes:

- total frozen items;
- candidate successes, abstentions, and failures;
- sufficient- and insufficient-coverage items;
- items with described correspondence;
- directional human responses entering the contingency; and
- all human abstentions.

These are lifecycle counts. They are not a pass rate, accuracy, candidate quality, or
population evidence.

## Artifact graph

```text
evaluation plan
preregistered protocol artifact
candidate eligibility artifact
human-synthesis binding artifact
    ↓
48 candidate result artifacts
48 item evaluation artifacts
    ↓
directional contingency artifact
lifecycle artifact
    ↓
completion artifact written last
```

Before returning, the evaluator rereads the completion, plan, protocol, eligibility,
synthesis binding, contingency, lifecycle, every candidate result, and every item
evaluation by exact hash.

The human synthesis and every source collection receipt were independently reread and
rehashed before candidate execution.

## Report structure

1. Frozen protocol and exact identities
2. Lifecycle and coverage
3. Per-item descriptive records
4. Candidate-direction by human-direction contingency counts
5. Immutable artifact references
6. Interpretation boundary and non-claims

A fixture-derived report opens with a prominent warning:

```text
SYNTHETIC TEST FIXTURE — NOT HUMAN RESEARCH EVIDENCE
```

## What the evaluation still cannot establish

The 48-item repository-authored pilot and its participating readers cannot establish:

- population validity;
- platform representativeness;
- demographic or dialect fairness;
- large-scale irony or sarcasm robustness;
- domain generalization;
- calibration;
- production readiness; or
- suitability for either browser product door.

A result may reveal useful correspondence and divergence on this exact pilot only.

## Candidate lifecycle after completion

```text
vader.sentiment → eligible_for_evaluation
```

Unchanged.

A completed evaluation creates no selection record and does not resolve the provisional
license review. Candidate selection, rejection, or another evaluation remains a later,
separately governed decision.

## Validation expectations

The test suite covers:

- complete frozen-corpus execution;
- exact protocol and candidate bindings;
- preservation of all VADER and human outputs;
- denominator-preserving item correspondence;
- contingency construction;
- candidate abstention and failure separation;
- fixture refusal before optional candidate loading;
- synthesis-object and stored-byte tamper rejection;
- registry drift rejection;
- append-only idempotence;
- completion and member reverification;
- report fixture warnings; and
- absence of browser or creator-surface imports.

Run the complete repository checks in both dependency states:

```bash
python -m ruff check src tests
python -m mypy
python -m pytest -q
```

and then:

```bash
pip install -e ".[dev,vader]"
python -m pytest -q
```
