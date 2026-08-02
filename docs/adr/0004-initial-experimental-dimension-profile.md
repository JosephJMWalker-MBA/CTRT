# ADR-0004: Initial Experimental Dimension Profile

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-02

## Context

The original project brief treated sentiment, emotion, emotional intensity, toxicity, tone, and an overall rating as if they were equally ready for implementation. The ontology now distinguishes named concepts from operationally eligible dimensions.

Phase 0 needs a bounded answer to three questions before model selection begins:

1. What does CTRT mean by tone?
2. Which dimensions may appear in the first experimental report?
3. Is emotional intensity ready to be scored?

## Decision

### Tone

Tone is not accepted as a direct measurement dimension in Phase 0. It is a user-facing profile composed of separately identified measurements. CTRT must not equate tone with sentiment or produce a canonical scalar tone score.

### Eligible experimental dimensions

The first experimental CTRT profile may contain:

- `sentiment_valence`;
- `emotion_profile` under a declared taxonomy;
- `toxicity_indicators` at category level under a declared taxonomy.

Eligibility means that candidate instruments may later be compared under the research protocol. It does not mean that any model has been selected, evaluated, or validated.

### Emotional intensity

`emotional_intensity` is ineligible for the first experimental report. CTRT must first decide whether intensity is:

- measured independently;
- derived from emotion outputs;
- or represented as a multi-feature activation profile.

No analyzer output may be labeled canonical emotional intensity until a revised eligibility record is accepted.

### Overall rating

No overall CTRT rating is defined. Eligible dimensions may appear together as a transparent profile, but none may contribute to a universal aggregate during Phase 0.

## Rationale

Sentiment, emotion, and toxicity each have a bounded provisional claim and an output structure that can be tested without asserting author intent, audience effect, truth, morality, policy violation, or harm.

Emotional intensity remains vulnerable to construct collapse: a score could simply restate negativity, maximum emotion probability, urgency, hostility, or stylistic emphasis. Deferring it prevents false precision.

Treating tone as a profile preserves useful ordinary language while keeping the canonical record composed of independently inspectable measurements.

## Consequences

- Model evaluation may begin later only for the three eligible dimensions.
- Candidate instruments must satisfy the applicable dimension-eligibility record.
- Reports must preserve component distributions, category outputs, evidence, provenance, uncertainty, and disagreement.
- User interfaces may use the heading “Tone profile” but must not imply a validated scalar tone construct.
- Emotional-intensity experiments, if conducted, remain non-canonical research until eligibility changes.
- An overall rating requires a new ADR defining its purpose, evidence, and validation burden.

## Rejected alternatives

### Treat sentiment as tone

Rejected because valence does not capture emotion composition, hostility, certainty, urgency, humor, empathy, or rhetorical posture.

### Include intensity because existing models output confidence values

Rejected because class probability is not emotional intensity.

### Include every proposed dimension and refine later

Rejected because early interface and schema choices would create de facto legitimacy before construct validity is established.

### Create a provisional overall rating immediately

Rejected because no defined user decision or validated aggregation purpose currently justifies collapsing the profile.

## Revisit conditions

This decision may be revised when:

- a dimension's eligibility record changes through documented evidence;
- the benchmark protocol demonstrates reliable measurement in a bounded domain;
- a clear first-user decision requires an additional construct;
- or a validated aggregation method shows material value beyond the transparent profile.
