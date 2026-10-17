import pytest
from pydantic import ValidationError

from app.models.allocation import ResourceAllocation


def test_valid_resource_allocation() -> None:
    allocation = ResourceAllocation(
        allocation_id="alloc-001",
        resource_id="water-001",
        destination_id="shelter-001",
        quantity_allocated=400,
    )

    assert allocation.allocation_id == "alloc-001"
    assert allocation.resource_id == "water-001"
    assert allocation.destination_id == "shelter-001"
    assert allocation.quantity_allocated == 400


def test_negative_allocation_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ResourceAllocation(
            allocation_id="alloc-002",
            resource_id="water-001",
            destination_id="shelter-001",
            quantity_allocated=-10,
        )


def test_unknown_allocation_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ResourceAllocation(
            allocation_id="alloc-003",
            resource_id="water-001",
            destination_id="shelter-001",
            quantity_allocated=100,
            unexpected_field="not allowed",
        )
