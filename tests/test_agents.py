"""Tests for the base LLM agent abstraction."""

from unittest.mock import MagicMock, patch

import anthropic
import pytest

from backend.agents.base import LLMAgent, LLMResponse, TokenUsage

# --- Fixtures ---


def _make_mock_response(
    text: str = "Hello, world!",
    input_tokens: int = 10,
    output_tokens: int = 20,
    model: str = "claude-sonnet-4-20250514",
    stop_reason: str = "end_turn",
) -> MagicMock:
    """Create a mock Anthropic Messages response."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    response.model = model
    response.stop_reason = stop_reason
    return response


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock Anthropic client."""
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.create.return_value = _make_mock_response()
    return client


@pytest.fixture
def agent(mock_client: MagicMock) -> LLMAgent:
    """Create an LLMAgent with a mocked client."""
    return LLMAgent(
        system_prompt="You are a helpful legal assistant.",
        client=mock_client,
        model="claude-sonnet-4-20250514",
        temperature=0.5,
    )


# --- TokenUsage tests ---


class TestTokenUsage:
    def test_total_tokens(self) -> None:
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_default_zero(self) -> None:
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_tokens == 0


# --- LLMAgent construction tests ---


class TestLLMAgentInit:
    def test_defaults_from_settings(self, mock_client: MagicMock) -> None:
        agent = LLMAgent(system_prompt="test", client=mock_client)
        assert agent.system_prompt == "test"
        assert agent.conversation_history == []
        assert agent.cumulative_usage.total_tokens == 0

    def test_custom_params(self, mock_client: MagicMock) -> None:
        agent = LLMAgent(
            system_prompt="test",
            client=mock_client,
            model="custom-model",
            temperature=0.3,
            max_tokens=2048,
        )
        assert agent.model == "custom-model"
        assert agent.temperature == 0.3
        assert agent.max_tokens == 2048


# --- Message building tests ---


class TestBuildMessages:
    def test_simple_prompt(self, agent: LLMAgent) -> None:
        messages = agent._build_messages("Hello")
        assert messages == [{"role": "user", "content": "Hello"}]

    def test_with_conversation_history(self, agent: LLMAgent) -> None:
        history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Response"},
        ]
        messages = agent._build_messages("Second", conversation_history=history)
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "First"}
        assert messages[1] == {"role": "assistant", "content": "Response"}
        assert messages[2] == {"role": "user", "content": "Second"}

    def test_uses_internal_history(self, agent: LLMAgent) -> None:
        agent.conversation_history = [
            {"role": "user", "content": "Prev"},
            {"role": "assistant", "content": "Ans"},
        ]
        messages = agent._build_messages("New")
        assert len(messages) == 3
        assert messages[-1] == {"role": "user", "content": "New"}


# --- Call tests ---


class TestCall:
    async def test_basic_call(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        result = await agent.call("Tell me about law")

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello, world!"
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 20
        assert result.model == "claude-sonnet-4-20250514"
        assert result.stop_reason == "end_turn"

    async def test_prompt_construction(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        await agent.call("My question")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == "You are a helpful legal assistant."
        assert call_kwargs.kwargs["messages"] == [{"role": "user", "content": "My question"}]
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs.kwargs["temperature"] == 0.5

    async def test_temperature_override(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        await agent.call("Question", temperature=0.0)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["temperature"] == 0.0

    async def test_max_tokens_override(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        await agent.call("Question", max_tokens=1024)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 1024

    async def test_updates_conversation_history(
        self, agent: LLMAgent, mock_client: MagicMock
    ) -> None:
        await agent.call("Hello")

        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0] == {"role": "user", "content": "Hello"}
        assert agent.conversation_history[1] == {"role": "assistant", "content": "Hello, world!"}

    async def test_cumulative_usage_tracking(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        mock_client.messages.create.return_value = _make_mock_response(
            input_tokens=10, output_tokens=20
        )
        await agent.call("First")

        mock_client.messages.create.return_value = _make_mock_response(
            input_tokens=15, output_tokens=25
        )
        await agent.call("Second")

        assert agent.cumulative_usage.input_tokens == 25
        assert agent.cumulative_usage.output_tokens == 45
        assert agent.cumulative_usage.total_tokens == 70

    async def test_custom_history_override(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        custom_history = [
            {"role": "user", "content": "Context"},
            {"role": "assistant", "content": "Noted"},
        ]
        await agent.call("Follow up", conversation_history=custom_history)

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 3
        assert messages[0]["content"] == "Context"


# --- Retry behavior tests ---


class TestRetryBehavior:
    @patch("backend.agents.base.asyncio.sleep", return_value=None)
    async def test_retries_on_server_error(
        self, mock_sleep: MagicMock, agent: LLMAgent, mock_client: MagicMock
    ) -> None:
        """Retries on 500 server errors with exponential backoff."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.json.return_value = {"error": "server error"}
        server_error = anthropic.InternalServerError(
            message="Server error",
            response=error_response,
            body={"error": "server error"},
        )

        mock_client.messages.create.side_effect = [
            server_error,
            _make_mock_response(text="Success after retry"),
        ]

        result = await agent.call("Test")
        assert result.content == "Success after retry"
        assert mock_client.messages.create.call_count == 2
        mock_sleep.assert_called_once()

    @patch("backend.agents.base.asyncio.sleep", return_value=None)
    async def test_retries_on_rate_limit(
        self, mock_sleep: MagicMock, agent: LLMAgent, mock_client: MagicMock
    ) -> None:
        """Retries on 429 rate limit errors."""
        error_response = MagicMock()
        error_response.status_code = 429
        error_response.json.return_value = {"error": "rate limited"}
        rate_error = anthropic.RateLimitError(
            message="Rate limited",
            response=error_response,
            body={"error": "rate limited"},
        )

        mock_client.messages.create.side_effect = [
            rate_error,
            _make_mock_response(text="After rate limit"),
        ]

        result = await agent.call("Test")
        assert result.content == "After rate limit"

    async def test_no_retry_on_client_error(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        """Does not retry on 4xx client errors (except 429)."""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {"error": "bad request"}
        client_error = anthropic.BadRequestError(
            message="Bad request",
            response=error_response,
            body={"error": "bad request"},
        )

        mock_client.messages.create.side_effect = client_error

        with pytest.raises(anthropic.BadRequestError):
            await agent.call("Test")

        assert mock_client.messages.create.call_count == 1

    @patch("backend.agents.base.asyncio.sleep", return_value=None)
    async def test_exhausted_retries_raises(
        self, mock_sleep: MagicMock, agent: LLMAgent, mock_client: MagicMock
    ) -> None:
        """Raises last error after all retries are exhausted."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.json.return_value = {"error": "server error"}
        server_error = anthropic.InternalServerError(
            message="Server error",
            response=error_response,
            body={"error": "server error"},
        )

        mock_client.messages.create.side_effect = server_error

        with pytest.raises(anthropic.InternalServerError):
            await agent.call("Test")

        # Default max_retries is 3
        assert mock_client.messages.create.call_count == 3

    @patch("backend.agents.base.asyncio.sleep", return_value=None)
    async def test_retries_on_connection_error(
        self, mock_sleep: MagicMock, agent: LLMAgent, mock_client: MagicMock
    ) -> None:
        """Retries on connection errors."""
        conn_error = anthropic.APIConnectionError(request=MagicMock())

        mock_client.messages.create.side_effect = [
            conn_error,
            _make_mock_response(text="Reconnected"),
        ]

        result = await agent.call("Test")
        assert result.content == "Reconnected"


# --- Structured output tests ---


class TestCallStructured:
    async def test_parses_json_response(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        mock_client.messages.create.return_value = _make_mock_response(
            text='{"legal_basis": ["Contract Act"], "confidence": 0.85}'
        )

        schema = {
            "type": "object",
            "properties": {
                "legal_basis": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
        }

        result = await agent.call_structured("Analyze this case", output_schema=schema)
        assert result["legal_basis"] == ["Contract Act"]
        assert result["confidence"] == 0.85

    async def test_handles_markdown_fenced_json(
        self, agent: LLMAgent, mock_client: MagicMock
    ) -> None:
        mock_client.messages.create.return_value = _make_mock_response(
            text='```json\n{"key": "value"}\n```'
        )

        result = await agent.call_structured(
            "Test", output_schema={"type": "object", "properties": {"key": {"type": "string"}}}
        )
        assert result["key"] == "value"

    async def test_schema_included_in_prompt(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        mock_client.messages.create.return_value = _make_mock_response(text='{"x": 1}')

        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        await agent.call_structured("Question", output_schema=schema)

        call_kwargs = mock_client.messages.create.call_args
        sent_prompt = call_kwargs.kwargs["messages"][-1]["content"]
        assert "Respond with ONLY valid JSON" in sent_prompt
        assert '"type": "object"' in sent_prompt


# --- Reset tests ---


class TestResets:
    async def test_reset_history(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        await agent.call("Hello")
        assert len(agent.conversation_history) == 2

        agent.reset_history()
        assert agent.conversation_history == []

    async def test_reset_usage(self, agent: LLMAgent, mock_client: MagicMock) -> None:
        await agent.call("Hello")
        assert agent.cumulative_usage.total_tokens > 0

        agent.reset_usage()
        assert agent.cumulative_usage.total_tokens == 0
