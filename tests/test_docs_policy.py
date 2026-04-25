from __future__ import annotations

import re
from pathlib import Path

from media_offline_database.sources import SourceRole


def test_env_example_contains_keyless_ci_budget_knobs() -> None:
    env_text = Path(".env.example").read_text(encoding="utf-8")

    required_keys = {
        "CLOUDFLARE_EMBEDDING_DAILY_NEURON_BUDGET",
        "EMBEDDING_BACKEND",
        "EMBEDDING_DAILY_TOKEN_BUDGET",
        "OPENAI_COMPAT_DAILY_REQUEST_BUDGET",
        "OPENAI_COMPAT_DEFAULT_MODEL",
        "OPENAI_COMPAT_FALLBACK_MODELS",
        "OPENROUTER_EMBEDDING_REQUESTS_PER_DAY",
    }

    for key in required_keys:
        assert f"{key}=" in env_text


def test_env_example_does_not_contain_real_looking_secrets() -> None:
    env_text = Path(".env.example").read_text(encoding="utf-8")
    secret_patterns = [
        r"gh[pousr]_[A-Za-z0-9_]{20,}",
        r"hf_[A-Za-z0-9]{20,}",
        r"sk-[A-Za-z0-9]{20,}",
        r"eyJ[A-Za-z0-9_-]{20,}",
    ]

    for pattern in secret_patterns:
        assert re.search(pattern, env_text) is None


def test_readme_links_point_to_existing_repo_files() -> None:
    readme_text = Path("README.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", readme_text)

    for link in links:
        if "://" in link:
            continue

        assert Path(link).exists(), f"README link points to missing file: {link}"


def test_source_policy_roles_match_source_role_enum() -> None:
    policy_text = Path("docs/source-admissibility-and-rate-limits.md").read_text(encoding="utf-8")
    documented_roles = set(re.findall(r"`([A-Z_]+)`", policy_text))
    enum_roles = {role.value for role in SourceRole}

    assert enum_roles <= documented_roles
    assert documented_roles <= enum_roles | {"ETag", "Last-Modified", "Retry-After"}


def test_backbone_sources_have_evidence_links() -> None:
    policy_lines = Path("docs/source-admissibility-and-rate-limits.md").read_text(
        encoding="utf-8"
    ).splitlines()

    backbone_rows = [line for line in policy_lines if "| `BACKBONE_SOURCE` |" in line]

    assert backbone_rows
    for row in backbone_rows:
        assert "http" in row
