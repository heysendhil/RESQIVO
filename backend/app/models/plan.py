from pydantic import BaseModel, ConfigDict

from app.models.allocation import ResourceAllocation
from app.models.resource import Resource
from app.models.shelter import Shelter


class PlanValidationRequest(BaseModel):
    """Groups the inputs of a resource-allocation plan for validation."""

    model_config = ConfigDict(extra="forbid")

    resources: list[Resource]
    allocations: list[ResourceAllocation]
    shelters: list[Shelter]
