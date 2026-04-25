from __future__ import annotations

from collections.abc import Iterable

from openai import OpenAI
from pydantic import BaseModel, ConfigDict


class LlmHandshakeResult(BaseModel):
    """Non-secret result for a tiny OpenAI-compatible model handshake."""

    model_config = ConfigDict(extra="forbid")

    model: str
    reachable: bool
    response: str | None = None
    error_type: str | None = None
    error_message: str | None = None


def openai_compat_handshake(
    *,
    api_key: str,
    base_url: str,
    models: Iterable[str],
) -> list[LlmHandshakeResult]:
    """Run a tiny hello-world chat completion against each configured model."""

    client = OpenAI(api_key=api_key, base_url=base_url)
    results: list[LlmHandshakeResult] = []

    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Reply with exactly: ok"},
                    {"role": "user", "content": "hello"},
                ],
                max_tokens=8,
                temperature=0,
            )
            content = response.choices[0].message.content
            results.append(
                LlmHandshakeResult(
                    model=model,
                    reachable=True,
                    response=content,
                )
            )
        except Exception as exc:
            results.append(
                LlmHandshakeResult(
                    model=model,
                    reachable=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )

    return results
