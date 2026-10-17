from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ResourceType(StrEnum):
    FOOD = "food"
    DRINKING_WATER = "drinking_water"
    MEDICAL_SUPPLIES = "medical_supplies"
    RESCUE_PERSONNEL = "rescue_personnel"
    EMERGENCY_VEHICLES = "emergency_vehicles"


class Resource(BaseModel):
    """Represents an available disaster-response resource."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1, max_length=100)

    name: str = Field(min_length=1, max_length=200)

    resource_type: ResourceType

    quantity_available: int = Field(ge=0)

    unit: str = Field(min_length=1, max_length=50)

    location: str = Field(min_length=1, max_length=200)
