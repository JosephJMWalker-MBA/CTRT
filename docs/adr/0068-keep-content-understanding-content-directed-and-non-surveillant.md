# ADR-0068: Keep content understanding content-directed and non-surveillant

- Status: accepted for the bounded Phase 1B branch
- Date: 2026-08-06
- Decision owners: CTRT project

## Context

Phase 1B already provides a creator-controlled **Check before I publish** reflection.
A second original product door is needed for a reader, parent, educator, or other person
who explicitly submits one piece of content and asks for help understanding it.

That request creates a serious boundary risk. A content-understanding tool can easily turn
into ambient monitoring, person-directed profiling, reductive danger labels, or automated
restriction. It can also imply that verified evidence settles the content's meaning.

The existing evidence reader already provides the correct trust boundary. It reconstructs
one exact stored content item only after re-verifying canonical text, session receipts,
experiment bundles, result identities, extraction identities, comparison order, and every
controlling artifact hash.

## Decision

Add one derived, noncanonical content-understanding reflection over
`VerifiedStoredContentExperimentReceipt` and `FileSystemArtifactStore`.

The workflow is content-directed:

```text
one explicitly submitted content item
    ↓
exact verified evidence reconstruction
    ↓
reader-provided purpose, context, and questions kept outside evidence
    ↓
plain-language observations and inspection questions
    ↓
reader-controlled source review and discussion
```

The layer does not execute analyzers, persist a new canonical artifact, monitor anyone,
or infer a viewer profile. It calls the existing stored evidence reader before deriving
any sentence.

## Reader context

The reader may provide:

- a purpose for inspecting the content;
- optional known context; and
- optional explicit questions.

These values are labeled as reader-provided context, not verified evidence. They do not
amend the canonical graph and are not used to infer identity, age, relationship, risk,
or intent.

## Preserved evidence

The reflection preserves:

- exact submitted text;
- lifecycle verification separate from analytical correctness;
- every instrument result separately;
- normalized measurements and declared bounds;
- exact evidence excerpts when available;
- analyzer abstention and failure;
- comparison agreement or disagreement;
- comparison abstention;
- calibration, applicability, extraction quality, and ambiguity separately;
- limitations; and
- immutable artifact references.

Agreement is not approval. Disagreement is not a warning label. Abstention is not proof
that no meaningful signal exists.

## Inspection prompts

Prompts are deterministic questions triggered by explicit evidence conditions. They ask
about:

- source, date, speaker, audience, and surrounding context;
- the reader's stated purpose and questions;
- highlighted excerpts in full context;
- agreement, disagreement, or abstention;
- calibration, applicability, extraction quality, and preserved uncertainty;
- limitations; and
- open-ended discussion without presuming what the content meant to another person.

Prompts do not answer themselves.

## Explicit prohibitions

This capability does not create:

- an overall CTRT score;
- an overall meaning, tone, or sentiment verdict;
- a safe/unsafe or harmful/harmless label;
- a recommendation to block, restrict, suppress, punish, or report;
- a viewer, child, parent, household, or audience profile;
- inferred intent or emotional state;
- ambient or hidden monitoring;
- automatic enforcement;
- a real analyzer or extractor;
- creator-facing VADER execution;
- a canonical content-understanding artifact;
- a production-readiness claim; or
- another governance layer.

## Consequences

CTRT gains a second recognizable application-shell workflow while retaining the same
constitutional kernel and evidence boundary as creator preflight.

The initial implementation remains a structured reflection over existing verified
synthetic evidence. A later local interface may collect one explicitly submitted content
item, but it must reuse this contract and the authorized extraction-backed execution path
rather than creating surveillance or a second analysis pipeline.

## Verification

Tests must prove:

- disagreement, agreement, and no-signal abstention remain distinct;
- exact per-instrument evidence remains visible;
- reader context remains outside verified evidence;
- unknown content identities fail without guessing;
- receipt drift and stored-byte tampering fail before reflection;
- no person-profile or restriction fields enter the view; and
- the public module surface remains bounded.
