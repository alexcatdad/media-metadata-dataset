from __future__ import annotations

from media_offline_database.llm import LlmHandshakeResult, resolve_z_ai_api_key


def test_llm_handshake_result_does_not_require_secret_fields() -> None:
    result = LlmHandshakeResult(model="example/free", reachable=True, response="ok")

    assert result.model_dump() == {
        "model": "example/free",
        "reachable": True,
        "response": "ok",
        "error_type": None,
        "error_message": None,
    }


def test_z_ai_api_key_resolver_accepts_already_joined_key() -> None:
    api_key = resolve_z_ai_api_key(
        api_key_id="test-id",
        api_key_secret="test-id.test-secret",
    )

    assert api_key == "test-id.test-secret"


def test_z_ai_api_key_resolver_joins_split_key_parts() -> None:
    api_key = resolve_z_ai_api_key(
        api_key_id="test-id",
        api_key_secret="test-secret",
    )

    assert api_key == "test-id.test-secret"
