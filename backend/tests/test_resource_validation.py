from app.models.allocation import ResourceAllocation
from app.models.resource import Resource, ResourceType
from app.services.validation import validate_resource_allocations


def make_resource(
    resource_id: str = "water-001",
    quantity_available: int = 1000,
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
    allocation_id: str,
    quantity_allocated: int,
    resource_id: str = "water-001",
) -> ResourceAllocation:
    return ResourceAllocation(
        allocation_id=allocation_id,
        resource_id=resource_id,
        destination_id="shelter-001",
        quantity_allocated=quantity_allocated,
    )


def test_allocation_within_available_stock_is_valid() -> None:
    result = validate_resource_allocations(
        resources=[make_resource()],
        allocations=[make_allocation("alloc-001", 800)],
    )

    assert result.valid is True
    assert result.violations == []


def test_allocation_equal_to_available_stock_is_valid() -> None:
    result = validate_resource_allocations(
        resources=[make_resource()],
        allocations=[make_allocation("alloc-002", 1000)],
    )

    assert result.valid is True
    assert result.violations == []


def test_allocation_exceeding_stock_reports_dom_04() -> None:
    result = validate_resource_allocations(
        resources=[make_resource()],
        allocations=[make_allocation("alloc-003", 1100)],
    )

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-04"
    assert violation.entity_id == "water-001"
    assert violation.details == {
        "quantity_available": 1000,
        "quantity_allocated": 1100,
        "excess_quantity": 100,
    }


def test_multiple_allocations_are_aggregated() -> None:
    result = validate_resource_allocations(
        resources=[make_resource()],
        allocations=[
            make_allocation("alloc-004", 400),
            make_allocation("alloc-005", 350),
            make_allocation("alloc-006", 350),
        ],
    )

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-04"
    assert violation.details["quantity_allocated"] == 1100
    assert violation.details["excess_quantity"] == 100


def test_unknown_resource_reference_is_reported() -> None:
    result = validate_resource_allocations(
        resources=[make_resource()],
        allocations=[
            make_allocation(
                "alloc-007",
                100,
                resource_id="unknown-resource",
            )
        ],
    )

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-04-UNKNOWN-RESOURCE"
    assert violation.entity_id == "unknown-resource"
