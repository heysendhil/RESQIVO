from app.models.allocation import ResourceAllocation
from app.models.resource import Resource, ResourceType
from app.models.shelter import Shelter
from app.services.validation import validate_plan


def make_resource(
    resource_id: str = "resource-001",
    quantity_available: int = 100,
) -> Resource:
    return Resource(
        resource_id=resource_id,
        name="Drinking Water",
        resource_type=ResourceType.DRINKING_WATER,
        quantity_available=quantity_available,
        unit="litres",
        location="Warehouse A",
    )


def make_allocation(
    allocation_id: str = "allocation-001",
    resource_id: str = "resource-001",
    quantity_allocated: int = 50,
) -> ResourceAllocation:
    return ResourceAllocation(
        allocation_id=allocation_id,
        resource_id=resource_id,
        destination_id="shelter-001",
        quantity_allocated=quantity_allocated,
    )


def make_shelter(
    shelter_id: str = "shelter-001",
    capacity: int = 100,
    current_occupancy: int = 50,
) -> Shelter:
    return Shelter(
        shelter_id=shelter_id,
        name="Emergency Shelter",
        location="Relief Camp A",
        capacity=capacity,
        current_occupancy=current_occupancy,
    )


def test_valid_plan_has_no_violations() -> None:
    result = validate_plan(
        resources=[make_resource()],
        allocations=[make_allocation()],
        shelters=[make_shelter()],
    )

    assert result.valid is True
    assert result.violations == []


def test_plan_reports_resource_overallocation() -> None:
    result = validate_plan(
        resources=[
            make_resource(quantity_available=100),
        ],
        allocations=[
            make_allocation(quantity_allocated=120),
        ],
        shelters=[make_shelter()],
    )

    assert result.valid is False
    assert any(violation.code == "DOM-04" for violation in result.violations)


def test_plan_reports_shelter_overcapacity() -> None:
    result = validate_plan(
        resources=[make_resource()],
        allocations=[make_allocation()],
        shelters=[
            make_shelter(
                capacity=100,
                current_occupancy=120,
            ),
        ],
    )

    assert result.valid is False
    assert any(violation.code == "DOM-05" for violation in result.violations)


def test_plan_reports_multiple_violation_types() -> None:
    result = validate_plan(
        resources=[
            make_resource(quantity_available=100),
        ],
        allocations=[
            make_allocation(quantity_allocated=120),
        ],
        shelters=[
            make_shelter(
                capacity=100,
                current_occupancy=120,
            ),
        ],
    )

    violation_codes = {violation.code for violation in result.violations}

    assert result.valid is False
    assert "DOM-04" in violation_codes
    assert "DOM-05" in violation_codes


def test_empty_plan_is_valid() -> None:
    result = validate_plan(
        resources=[],
        allocations=[],
        shelters=[],
    )

    assert result.valid is True
    assert result.violations == []
