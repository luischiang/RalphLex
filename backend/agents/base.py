"""Base LLM agent abstraction supporting Anthropic and Ollama (OpenAI-compatible) backends."""

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


def _create_default_client() -> Any:
    """Create the default LLM client based on settings."""
    if settings.llm_provider == "ollama":
        from openai import OpenAI

        return OpenAI(
            base_url=settings.ollama_base_url,
            api_key="ollama",  # Ollama doesn't need a real key
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


class LLMAgent:
    """Base agent class supporting Anthropic and Ollama backends.

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
        client: Any = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.model = model or settings.model_name
        self.temperature = temperature if temperature is not None else settings.default_temperature
        self.max_tokens = max_tokens or settings.max_tokens
        self.client = client or _create_default_client()
        self.conversation_history: list[dict[str, str]] = []
        self.cumulative_usage = TokenUsage()
        self._provider = settings.llm_provider if client is None else _detect_provider(client)

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

    async def _call_ollama(
        self,
        messages: list[dict[str, str]],
        temp: float,
        tokens: int,
    ) -> LLMResponse:
        """Call Ollama via OpenAI-compatible API."""
        # Prepend system message for OpenAI-compatible API
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages

        response = await asyncio.to_thread(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=temp,
                max_tokens=tokens,
            )
        )

        content = response.choices[0].message.content or ""
        usage_data = response.usage
        call_usage = TokenUsage(
            input_tokens=usage_data.prompt_tokens if usage_data else 0,
            output_tokens=usage_data.completion_tokens if usage_data else 0,
        )
        self.cumulative_usage.input_tokens += call_usage.input_tokens
        self.cumulative_usage.output_tokens += call_usage.output_tokens

        return LLMResponse(
            content=content,
            usage=call_usage,
            model=response.model or self.model,
            stop_reason=response.choices[0].finish_reason,
        )

    async def _call_anthropic(
        self,
        messages: list[dict[str, str]],
        temp: float,
        tokens: int,
    ) -> LLMResponse:
        """Call Anthropic Claude API."""
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

        return LLMResponse(
            content=content,
            usage=call_usage,
            model=response.model,
            stop_reason=response.stop_reason,
        )

    async def call(
        self,
        prompt: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Call the LLM with retry logic and exponential backoff.

        Args:
            prompt: The user message to send.
            conversation_history: Optional override for conversation history.
            temperature: Optional override for this call's temperature.
            max_tokens: Optional override for this call's max tokens.

        Returns:
            LLMResponse with content and usage data.
        """
        messages = self._build_messages(prompt, conversation_history)
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens or self.max_tokens

        last_error: Exception | None = None
        for attempt in range(settings.max_retries):
            try:
                if self._provider == "ollama":
                    llm_response = await self._call_ollama(messages, temp, tokens)
                else:
                    llm_response = await self._call_anthropic(messages, temp, tokens)

                # Update conversation history
                self.conversation_history.append({"role": "user", "content": prompt})
                self.conversation_history.append(
                    {"role": "assistant", "content": llm_response.content}
                )

                return llm_response

            except anthropic.APIStatusError as e:
                last_error = e
                # Don't retry on 4xx client errors (except 429 rate limit)
                if 400 <= e.status_code < 500 and e.status_code != 429:
                    raise
                delay = settings.retry_base_delay * (2**attempt)
                logger.warning(
                    "API error (attempt %d/%d): %s. Retrying in %.1fs",
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
                    "Connection error (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    settings.max_retries,
                    str(e),
                    delay,
                )
                await asyncio.sleep(delay)
            except Exception as e:
                last_error = e
                delay = settings.retry_base_delay * (2**attempt)
                logger.warning(
                    "LLM error (attempt %d/%d): %s. Retrying in %.1fs",
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
        """Call the LLM requesting JSON output matching a schema.

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

        try:
            result: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            # Try to repair truncated JSON from local models
            result = _repair_json(text)
        return result

    def reset_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []

    def reset_usage(self) -> None:
        """Reset cumulative token usage counters."""
        self.cumulative_usage = TokenUsage()


def _detect_provider(client: Any) -> str:
    """Detect LLM provider from client type."""
    if hasattr(client, "chat"):
        return "ollama"
    return "anthropic"


def _repair_json(text: str) -> dict[str, Any]:
    """Attempt to repair truncated JSON from local models.

    Tries progressively more aggressive fixes:
    1. Close unterminated strings and brackets
    2. Extract the largest valid JSON object from the text
    """
    import json
    import re

    # Try to find a JSON object start
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)

    text = text[start:]

    # Count open braces/brackets and close them
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False
    last_valid = 0

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            open_braces += 1
        elif ch == "}":
            open_braces -= 1
        elif ch == "[":
            open_brackets += 1
        elif ch == "]":
            open_brackets -= 1

        if open_braces == 0 and open_brackets == 0:
            last_valid = i
            break

    # If still unbalanced, try to close it
    if open_braces > 0 or open_brackets > 0:
        # If we're inside a string, close it
        if in_string:
            text += '"'

        # Remove any trailing incomplete key-value pair
        text = re.sub(r',\s*"[^"]*"?\s*:?\s*"?[^"]*$', "", text)

        # Close open brackets/braces
        text += "]" * open_brackets
        text += "}" * open_braces

    try:
        result: dict[str, Any] = json.loads(text)
        return result
    except json.JSONDecodeError:
        # Last resort: try to find any valid JSON object
        match = re.search(r"\{[^{}]*\}", text)
        if match:
            result = json.loads(match.group())
            return result
        raise
