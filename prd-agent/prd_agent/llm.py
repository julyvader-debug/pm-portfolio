"""Thin wrapper around the Claude API: one streamed call, text out."""

from __future__ import annotations

import anthropic

MODEL = "claude-opus-5-5"
# Server-side fallback: if the model declines a request, the API retries it on
# a fallback model chosen by refusal category, inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """The model returned no usable answer (refusal or truncation)."""


def complete(
    client: anthropic.Anthropic,
    *,
    system: str,
    user: str,
    effort: str = "high",
    output_format: dict | None = None,
    max_tokens: int = 64000,
) -> str:
    """Run one streamed request and return the concatenated text output.

    Thinking is adaptive by default on this model; effort controls depth.
    Streaming avoids HTTP timeouts on long PRDs.
    """
    output_config: dict = {"effort": effort}
    if output_format is not None:
        output_config["format"] = output_format

    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=output_config,
        betas=[FALLBACK_BETA],
        extra_body={"fallbacks": "default"},
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        reason = getattr(details, "explanation", None) or "no explanation given"
        raise LLMError(f"The model declined this request: {reason}")
    if message.stop_reason == "max_tokens":
        raise LLMError(f"Output was cut off at max_tokens={max_tokens}. Shorten the input or raise the limit.")

    text = "".join(block.text for block in message.content if block.type == "text")
    if not text.strip():
        raise LLMError("The model returned an empty response.")
    return text
