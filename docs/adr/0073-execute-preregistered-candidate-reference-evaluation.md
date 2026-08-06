# ADR-0073: Execute the preregistered candidate-to-human-reference evaluation descriptively

- **Status:** Accepted
- **Date:** 2026-08-06
- **Builds on:** ADR-0063, ADR-0064, ADR-0065, ADR-0066, ADR-0072

## Context

ADR-0072 froze the exact VADER-to-human-reference evaluation protocol before any
candidate output was paired with human-reference synthesis. The repository now has
four separately governed ingredients:

1. an admitted VADER candidate at `eligible_for_evaluation`;
2. a frozen 48-item human-reference corpus;
3. blinded, append-only human-reference collection and descriptive synthesis; and
4. a preregistered directional mapping and permitted-measure set.

The missing operation is the result-bearing lifecycle that binds those ingredients
without changing their meaning.

The most dangerous implementation would be a convenience script that reads a table of
human responses, runs VADER, and prints an "accuracy" percentage. That would violate
several decisions already accepted by the repository:

- humans are references, not infallible ground truth;
- the original six-option distribution must remain visible;
- human abstention is a response category, not missing data;
- candidate abstention and failure are distinct from human disagreement;
- VADER's `compound` output is not confidence;
- the upstream `-0.05` and `0.05` thresholds may not be tuned after seeing results;
- a completed evaluation may not select the candidate or authorize product use; and
- every controlling input and derived record must remain append-only and reverified.

The evaluation must also distinguish production evidence from automated test fixtures.
The human-reference synthesis module already marks fixture collections at their source
stores and refuses them in its production entry point. A later evaluation must not lose
that boundary merely because a fixture-derived synthesis receipt has the same Python
type as a real one.

## Decision

Add a separate, research-only evaluation lifecycle in
`ctrt.candidate_reference_evaluation`.

The lifecycle loads and validates the frozen ADR-0072 protocol before loading the
optional candidate dependency or executing the candidate. It then:

1. validates the exact repository bindings named by the frozen protocol;
2. reverifies the supplied human-reference synthesis completion and every referenced
   synthesis artifact;
3. locates each source collection receipt and checks its fixture marker;
4. refuses fixture-marked collections in the production entry point;
5. loads the pinned VADER adapter only after the human-evidence boundary passes;
6. applies the existing candidate-registry eligibility rules without creating a
   second eligibility standard;
7. executes the exact candidate on every frozen corpus item in frozen order;
8. preserves all four VADER outputs separately for successful results;
9. derives a candidate direction only through the preregistered thresholds;
10. preserves the full six-option human distribution and a separate four-count
    directional view;
11. creates item-level denominator-preserving correspondence only when candidate
    execution succeeded and human coverage meets the declared minimum;
12. keeps candidate abstention, candidate failure, insufficient human coverage, and
    human abstention distinct;
13. creates the permitted three-by-three candidate-direction by human-direction
    contingency counts;
14. persists the plan, protocol, eligibility, source-synthesis binding, candidate
    results, item evaluations, contingency counts, lifecycle record, and completion;
15. rereads and rehashes every evaluation artifact before returning a verified
    receipt; and
16. renders a deterministic Markdown research report from the verified records.

## Production and fixture entry points

The public production entry point is:

```python
run_candidate_reference_evaluation(request, synthesis=receipt)
```

It refuses any source collection carrying the existing synthetic-fixture marker. This
check happens before `vaderSentiment` is loaded.

The explicit test-only entry point is:

```python
run_candidate_reference_evaluation_with_test_fixtures(
    request,
    synthesis=fixture_receipt,
    adapter=fixture_adapter,
)
```

It requires every source collection to carry the fixture marker. The resulting plan,
completion, and report carry:

```text
synthetic_test_fixture = true
```

and the fixed non-claim:

> This evaluation used synthetic test-fixture annotations. It is not human research
> evidence and must never be reported as an empirical human result.

A mixed real/fixture input population is rejected by both entry points.

## Frozen plan

Every run creates a `CandidateReferenceEvaluationPlan` before candidate execution. It
binds:

- evaluation contract and record type;
- preregistered protocol identity, version, and hash;
- candidate registry identity, version, and hash;
- candidate, analyzer, adapter, and configuration identity;
- annotation and synthesis protocol identities;
- exact synthesis completion reference;
- corpus identity, version, hash, and ordered item IDs;
- dimension identity and version;
- fixture state; and
- exact non-claims.

The plan is an execution commitment. It is not a mutable settings object.

## Candidate execution

The evaluation uses the same candidate authorization function used by the workbench and
VADER characterization path. It additionally verifies the real-candidate package and
configuration binding frozen by ADR-0072.

The production path requires the exact admitted package and adapter:

```text
candidate       = vader.sentiment
analyzer        = vader.sentiment.polarity
package         = vaderSentiment==3.3.2
adapter         = ctrt-vader-adapter@0.1.0
candidate state = eligible_for_evaluation
```

The lifecycle does not change the candidate registry. Candidate execution does not
resolve the provisional license review.

Every frozen corpus item is executed. An item is never silently excluded because its
human-reference synthesis is ambiguous or because the candidate abstains.

## Item-level records

Each `CandidateReferenceItemEvaluation` preserves:

- exact frozen position, item ID, text, and content hash;
- exact human coverage status;
- all six original human response counts, including zero counts;
- derived unfavorable, neutral, favorable, and abstention counts;
- candidate result status and raw output;
- all four bounded VADER outputs when execution succeeds;
- the preregistered candidate bucket, when available;
- denominator-preserving correspondence, when permitted;
- explicit exclusion reasons otherwise;
- immutable candidate-result reference; and
- immutable human-synthesis item reference.

A successful candidate result with sufficient human coverage produces:

```text
evaluation_status = described
```

A candidate abstention produces:

```text
evaluation_status = candidate_abstained
```

A candidate structural failure produces:

```text
evaluation_status = candidate_failed
```

A successful candidate result without the required human coverage produces:

```text
evaluation_status = insufficient_reference_coverage
```

Human coverage remains a separate field in every case, so one condition cannot erase
another.

## Correspondence is not accuracy

For a described item, the record carries:

- candidate directional bucket;
- same-direction human count;
- unfavorable human count;
- neutral human count;
- favorable human count;
- complete non-abstaining denominator; and
- human abstention count outside that denominator.

No rate field exists. No human response is selected as the correct answer. A
same-direction count describes how many participating readers chose a category mapped
to the candidate's direction. It does not establish that the candidate or the readers
were correct.

## Corpus-level contingency

The only cross-item directional summary is the preregistered three-by-three contingency
of candidate direction by human direction.

Each cell counts human responses on items eligible for correspondence. The table does
not count "correct items," because the protocol defines no correct human label.

The contingency record preserves its full denominator. Human abstentions, candidate
abstentions, candidate failures, and insufficient-coverage items remain outside the
three-by-three table and visible in their own lifecycle counts.

## Lifecycle summary

The lifecycle record separately preserves:

- total frozen items;
- candidate successes;
- candidate abstentions;
- candidate failures;
- sufficient-coverage items;
- insufficient-coverage items;
- items with described correspondence;
- human directional responses entering the contingency; and
- all human abstentions.

These are operational counts, not candidate-quality measures.

## Artifact graph

```text
frozen evaluation protocol
verified human-reference synthesis
accepted real-candidate registry
        ↓
evaluation plan                         written before candidate execution
protocol artifact
candidate eligibility artifact
human-synthesis binding artifact
        ↓
exact candidate result                  one per frozen item
item descriptive evaluation             one per frozen item
        ↓
directional contingency
lifecycle summary
        ↓
evaluation completion                   written last
        ↓
read-time rehashing of every artifact
        ↓
verified evaluation receipt
        ↓
deterministic Markdown report
```

The Markdown report is derived presentation. Canonical artifacts remain controlling.

## CLI

The production command is:

```bash
python -m ctrt.candidate_reference_evaluation \
  --human-workspace .ctrt/human-reference \
  --receipt <completed-assignment-1> \
  --receipt <completed-assignment-2> \
  --receipt <completed-assignment-3> \
  --run-token pilot-run-0001
```

The command first creates a fresh verified synthesis inside the declared evaluation run
directory and then executes the evaluation. It exposes no fixture override.

## Explicit non-claims

A completed evaluation does not establish:

- ground truth;
- correctness or accuracy;
- precision, recall, F1, specificity, or sensitivity;
- correlation, calibration, significance, or confidence intervals;
- a majority, mode, median, mean, or adjudicated human answer;
- a merged human score;
- an aggregate candidate score;
- threshold validity for this corpus;
- population validity;
- domain generalization;
- subgroup fairness;
- candidate selection;
- production readiness;
- creator-facing or reader-facing authorization;
- moderation or enforcement authority; or
- an overall CTRT score.

## Rejected alternatives

### Treat the human mode as the correct label

Rejected because it replaces preserved disagreement with a response no individual may
have asserted and converts references into ground truth.

### Compute an accuracy percentage

Rejected because the frozen protocol explicitly prohibits accuracy and provides no
gold answer against which it could be computed.

### Tune the VADER thresholds on the pilot corpus

Rejected because the thresholds were preregistered before pairing. Post-result tuning
would change the question after observing the answer.

### Drop abstentions and low-coverage items

Rejected because abstention and coverage are evidence about the limits of the task.
Silent exclusion would bias the visible result and break the frozen corpus population.

### Let fixtures pass through the production entry point

Rejected because fixture-generated annotations could be mistaken for empirical human
results once they reached an otherwise valid synthesis receipt.

### Advance the candidate lifecycle automatically after completion

Rejected because evaluation evidence and governance authority are separate. A later
selection decision requires its own accepted record and domain-bounded rationale.

## Consequences

### Positive

- The first candidate-reference result is constrained by rules frozen before pairing.
- Human disagreement and abstention remain inspectable.
- Candidate failure and abstention cannot be hidden inside an aggregate.
- Test coverage can exercise the complete lifecycle without fabricating a human study.
- Production execution structurally refuses those same fixtures.
- The evaluation can be repeated and independently inspected from append-only records.

### Costs

- The report is longer than a conventional benchmark table.
- The pilot produces descriptive counts rather than a familiar quality score.
- Real empirical output still requires independent human participants.
- Candidate selection remains a separate later task.

## Follow-up boundary

After this lifecycle is merged, the next empirical step is not another protocol wrapper.
It is to collect genuine independent human-reference assignments, run the accepted
synthesis, execute this frozen evaluation, and inspect the resulting descriptive record.

Any decision to change VADER's lifecycle status or connect a real candidate to a product
door must be made in a separate ADR and selection artifact after the evidence exists.
