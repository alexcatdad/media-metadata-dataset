from __future__ import annotations

from media_offline_database.llm import LlmHandshakeResult


def test_llm_handshake_result_does_not_require_secret_fields() -> None:
    result = LlmHandshakeResult(model="example/free", reachable=True, response="ok")

    assert result.model_dump() == {
        "model": "example/free",
        "reachable": True,
        "response": "ok",
        "error_type": None,
        "error_message": None,
    }
