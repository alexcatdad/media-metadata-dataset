from __future__ import annotations

from enum import StrEnum


class SourceRole(StrEnum):
    """How a source is allowed to participate in the dataset compiler."""

    BACKBONE_SOURCE = "BACKBONE_SOURCE"
    ID_SOURCE = "ID_SOURCE"
    LOCAL_EVIDENCE = "LOCAL_EVIDENCE"
    RUNTIME_ONLY = "RUNTIME_ONLY"
    PAID_EXPERIMENT_ONLY = "PAID_EXPERIMENT_ONLY"
    BLOCKED = "BLOCKED"
