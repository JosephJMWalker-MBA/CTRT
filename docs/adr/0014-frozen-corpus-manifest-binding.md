# ADR-0014: Frozen corpus manifests bind exact runtime content

- **Status:** Accepted
- **Date:** 2026-08-02
- **Decision owners:** CTRT maintainers

## Context

A frozen experiment plan previously named a corpus artifact by ID, version, and hash and listed ordered content IDs. The multi-content runner enforced the ordered ID population, but it did not independently prove that the runtime text and metadata were the same content frozen into the corpus artifact.

An unchanged content ID is insufficient when text, language, source type, or extraction identity can drift. Trusting a caller-supplied hash is also insufficient because the supplied hash may no longer describe the bytes presented to analyzers.

## Decision

CTRT will use a canonical frozen corpus manifest containing an ordered list of content entries. Every entry records:

- contiguous zero-based position;
- stable content ID;
- SHA-256 hash of the exact UTF-8 text bytes;
- language;
- source type;
- extraction identity.

Before any artifact is written, the corpus-bound runner must verify:

1. the experiment plan's corpus ID, version, and hash exactly match the canonical manifest;
2. the plan's ordered content IDs exactly match the manifest;
3. runtime content IDs are neither missing, additional, duplicated, nor reordered;
4. each runtime content hash is recomputed from its actual UTF-8 text;
5. the recomputed hash matches both the supplied content hash and manifest hash;
6. language, source type, and extraction identity match the manifest;
7. candidate eligibility and the existing one-dimension execution limits still hold.

The current Workbench uses `content-item:<content_id>` as its extraction identity. This ADR does not generalize that convention. Other extraction identities require a future governed extraction-manifest contract.

After preflight succeeds, the canonical corpus manifest is persisted in the append-only store. The existing multi-content runner then executes normally. A final corpus-bound completion artifact links:

- the exact stored corpus manifest;
- the verified multi-content experiment completion;
- the ordered content identities copied from the manifest.

The linked completion is written only after the underlying experiment completes, and it is reread and hash-verified before a corpus-bound receipt is returned.

## Consequences

### Positive

- Content IDs can no longer conceal changed text.
- Caller-supplied hashes are verified rather than trusted.
- Language, source type, and extraction provenance become part of reproducibility.
- Every corpus mismatch fails before the artifact store is touched.
- The final record makes corpus provenance directly inspectable without creating an aggregate analytical result.

### Limitations

- Unicode normalization is not performed; exact UTF-8 bytes are authoritative.
- The manifest does not embed text, source documents, licensing terms, or acquisition evidence.
- Only the current `content-item:` extraction identity is executable.
- The local filesystem store still provides no remote durability, signatures, or access control.
- A persisted corpus manifest may remain if a later governed session fails; it is a valid immutable preflight artifact, not proof of experiment completion.

## Rejected alternatives

### Trust the content object's declared hash

Rejected because changed text could be paired with a stale or substituted hash.

### Bind only content IDs and hashes

Rejected because language, source type, and extraction identity materially affect interpretation and reproducibility.

### Add corpus fields directly to every session receipt

Rejected for this slice because the frozen plan already references the corpus, and a single linked completion records the experiment-level binding without duplicating the full manifest across every session.

### Treat corpus verification as an aggregate measurement

Rejected. Corpus verification is provenance and lifecycle evidence only. It does not summarize analyzer outcomes or imply content quality, accuracy, agreement, or confidence.
