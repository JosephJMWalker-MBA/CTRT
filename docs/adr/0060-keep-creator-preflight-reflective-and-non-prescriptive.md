# ADR-0060: Keep creator preflight reflective and non-prescriptive

- Status: Accepted
- Date: 2026-08-05
- Phase: 1B
- Depends on: ADR-0059 and the merged Phase 1A constitutional checkpoint

## Context

Phase 1A established a governed synthetic evidence path. PR #57 added the first application-shell capability: a human-readable view derived only after exact stored evidence re-verifies.

The first intended human workflow is creator preflight:

```text
Draft
  -> analyze
  -> inspect evidence, disagreement, abstention, and uncertainty
  -> decide whether to publish, revise, pause, or seek feedback
```

This workflow is useful precisely because the creator retains authority. A pre-publication tool can easily become a scoring or approval system if it converts measurements into a hidden recommendation such as:

- publish;
- revise;
- safe to post;
- likely acceptable;
- high-risk content; or
- overall positive or negative tone.

Those outputs would violate the CTRT Constitution's separation between measurement and judgment. They would also falsely imply that synthetic Phase 1A fixtures have demonstrated real-world analytical validity.

Creator context introduces another boundary. A creator may describe intended meaning, audience, or concerns. That context can help organize reflection, but it is not part of the canonical evidence graph and must not be silently promoted into verified evidence.

## Decision

Creator preflight SHALL remain a deterministic, noncanonical reflection layer over the verified evidence view.

The preflight request selects one exact verified content ID and may include creator-provided:

- intended message;
- intended audience; and
- concerns.

Creator-provided context SHALL be labeled as context rather than verified evidence.

Before preflight is derived, the implementation SHALL call the existing stored-content evidence reader. Therefore, all existing requirements remain controlling:

- exact content identity and order;
- read-time rehashing;
- persisted receipt comparison;
- full experiment-bundle reconstruction;
- separate instrument results;
- preserved disagreement and abstention; and
- immutable artifact references.

The preflight SHALL provide:

1. the exact stored draft;
2. creator-provided context, clearly separated from evidence;
3. plain-language observations traceable to immutable artifacts;
4. deterministic reflection questions triggered by the preserved evidence state;
5. neutral creator-controlled actions; and
6. interpretation notices preserving the constitutional boundary.

The preflight SHALL NOT:

- calculate an overall CTRT score;
- calculate overall tone or sentiment;
- collapse confidence into one scalar;
- label content safe, unsafe, good, bad, approved, or prohibited;
- recommend publishing, revising, restricting, or suppressing;
- profile the creator or audience;
- infer creator intent from content;
- treat creator-provided context as verified evidence;
- replace or amend canonical artifacts;
- write a canonical preflight artifact; or
- claim production readiness.

## Deterministic prompt triggers

Reflection questions may be added only from explicit stored conditions.

Examples include:

- every preflight asks whether the evidence matches the creator's stated intent;
- every preflight asks what context is absent from the exact stored text;
- intended-audience context adds an audience-interpretation question;
- creator concerns add questions asking what evidence addresses each concern;
- local evidence spans add a highlighted-wording question;
- material disagreement adds a question about ambiguity, contrast, or missing context;
- agreement adds a question about whether the shared measured signal is intentional;
- instrument abstention adds a manual-inspection question;
- comparison abstention adds a question directing attention back to original results;
- nonvalidated calibration adds a question about how much weight to assign the result;
- non-in-domain applicability adds a scope question;
- non-clean extraction adds a source-inspection question;
- preserved uncertainty adds an uncertainty-priority question; and
- comparison limitations add a limitation-priority question.

These prompts do not answer themselves. They organize human attention without creating a verdict.

## Creator-controlled actions

The initial interaction presents four neutral possibilities:

1. publish as written;
2. revise and run preflight again;
3. pause without publishing; or
4. seek feedback from a person who understands the context.

CTRT does not select or rank these actions.

## Consequences

### Positive

- The first recognizable product workflow remains constitutionally aligned.
- Creators can inspect evidence without surrendering decision authority.
- Disagreement, abstention, and uncertainty become usable rather than merely stored.
- Creator context improves reflection without contaminating the evidence graph.
- The same interaction pattern can later support a user interface without changing the kernel.

### Costs

- The interaction may feel less decisive than products that emit one recommendation.
- Deterministic prompts cannot adapt conversationally beyond explicit evidence conditions.
- The synthetic analyzers remain demonstrations of workflow behavior, not useful real-world instruments.
- A creator must still exercise judgment and may seek human context the system does not possess.

## Rejected alternatives

### Emit a publish-readiness score

Rejected because no such construct has been defined or validated and because it would collapse measurement into judgment.

### Recommend revision when instruments disagree

Rejected because disagreement is evidence to inspect, not automatic proof that the draft is defective.

### Treat agreement as approval

Rejected because instrument agreement on one measured dimension does not establish accuracy, desirability, or fitness to publish.

### Persist creator context into the canonical evidence graph

Rejected for this phase because creator intent and audience are user-supplied context, not independently verified research artifacts.

### Add a language model to generate personalized advice

Rejected for this bounded slice because it would introduce an ungoverned analytical component before real-candidate admission and empirical evaluation.

## Review criterion

This decision remains satisfied only while creator preflight:

- derives from exact reverified evidence;
- keeps creator context visibly separate;
- traces observations and prompts to immutable artifacts;
- preserves original measurements, disagreement, abstention, and uncertainty;
- creates no recommendation or aggregate; and
- leaves the final action with the creator.
