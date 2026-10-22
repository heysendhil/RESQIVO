from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.plan import PlanValidationRequest
from app.models.resource import Resource, ResourceType
from app.models.scenario import DisasterScenario
from app.models.shelter import Shelter
from app.qa.schemas import MAX_QUESTION_CHARS, PLANNING_NOTICE, AnswerResponse
from app.services.validation import ValidationResult

MAX_CORRECTION_ATTEMPTS = 2

# Violations that changing allocations can fix. Others (for example DOM-05,
# duplicate resource or shelter IDs) come from the input facts and are reported.
CORRECTABLE_CODES = frozenset(
    {
        "DOM-04",
        "DOM-04-UNKNOWN-RESOURCE",
        "DOM-04-DUPLICATE-ALLOCATION",
        "DOM-06-UNKNOWN-DESTINATION",
    }
)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    plan: PlanValidationRequest | None = None


class PlanReview(BaseModel):
    """Deterministic validation of the submitted plan and of any correction."""

    original_validation: ValidationResult
    final_plan: PlanValidationRequest
    final_validation: ValidationResult
    correction_attempts: int
    max_correction_attempts: int = MAX_CORRECTION_ATTEMPTS
    corrected: bool
    uncorrectable_codes: list[str]


class ReviewResponse(BaseModel):
    answer: AnswerResponse
    plan_review: PlanReview | None = None
    notice: str = PLANNING_NOTICE


# Drafting (POST /draft-plan) -------------------------------------------------

MAX_DRAFT_RESOURCES = 100
MAX_DRAFT_SHELTERS = 100
MAX_DRAFT_NEEDS = 200
MAX_DRAFT_CONSTRAINTS = 10
MAX_CONSTRAINT_CHARS = 500

DRAFT_NOTICE = (
    "This is a draft proposal for human review. No resources have been "
    "dispatched, booked or requested, and no one has been contacted. A "
    '"draft_valid" status means only that the proposal passed RESQIVO\'s '
    "deterministic validation rules; it does not mean the plan is operationally "
    "safe, optimal, or appropriate for real-world emergency response. "
    + PLANNING_NOTICE
)


class AllocationNeed(BaseModel):
    """A known requirement: a quantity of a resource type at a shelter."""

    model_config = ConfigDict(extra="forbid")

    destination_id: str = Field(min_length=1, max_length=100)
    resource_type: ResourceType
    quantity_needed: int = Field(ge=0)


class DraftPlanRequest(BaseModel):
    """A scenario and the only inventory and shelters a draft may use."""

    model_config = ConfigDict(extra="forbid")

    scenario: DisasterScenario
    resources: list[Resource] = Field(max_length=MAX_DRAFT_RESOURCES)
    shelters: list[Shelter] = Field(max_length=MAX_DRAFT_SHELTERS)
    needs: list[AllocationNeed] = Field(
        default_factory=list, max_length=MAX_DRAFT_NEEDS
    )
    constraints: list[
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True, min_length=1, max_length=MAX_CONSTRAINT_CHARS
            ),
        ]
    ] = Field(default_factory=list, max_length=MAX_DRAFT_CONSTRAINTS)

    @model_validator(mode="after")
    def _needs_reference_supplied_shelters(self) -> DraftPlanRequest:
        shelter_ids = {shelter.shelter_id for shelter in self.shelters}
        if any(need.destination_id not in shelter_ids for need in self.needs):
            raise ValueError("Every need must reference a supplied shelter_id.")
        return self


InsufficientInformationReason = Literal[
    "no_affected_population",
    "no_available_resources",
    "no_shelters",
]


class DraftPlanResponse(BaseModel):
    """The outcome of a drafting run.

    status is one of:
    - insufficient_information: no draft was produced (see reason).
    - draft_invalid: a draft exists but fails deterministic validation.
    - draft_valid: a draft exists and passes deterministic validation.

    Validity always comes from the validator, never from the model.
    """

    request_id: str
    status: Literal["insufficient_information", "draft_invalid", "draft_valid"]
    reason: InsufficientInformationReason | None = None
    input_validation: ValidationResult
    guidance: AnswerResponse | None = None
    evidence_available: bool = False
    plan_review: PlanReview | None = None
    limitations: list[str] = Field(default_factory=list)
    notice: str = DRAFT_NOTICE
