# ADR-0001: Separate Measurement from Judgment

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-02

## Context

Content-analysis systems often collapse descriptive measurement, interpretation, policy judgment, and enforcement into a single output. This makes hidden values difficult to inspect and encourages users to treat probabilistic model outputs as authoritative verdicts.

## Decision

CTRT will treat measurement, interpretation, judgment, and action as distinct responsibilities.

A CTRT analysis may report defined characteristics of a content item. It may not, by default, decide whether the content should exist, whether its creator is good or bad, or what action a user or platform must take.

Interfaces and schemas must preserve this separation. Policy or filtering systems built in later phases must consume CTRT measurements as external decision inputs rather than becoming part of the canonical measurement engine.

## Consequences

- Reports require dimension-level language rather than moral verdicts.
- Future enforcement or filtering integrations require separate governance.
- The project may decline simpler labels that imply unsupported judgment.
- Explanations must avoid inferring intent or character.
- CTRT remains useful across users and institutions with different decision rules.
