from pydantic import BaseModel, ConfigDict, Field


class Shelter(BaseModel):
    """Represents an emergency shelter and its occupancy."""

    model_config = ConfigDict(extra="forbid")

    shelter_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    capacity: int = Field(ge=0)
    current_occupancy: int = Field(ge=0)
