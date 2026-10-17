import pytest
from pydantic import ValidationError

from app.models.resource import Resource, ResourceType


def test_valid_resource() -> None:
    resource = Resource(
        resource_id="water-001",
        name="Drinking Water",
        resource_type=ResourceType.DRINKING_WATER,
        quantity_available=5000,
        unit="litres",
        location="Warehouse A",
    )

    assert resource.quantity_available == 5000
    assert resource.resource_type == ResourceType.DRINKING_WATER


def test_negative_resource_quantity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Resource(
            resource_id="water-002",
            name="Drinking Water",
            resource_type=ResourceType.DRINKING_WATER,
            quantity_available=-100,
            unit="litres",
            location="Warehouse A",
        )


def test_unknown_resource_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Resource(
            resource_id="water-003",
            name="Drinking Water",
            resource_type=ResourceType.DRINKING_WATER,
            quantity_available=100,
            unit="litres",
            location="Warehouse A",
            unexpected_field="not allowed",
        )
