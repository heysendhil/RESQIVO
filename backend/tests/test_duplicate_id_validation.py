from app.models.allocation import ResourceAllocation
from app.models.resource import Resource, ResourceType
from app.models.shelter import Shelter
from app.services.validation import (
    validate_plan,
    validate_resource_allocations,
    validate_shelters,
)


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
    allocation_id: str = "alloc-001",
    resource_id: str = "water-001",
    destination_id: str = "shelter-001",
    quantity_allocated: int = 100,
) -> ResourceAllocation:
    return ResourceAllocation(
        allocation_id=allocation_id,
        resource_id=resource_id,
        destination_id=destination_id,
        quantity_allocated=quantity_allocated,
    )


def make_shelter(
    shelter_id: str = "shelter-001",
    capacity: int = 500,
    current_occupancy: int = 200,
) -> Shelter:
    return Shelter(
        shelter_id=shelter_id,
        name="Community Hall",
        location="Simulated Zone A",
        capacity=capacity,
        current_occupancy=current_occupancy,
    )


def test_unique_resource_ids_are_valid() -> None:
    result = validate_resource_allocations(
        resources=[make_resource("water-001"), make_resource("water-002")],
        allocations=[make_allocation(resource_id="water-001")],
    )

    assert result.valid is True
    assert result.violations == []


def test_duplicate_resource_id_reports_dom_04_duplicate_resource() -> None:
    result = validate_resource_allocations(
        resources=[make_resource("water-001"), make_resource("water-001")],
        allocations=[],
    )

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-04-DUPLICATE-RESOURCE"
    assert violation.entity_id == "water-001"
    assert violation.details == {"occurrences": 2}


def test_duplicate_resource_result_does_not_depend_on_entry_order() -> None:
    # Previously the last duplicate silently overwrote earlier entries, so
    # the stock check depended on which entry came last.
    allocations = [make_allocation(quantity_allocated=4000)]
    large_first = [
        make_resource("water-001", quantity_available=5000),
        make_resource("water-001", quantity_available=100),
    ]

    result_large_first = validate_resource_allocations(large_first, allocations)
    result_small_first = validate_resource_allocations(
        list(reversed(large_first)), allocations
    )

    assert result_large_first == result_small_first
    assert [violation.code for violation in result_large_first.violations] == [
        "DOM-04-DUPLICATE-RESOURCE"
    ]


def test_allocation_to_duplicate_resource_is_not_reported_as_unknown() -> None:
    result = validate_resource_allocations(
        resources=[make_resource("water-001"), make_resource("water-001")],
        allocations=[make_allocation(resource_id="water-001")],
    )

    assert [violation.code for violation in result.violations] == [
        "DOM-04-DUPLICATE-RESOURCE"
    ]


def test_unique_shelter_ids_are_valid() -> None:
    result = validate_shelters(
        [make_shelter("shelter-001"), make_shelter("shelter-002")]
    )

    assert result.valid is True
    assert result.violations == []


def test_duplicate_shelter_id_reports_dom_05_duplicate_shelter() -> None:
    result = validate_shelters(
        [make_shelter("shelter-001"), make_shelter("shelter-001")]
    )

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-05-DUPLICATE-SHELTER"
    assert violation.entity_id == "shelter-001"
    assert violation.details == {"occurrences": 2}


def test_multiple_duplicate_ids_are_each_reported_once() -> None:
    resources = [
        make_resource("water-001"),
        make_resource("water-002"),
        make_resource("water-001"),
        make_resource("water-003"),
        make_resource("water-002"),
        make_resource("water-002"),
    ]

    result = validate_resource_allocations(resources, allocations=[])

    assert [
        (violation.entity_id, violation.details) for violation in result.violations
    ] == [
        ("water-001", {"occurrences": 2}),
        ("water-002", {"occurrences": 3}),
    ]


def test_duplicate_violations_follow_first_occurrence_order() -> None:
    shelters = [
        make_shelter("shelter-002"),
        make_shelter("shelter-001"),
        make_shelter("shelter-002"),
        make_shelter("shelter-001"),
    ]

    first_run = validate_shelters(shelters)
    second_run = validate_shelters(shelters)

    assert first_run == second_run
    assert [violation.entity_id for violation in first_run.violations] == [
        "shelter-002",
        "shelter-001",
    ]


def test_plan_reports_resource_duplicates_before_shelter_duplicates() -> None:
    result = validate_plan(
        resources=[make_resource("water-001"), make_resource("water-001")],
        allocations=[],
        shelters=[make_shelter("shelter-001"), make_shelter("shelter-001")],
    )

    assert result.valid is False
    assert [violation.code for violation in result.violations] == [
        "DOM-04-DUPLICATE-RESOURCE",
        "DOM-05-DUPLICATE-SHELTER",
    ]


def test_destination_validation_with_unique_shelter_ids() -> None:
    shelters = [make_shelter("shelter-001"), make_shelter("shelter-002")]

    known = validate_plan(
        resources=[make_resource()],
        allocations=[make_allocation(destination_id="shelter-002")],
        shelters=shelters,
    )
    unknown = validate_plan(
        resources=[make_resource()],
        allocations=[make_allocation(destination_id="shelter-999")],
        shelters=shelters,
    )

    assert known.valid is True
    assert known.violations == []
    assert [violation.code for violation in unknown.violations] == [
        "DOM-06-UNKNOWN-DESTINATION"
    ]
    assert unknown.violations[0].entity_id == "alloc-001"


def test_unique_resource_stock_is_still_checked_alongside_duplicates() -> None:
    result = validate_resource_allocations(
        resources=[
            make_resource("water-001"),
            make_resource("water-001"),
            make_resource("water-002", quantity_available=1000),
        ],
        allocations=[make_allocation(resource_id="water-002", quantity_allocated=1100)],
    )

    assert [violation.code for violation in result.violations] == [
        "DOM-04-DUPLICATE-RESOURCE",
        "DOM-04",
    ]
    assert result.violations[1].entity_id == "water-002"
    assert result.violations[1].details == {
        "quantity_available": 1000,
        "quantity_allocated": 1100,
        "excess_quantity": 100,
    }


def test_shelter_capacity_is_still_checked_alongside_duplicates() -> None:
    result = validate_shelters(
        [
            make_shelter("shelter-001"),
            make_shelter("shelter-001"),
            make_shelter("shelter-002", capacity=300, current_occupancy=400),
        ]
    )

    assert [violation.code for violation in result.violations] == [
        "DOM-05-DUPLICATE-SHELTER",
        "DOM-05",
    ]
    assert result.violations[1].entity_id == "shelter-002"
    assert result.violations[1].details == {
        "capacity": 300,
        "current_occupancy": 400,
        "excess_occupancy": 100,
    }
