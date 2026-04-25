from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROVIDER_CONTRACT_DIR = Path("benchmarks/providers")
SECRET_LIKE_PATTERNS = (
    r"\bsk-[A-Za-z0-9_-]{20,}\b",
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
    r"\bhf_[A-Za-z0-9]{20,}\b",
    r"\bAIza[0-9A-Za-z_-]{20,}\b",
    r"\beyJ[A-Za-z0-9_-]{20,}\b",
)


def load_provider_contracts() -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for path in sorted(PROVIDER_CONTRACT_DIR.glob("*.json")):
        contract = json.loads(path.read_text(encoding="utf-8"))
        contract["_path"] = str(path)
        contracts.append(contract)
    return contracts


def test_provider_contracts_exist() -> None:
    assert load_provider_contracts()


def test_provider_contracts_have_required_safety_fields() -> None:
    required_top_level = {
        "auth",
        "base_url",
        "canonical_eligible",
        "data_use",
        "docs",
        "id",
        "limits",
        "models",
        "name",
        "status",
        "tasks",
    }

    for contract in load_provider_contracts():
        missing = required_top_level - set(contract)
        assert not missing, f"{contract['_path']} missing fields: {sorted(missing)}"
        assert contract["docs"], f"{contract['_path']} needs official docs links"
        assert contract["models"], f"{contract['_path']} needs at least one model"
        assert contract["limits"]["max_concurrency"] >= 1
        assert contract["limits"]["per_run_request_budget"] >= 1


def test_provider_models_declare_task_and_ranking_eligibility() -> None:
    for contract in load_provider_contracts():
        for model in contract["models"]:
            assert "task" in model, f"{contract['_path']} model missing task: {model['id']}"
            assert "qualified_for_ranking" in model, (
                f"{contract['_path']} model missing qualified_for_ranking: {model['id']}"
            )


def test_provider_auth_contracts_are_explicit() -> None:
    allowed_auth_schemes = {"api_key_header", "bearer"}

    for contract in load_provider_contracts():
        auth = contract["auth"]
        assert auth["scheme"] in allowed_auth_schemes
        assert auth["env"].isupper()
        assert auth["header"]
        assert auth["format"]


def test_provider_contracts_do_not_store_secret_values() -> None:
    for path in sorted(PROVIDER_CONTRACT_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_LIKE_PATTERNS:
            assert re.search(pattern, text) is None, (
                f"{path} appears to contain a secret-like value"
            )


def test_gemini_contract_uses_documented_api_key_header() -> None:
    gemini = json.loads((PROVIDER_CONTRACT_DIR / "gemini.json").read_text(encoding="utf-8"))

    assert gemini["auth"]["scheme"] == "api_key_header"
    assert gemini["auth"]["header"] == "x-goog-api-key"
    assert gemini["auth"]["env"] == "GOOGLE_AI_STUDIO_API_KEY"
    assert "JWT" in gemini["auth"]["notes"]
    assert gemini["data_use"]["free_tier_content_used_to_improve_products"] is True


def test_gemini_initial_models_are_free_of_charge_and_not_deprecated_2_0() -> None:
    gemini = json.loads((PROVIDER_CONTRACT_DIR / "gemini.json").read_text(encoding="utf-8"))

    for model in gemini["models"]:
        assert model["free_tier"] == "free_of_charge"
        assert not model["id"].startswith("gemini-2.0-")


def test_openrouter_contract_has_qualified_allowlist_and_excludes_preview_ling() -> None:
    openrouter = json.loads((PROVIDER_CONTRACT_DIR / "openrouter.json").read_text(encoding="utf-8"))
    qualified = {model["id"] for model in openrouter["models"] if model["qualified_for_ranking"] is True}
    excluded = {
        model["id"]: model
        for model in openrouter["models"]
        if model["qualified_for_ranking"] is False
    }

    assert "openai/gpt-oss-20b:free" in qualified
    assert "openai/gpt-oss-120b:free" in qualified
    assert "liquid/lfm-2.5-1.2b-instruct:free" in qualified
    assert "openrouter/free" in excluded
    assert "inclusionai/ling-2.6-flash:free" in excluded
    assert "inclusionai/ling-2.6-1t:free" in excluded
    assert excluded["inclusionai/ling-2.6-flash:free"]["stability"] == "preview_or_going_away"
