from __future__ import annotations

from media_offline_database.sources import SourceRole


def test_source_roles_are_stable() -> None:
    assert [role.value for role in SourceRole] == [
        "BACKBONE_SOURCE",
        "ID_SOURCE",
        "LOCAL_EVIDENCE",
        "RUNTIME_ONLY",
        "BLOCKED",
    ]
