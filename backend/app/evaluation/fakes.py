"""Offline stand-ins for retrieval and the chat model. They make no network
requests and return only the dataset's scripted outputs."""

import json
import re
from typing import Any

from langchain_core.messages import AIMessage

from app.qa.prompt import SYSTEM_PROMPT
from app.rag.store import RetrievalError, RetrievedPassage
from app.workflow.correction import CORRECTION_SYSTEM_PROMPT
from app.workflow.drafting import DRAFT_SYSTEM_PROMPT

_SHOWN = re.compile(r'<retrieved_passage label="(P\d+)" source_id="([^"]+)"')
_SOURCE_REF = re.compile(r"\[(SYN-\d{3})\]")
# A well-formed label that is never provided, as a model inventing a citation to
# an unretrieved source would produce.
UNPROVIDED_LABEL = "P99"


def to_passage(fixture: dict[str, Any], distance: float) -> RetrievedPassage:
    return RetrievedPassage(
        text=fixture["text"],
        source_id=fixture["id"],
        title=fixture["title"],
        publisher=fixture["publisher"],
        url=fixture["url"],
        chunk_id=f"{fixture['id']}:0000",
        chunk_index=0,
        synthetic=True,
        distance=distance,
    )


class FixtureRetriever:
    """Returns the case's fixed passages for any query."""

    def __init__(self, passages: list[RetrievedPassage], error: Exception | None):
        self.passages = passages
        self.error = error
        self.calls = 0

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedPassage]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.passages[:k]


def retrieval_error() -> RetrievalError:
    return RetrievalError("Scripted retrieval failure.")


def cite(text: str, messages: list[Any]) -> str:
    """Replace [SYN-xxx] with the label the passage was shown under, or with a
    label that was never provided if it was not shown."""
    labels: dict[str, str] = {}
    for message in messages:
        for label, source_id in _SHOWN.findall(str(getattr(message, "content", ""))):
            labels.setdefault(source_id, label)
    return _SOURCE_REF.sub(
        lambda m: f"[{labels.get(m.group(1), UNPROVIDED_LABEL)}]", text
    )


def _as_text(reply: str | dict[str, Any]) -> str:
    return reply if isinstance(reply, str) else json.dumps(reply)


class ScriptedChatModel:
    """Serves scripted replies by prompt type. bind_tools records the tools
    offered and returns a model that serves scripted tool-calling turns."""

    def __init__(
        self,
        answer: str = "",
        draft: str | dict[str, Any] = "",
        corrections: list[str | dict[str, Any]] | None = None,
        turns: list[Any] | None = None,
    ) -> None:
        self.answer = answer
        self.draft = _as_text(draft)
        self.corrections = [
            self.draft if c == "same" else _as_text(c) for c in corrections or []
        ]
        self.turns = list(turns or [])
        self.bound_tools: list[list[str]] = []
        self.answers: list[str] = []
        self.calls = {"answer": 0, "draft": 0, "correction": 0, "tool_turn": 0}

    def bind_tools(self, tools, **kwargs):
        self.bound_tools.append([tool.name for tool in tools])
        return _BoundScriptedModel(self)

    def invoke(self, messages):
        system = messages[0].content
        if system == SYSTEM_PROMPT:
            self.calls["answer"] += 1
            self.answers.append(cite(self.answer, messages))
            return AIMessage(content=self.answers[-1])
        if system == DRAFT_SYSTEM_PROMPT:
            self.calls["draft"] += 1
            return AIMessage(content=self.draft)
        if system == CORRECTION_SYSTEM_PROMPT:
            self.calls["correction"] += 1
            reply = self.corrections.pop(0) if self.corrections else "no change"
            return AIMessage(content=reply)
        raise RuntimeError("Unexpected prompt for the scripted model.")


class _BoundScriptedModel:
    def __init__(self, model: ScriptedChatModel) -> None:
        self._model = model

    def invoke(self, messages):
        self._model.calls["tool_turn"] += 1
        if not self._model.turns:
            raise RuntimeError("The scripted model has no more turns.")
        turn = self._model.turns.pop(0)
        number = self._model.calls["tool_turn"]
        return AIMessage(
            content=cite(turn.get("text") or "", messages),
            tool_calls=[
                {"name": c["name"], "args": c["args"], "id": f"t{number}-{i}"}
                for i, c in enumerate(turn.get("tool_calls", []))
            ],
            invalid_tool_calls=[
                {
                    "name": c["name"],
                    "args": c["args"],
                    "id": f"t{number}-bad{i}",
                    "error": "Scripted parse failure.",
                }
                for i, c in enumerate(turn.get("invalid_tool_calls", []))
            ],
        )
