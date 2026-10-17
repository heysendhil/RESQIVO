from pydantic import BaseModel, ConfigDict, Field


class ResourceAllocation(BaseModel):
    """Represents a proposed allocation of a resource."""

    model_config = ConfigDict(extra="forbid")

    allocation_id: str = Field(
        min_length=1,
        max_length=100,
        description="Unique identifier for this allocation.",
    )

    resource_id: str = Field(
        min_length=1,
        max_length=100,
        description="Identifier of the resource being allocated.",
    )

    destination_id: str = Field(
        min_length=1,
        max_length=100,
        description="Identifier of the receiving shelter.",
    )

    quantity_allocated: int = Field(
        ge=0,
        description="Quantity proposed for allocation.",
    )
