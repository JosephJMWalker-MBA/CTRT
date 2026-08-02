"""Taxonomy identity and comparability contracts for CTRT workbench reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaxonomyRelation(StrEnum):
    """Declared relationship between two analyzer taxonomies."""

    IDENTICAL = "identical"
    COMPATIBLE_MAPPING = "compatible-mapping"
    PARTIAL_OVERLAP = "partial-overlap"
    INCOMPATIBLE = "incompatible"
    UNASSESSED = "unassessed"


class TaxonomyDisplayMode(StrEnum):
    """Permitted comparison presentation for a taxonomy pair."""

    SIDE_BY_SIDE = "side-by-side"
    MAPPED_COMPARISON = "mapped-comparison"


@dataclass(frozen=True, slots=True)
class TaxonomyRef:
    """Versioned identity for one declared output taxonomy."""

    taxonomy_id: str
    taxonomy_version: str

    def __post_init__(self) -> None:
        if not self.taxonomy_id.strip() or not self.taxonomy_version.strip():
            raise ValueError("taxonomy identity fields must not be empty")


@dataclass(frozen=True, slots=True)
class TaxonomyComparison:
    """Versioned relationship record that prevents false taxonomy equivalence."""

    comparison_id: str
    comparison_version: str
    left: TaxonomyRef
    right: TaxonomyRef
    relation: TaxonomyRelation
    display_mode: TaxonomyDisplayMode
    score_combination_permitted: bool = False
    mapping_method_id: str | None = None
    mapping_method_version: str | None = None
    evidence_ref: str | None = None
    information_loss: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.comparison_id.strip() or not self.comparison_version.strip():
            raise ValueError("taxonomy comparison identity fields must not be empty")
        if self.score_combination_permitted:
            raise ValueError("Phase 0 taxonomy comparisons may not combine scores")
        if len(self.information_loss) != len(set(self.information_loss)):
            raise ValueError("taxonomy information_loss must not contain duplicates")
        if any(not item.strip() for item in self.information_loss):
            raise ValueError("taxonomy information_loss entries must not be empty")
        if self.evidence_ref is not None and not self.evidence_ref.strip():
            raise ValueError("taxonomy evidence_ref must be non-empty when provided")

        same_taxonomy = self.left == self.right
        if self.relation is TaxonomyRelation.IDENTICAL:
            if not same_taxonomy:
                raise ValueError("identical relation requires matching taxonomy identities")
            if self.display_mode is not TaxonomyDisplayMode.MAPPED_COMPARISON:
                raise ValueError("identical taxonomies require mapped-comparison display")
        elif same_taxonomy:
            raise ValueError("matching taxonomy identities must use identical relation")

        requires_mapping = self.relation in {
            TaxonomyRelation.COMPATIBLE_MAPPING,
            TaxonomyRelation.PARTIAL_OVERLAP,
        }
        if requires_mapping:
            if self.mapping_method_id is None or self.mapping_method_version is None:
                raise ValueError("mapped taxonomy relation requires method identity")
            if not self.mapping_method_id.strip() or not self.mapping_method_version.strip():
                raise ValueError("taxonomy mapping method fields must not be empty")
        elif self.mapping_method_id is not None or self.mapping_method_version is not None:
            raise ValueError("unmapped taxonomy relation may not name a mapping method")

        if self.relation is TaxonomyRelation.PARTIAL_OVERLAP and not self.information_loss:
            raise ValueError("partial-overlap relation requires information_loss")
        if self.relation in {
            TaxonomyRelation.PARTIAL_OVERLAP,
            TaxonomyRelation.INCOMPATIBLE,
            TaxonomyRelation.UNASSESSED,
        } and self.display_mode is not TaxonomyDisplayMode.SIDE_BY_SIDE:
            raise ValueError("non-equivalent taxonomies require side-by-side display")
