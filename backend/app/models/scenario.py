from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DisasterType(StrEnum):
    FLOOD = "flood"
    EARTHQUAKE = "earthquake"
    CYCLONE = "cyclone"
    WILDFIRE = "wildfire"


class DisasterSeverity(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class DisasterScenario(BaseModel):
    """Represents a simulated natural-disaster scenario."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(
        min_length=1,
        max_length=100,
        description="Unique identifier for the scenario.",
    )

    name: str = Field(
        min_length=1,
        max_length=200,
        description="Human-readable scenario name.",
    )

    disaster_type: DisasterType

    severity: DisasterSeverity

    affected_population: int = Field(
        ge=0,
        description="Estimated number of affected people.",
    )

    location: str = Field(
        min_length=1,
        max_length=200,
        description="Simulated disaster location.",
    )

    description: str = Field(
        default="",
        max_length=2000,
        description="Additional scenario details.",
    )
