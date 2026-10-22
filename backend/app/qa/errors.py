class QAError(Exception):
    """Base class for question-answering failures reported to API clients."""


class QAConfigurationError(QAError):
    """Question answering is not configured, or is configured incorrectly."""


class ModelNotConfiguredError(QAConfigurationError):
    """Live inference was requested but no API key is available."""


class RetrievalUnavailableError(QAError):
    """The knowledge base could not be searched."""


class ModelResponseError(QAError):
    """The language model failed, declined, or returned no usable answer."""


class ToolCallLimitError(ModelResponseError):
    """The model requested more tool calls, or the workflow took more steps, than
    allowed before giving a final answer."""


class ToolExecutionError(QAError):
    """An approved tool failed unexpectedly while executing a model's request."""
