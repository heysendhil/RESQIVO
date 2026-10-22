"""Schema and loader for the version-controlled agentic evaluation dataset."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.rag.config import REPO_ROOT

DEFAULT_DATASET_PATH = REPO_ROOT / "data" / "synthetic" / "agentic_evaluation.json"
DEFAULT_PASSAGES_PATH = REPO_ROOT / "data" / "synthetic" / "knowledge_passages.json"

Category = Literal["positive", "negative", "boundary", "adversarial"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetrievedFixture(_Strict):
    passage: str = Field(pattern=r"^SYN-\d{3}$")
    distance: float = Field(ge=0, le=2)


class _Case(_Strict):
    id: str
    category: Category
    tags: list[str] = Field(default_factory=list)
    success_criteria: str = Field(min_length=1)
    retrieved: list[RetrievedFixture] | None = None
    knowledge_base_empty: bool = False


class GroundingExpected(_Strict):
    status: Literal["answered", "insufficient_evidence"] | None = None
    reason: str | None = None
    cited_sources: list[str] = Field(default_factory=list)
    grounding_rule: str | None = None
    error: str | None = None


class GroundingCase(_Case):
    id: str = Field(pattern=r"^GRD-\d{3}$")
    question: str = Field(min_length=1, max_length=1000)
    scripted_answer: str
    expected: GroundingExpected


class DraftingExpected(_Strict):
    status: (
        Literal["insufficient_information", "draft_invalid", "draft_valid"] | None
    ) = None
    reason: str | None = None
    final_codes: list[str] | None = None
    uncorrectable_codes: list[str] | None = None
    correction_attempts: int | None = Field(default=None, ge=0, le=2)
    corrected: bool | None = None
    evidence_available: bool | None = None
    error: str | None = None


class DraftingCase(_Case):
    id: str = Field(pattern=r"^DRF-\d{3}$")
    request_overrides: dict[str, Any] = Field(default_factory=dict)
    scripted_draft: str | dict[str, Any]
    scripted_corrections: list[str | dict[str, Any]] = Field(default_factory=list)
    scripted_guidance: str | None = None
    expected: DraftingExpected


class ScriptedCall(_Strict):
    name: str
    args: dict[str, Any] | str


class ScriptedTurn(_Strict):
    tool_calls: list[ScriptedCall] = Field(default_factory=list)
    invalid_tool_calls: list[ScriptedCall] = Field(default_factory=list)
    text: str | None = None


class ToolExpected(_Strict):
    outcome: Literal["answered", "insufficient_evidence", "error"]
    reason: str | None = None
    error: str | None = None
    records: list[tuple[str, str, str | None]] | None = None
    final_valid: bool | None = None
    draft_status: str | None = None
    executed_searches: int | None = None
    bound_tools_unchanged: bool | None = None


class ToolCallingCase(_Case):
    id: str = Field(pattern=r"^TCL-\d{3}$")
    workflow: Literal["review", "draft"]
    question: str | None = None
    plan: str | None = None
    max_tool_calls: int = Field(default=4, ge=1)
    retrieval_error: bool = False
    turns: list[ScriptedTurn] = Field(min_length=1)
    scripted_corrections: list[str | dict[str, Any]] = Field(default_factory=list)
    expected: ToolExpected


class EvaluationDataset(_Strict):
    synthetic: Literal[True]
    version: int = Field(ge=1)
    notice: str
    prepared_by: str
    prepared_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    changes: str | None = None
    base_request: dict[str, Any]
    default_draft: dict[str, Any]
    review_plans: dict[str, list[dict[str, Any]]]
    grounding: list[GroundingCase]
    drafting: list[DraftingCase]
    tool_calling: list[ToolCallingCase]


class LoadedDataset(BaseModel):
    path: str
    sha256: str
    dataset: EvaluationDataset
    passages: dict[str, dict[str, Any]]


def load_dataset(
    path: Path = DEFAULT_DATASET_PATH, passages_path: Path = DEFAULT_PASSAGES_PATH
) -> LoadedDataset:
    """Load and check the dataset. Raises ValueError listing every problem."""
    raw = path.read_bytes()
    dataset = EvaluationDataset.model_validate(json.loads(raw))
    fixture = json.loads(passages_path.read_text(encoding="utf-8"))
    if fixture.get("synthetic") is not True:
        raise ValueError("Evaluation passages must be synthetic fixtures.")
    passages = {p["id"]: p for p in fixture["passages"]}

    problems = []
    cases = [*dataset.grounding, *dataset.drafting, *dataset.tool_calling]
    ids = [case.id for case in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate case IDs: {duplicates}")
    for case in cases:
        for item in case.retrieved or []:
            if item.passage not in passages:
                problems.append(f"{case.id}: unknown passage {item.passage}")
        if case.knowledge_base_empty and case.retrieved:
            problems.append(f"{case.id}: an empty knowledge base retrieves nothing")
    for case in dataset.tool_calling:
        if case.plan is not None and case.plan not in dataset.review_plans:
            problems.append(f"{case.id}: unknown plan {case.plan}")
        if case.workflow == "review" and not case.question:
            problems.append(f"{case.id}: review cases need a question")
    if problems:
        raise ValueError("Invalid evaluation dataset:\n- " + "\n- ".join(problems))
    return LoadedDataset(
        path=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
        dataset=dataset,
        passages=passages,
    )
