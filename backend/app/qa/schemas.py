from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_QUESTION_CHARS = 1000

PLANNING_NOTICE = (
    "RESQIVO answers support simulated planning and education only. They do not "
    "replace emergency services, public authorities, or official instructions."
)


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class Citation(BaseModel):
    """Attribution copied from retrieval metadata, never from model output."""

    label: str
    source_id: str
    title: str
    publisher: str
    url: str
    chunk_id: str
    synthetic: bool
    distance: float


InsufficientReason = Literal[
    "knowledge_base_empty",
    "no_relevant_passages",
    "model_reported_insufficient_evidence",
    "answer_not_grounded",
]


class AnswerResponse(BaseModel):
    status: Literal["answered", "insufficient_evidence"]
    reason: InsufficientReason | None = None
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    uses_synthetic_sources: bool = False
    notice: str = PLANNING_NOTICE
