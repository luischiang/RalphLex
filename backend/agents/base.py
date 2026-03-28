"""Base LLM agent abstraction wrapping the Anthropic Python SDK."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Tracks cumulative token usage across calls."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str
    usage: TokenUsage
    model: str
    stop_reason: str | None = None


class LLMAgent:
    """Base agent class that wraps the Anthropic Python SDK.

    Provides prompt construction, retry logic with exponential backoff,
    token usage tracking, and configurable temperature.
    """

    def __init__(
        self,
        system_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.model = model or settings.model_name
        self.temperature = temperature if temperature is not None else settings.default_temperature
        self.max_tokens = max_tokens or settings.max_tokens
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.conversation_history: list[dict[str, str]] = []
        self.cumulative_usage = TokenUsage()

    def _build_messages(
        self,
        prompt: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build the messages list for the API call."""
        messages: list[dict[str, str]] = []
        if conversation_history is not None:
            history = conversation_history
        else:
            history = self.conversation_history
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages

    async def call(
        self,
        prompt: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Call Claude with retry logic and exponential backoff.

        Args:
            prompt: The user message to send.
            conversation_history: Optional override for conversation history.
            temperature: Optional override for this call's temperature.
            max_tokens: Optional override for this call's max tokens.

        Returns:
            LLMResponse with content and usage data.

        Raises:
            anthropic.APIError: If all retries are exhausted.
        """
        messages = self._build_messages(prompt, conversation_history)
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens or self.max_tokens

        last_error: Exception | None = None
        for attempt in range(settings.max_retries):
            try:
                response = await asyncio.to_thread(
                    lambda: self.client.messages.create(
                        model=self.model,
                        max_tokens=tokens,
                        temperature=temp,
                        system=self.system_prompt,
                        messages=cast(list[MessageParam], messages),
                    )
                )

                call_usage = TokenUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
                self.cumulative_usage.input_tokens += call_usage.input_tokens
                self.cumulative_usage.output_tokens += call_usage.output_tokens

                content = ""
                if response.content:
                    first_block = response.content[0]
                    if hasattr(first_block, "text"):
                        content = first_block.text  # type: ignore[union-attr]

                # Update conversation history
                self.conversation_history.append({"role": "user", "content": prompt})
                self.conversation_history.append({"role": "assistant", "content": content})

                return LLMResponse(
                    content=content,
                    usage=call_usage,
                    model=response.model,
                    stop_reason=response.stop_reason,
                )

            except anthropic.APIStatusError as e:
                last_error = e
                # Don't retry on 4xx client errors (except 429 rate limit)
                if 400 <= e.status_code < 500 and e.status_code != 429:
                    raise
                delay = settings.retry_base_delay * (2**attempt)
                logger.warning(
                    "Anthropic API error (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    settings.max_retries,
                    str(e),
                    delay,
                )
                await asyncio.sleep(delay)
            except anthropic.APIConnectionError as e:
                last_error = e
                delay = settings.retry_base_delay * (2**attempt)
                logger.warning(
                    "Anthropic connection error (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    settings.max_retries,
                    str(e),
                    delay,
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        raise last_error  # type: ignore[misc]

    async def call_structured(
        self,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Call Claude requesting JSON output matching a schema.

        Wraps the prompt with instructions to return JSON conforming to the
        provided schema, then parses the response.

        Args:
            prompt: The user message.
            output_schema: A JSON schema dict describing expected output.
            conversation_history: Optional override for conversation history.
            temperature: Optional override for temperature.

        Returns:
            Parsed JSON dict from the response.
        """
        import json

        schema_str = json.dumps(output_schema, indent=2)
        structured_prompt = (
            f"{prompt}\n\n"
            f"Respond with ONLY valid JSON matching this schema:\n"
            f"```json\n{schema_str}\n```\n"
            f"Do not include any text outside the JSON object."
        )

        response = await self.call(
            structured_prompt,
            conversation_history=conversation_history,
            temperature=temperature,
        )

        # Extract JSON from response, handling potential markdown fencing
        text = response.content.strip()
        if text.startswith("```"):
            # Remove markdown code fences
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [line for line in lines[1:] if line.strip() != "```"]
            text = "\n".join(lines)

        result: dict[str, Any] = json.loads(text)
        return result

    def reset_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []

    def reset_usage(self) -> None:
        """Reset cumulative token usage counters."""
        self.cumulative_usage = TokenUsage()
