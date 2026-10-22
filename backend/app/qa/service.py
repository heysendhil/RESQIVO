"""Grounded question answering: retrieve, generate from evidence only, cite."""

import logging
from typing import Any, Protocol

from app.limits import check_deadline
from app.observability import (
    log_event,
    record_answer,
    record_grounding_rejection,
    record_model_call,
    record_retrieval,
)
from app.qa.errors import (
    ModelResponseError,
    QAConfigurationError,
    RetrievalUnavailableError,
)
from app.qa.grounding import check_grounding
from app.qa.prompt import INSUFFICIENT_EVIDENCE_MARKER, build_messages, passage_label
from app.qa.schemas import AnswerResponse, Citation
from app.rag.embeddings import EmbeddingModelUnavailableError
from app.rag.store import KnowledgeBaseEmptyError, RetrievalError, RetrievedPassage

logger = logging.getLogger("resqivo.qa")


class Retriever(Protocol):
    def retrieve(self, query: str, k: int = 4) -> list[RetrievedPassage]: ...


class ChatModel(Protocol):
    def invoke(self, input: Any) -> Any: ...


class QuestionAnsweringService:
    """Answers questions from retrieved passages only.

    The model is called without tools, so it can only produce text. An answer is
    returned only if it passes sentence-level grounding validation (grounding.py):
    every factual sentence cites a provided passage that supports it. Citations
    are built from retrieval metadata, never from model output.
    """

    def __init__(
        self,
        retriever: Retriever,
        model: ChatModel,
        top_k: int = 4,
        max_distance: float = 1.0,
    ) -> None:
        self._retriever = retriever
        self._model = model
        self._top_k = top_k
        self._max_distance = max_distance

    def answer(self, question: str) -> AnswerResponse:
        check_deadline()
        try:
            retrieved = self._retriever.retrieve(question, k=self._top_k)
        except KnowledgeBaseEmptyError:
            record_retrieval("empty_knowledge_base")
            return _finish(
                AnswerResponse(
                    status="insufficient_evidence", reason="knowledge_base_empty"
                ),
                passages=0,
            )
        except EmbeddingModelUnavailableError as exc:
            record_retrieval("configuration_error")
            raise QAConfigurationError("The embedding model is not available.") from exc
        except RetrievalError as exc:
            record_retrieval("failure")
            raise RetrievalUnavailableError("Knowledge retrieval failed.") from exc

        record_retrieval("success")
        return self.answer_from_passages(question, retrieved)

    def answer_from_passages(
        self, question: str, retrieved: list[RetrievedPassage]
    ) -> AnswerResponse:
        """Answer from already-retrieved passages: apply the distance cut-off,
        generate, and keep the answer only if its citations are grounded."""
        passages = [p for p in retrieved if p.distance <= self._max_distance]
        if not passages:
            return _finish(
                AnswerResponse(
                    status="insufficient_evidence", reason="no_relevant_passages"
                ),
                passages=0,
            )

        text = self._generate(question, passages)

        if INSUFFICIENT_EVIDENCE_MARKER in text:
            return _finish(
                AnswerResponse(
                    status="insufficient_evidence",
                    reason="model_reported_insufficient_evidence",
                ),
                passages=len(passages),
            )

        citations = grounded_citations(text, passages)
        if citations is None:
            return _finish(
                AnswerResponse(
                    status="insufficient_evidence", reason="answer_not_grounded"
                ),
                passages=len(passages),
            )

        return _finish(
            AnswerResponse(
                status="answered",
                answer=text,
                citations=citations,
                uses_synthetic_sources=any(c.synthetic for c in citations),
            ),
            passages=len(passages),
        )

    def _generate(self, question: str, passages: list[RetrievedPassage]) -> str:
        check_deadline()
        try:
            response = self._model.invoke(build_messages(question, passages))
        except Exception as exc:
            record_model_call("answer", ok=False)
            raise ModelResponseError("The language model request failed.") from exc

        metadata = getattr(response, "response_metadata", None) or {}
        text = (getattr(response, "text", "") or "").strip()
        refused = metadata.get("stop_reason") == "refusal"
        record_model_call("answer", ok=bool(text) and not refused)
        if refused:
            raise ModelResponseError("The language model declined to answer.")
        if not text:
            raise ModelResponseError("The language model returned no answer.")
        return text


def _finish(answer: AnswerResponse, passages: int) -> AnswerResponse:
    record_answer(answer.status, answer.reason)
    log_event(
        logger,
        "qa.answer",
        status=answer.status,
        reason=answer.reason,
        passages=passages,
        citations=len(answer.citations),
    )
    return answer


def grounded_citations(
    text: str, passages: list[RetrievedPassage], log_context: str = "qa"
) -> list[Citation] | None:
    """Validate the answer sentence by sentence and map its cited labels to the
    retrieved passages, in order of first citation.

    Returns None if the answer fails grounding validation. The failing rule is
    logged with sentence counts only, never answer or passage text.
    """
    check = check_grounding(text, passages)
    if not check.passed:
        record_grounding_rejection(check.rule or "unknown")
        log_event(
            logger,
            "grounding.rejected",
            context=log_context,
            rule=check.rule,
            sentence=check.failed_sentence,
            sentences=len(check.sentences),
        )
        return None
    by_label = {passage_label(i): p for i, p in enumerate(passages)}
    cited = check.cited_labels
    return [
        Citation(
            label=label,
            source_id=by_label[label].source_id,
            title=by_label[label].title,
            publisher=by_label[label].publisher,
            url=by_label[label].url,
            chunk_id=by_label[label].chunk_id,
            synthetic=by_label[label].synthetic,
            distance=by_label[label].distance,
        )
        for label in cited
    ]
