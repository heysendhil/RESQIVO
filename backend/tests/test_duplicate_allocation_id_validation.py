from app.models.allocation import ResourceAllocation
from app.models.resource import Resource, ResourceType
from app.models.shelter import Shelter
from app.services.validation import validate_allocation_ids, validate_plan


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


def make_shelter(shelter_id: str = "shelter-001") -> Shelter:
    return Shelter(
        shelter_id=shelter_id,
        name="Community Hall",
        location="Simulated Zone A",
        capacity=500,
        current_occupancy=200,
    )


def test_unique_allocation_ids_are_valid() -> None:
    result = validate_allocation_ids(
        [make_allocation("alloc-001"), make_allocation("alloc-002")]
    )

    assert result.valid is True
    assert result.violations == []


def test_duplicate_allocation_id_reports_dom_04_duplicate_allocation() -> None:
    result = validate_allocation_ids(
        [make_allocation("alloc-001"), make_allocation("alloc-001")]
    )

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-04-DUPLICATE-ALLOCATION"
    assert violation.entity_id == "alloc-001"
    assert violation.details == {"occurrences": 2}


def test_multiple_duplicate_allocation_ids_report_correct_counts() -> None:
    allocations = [
        make_allocation("alloc-001"),
        make_allocation("alloc-002"),
        make_allocation("alloc-001"),
        make_allocation("alloc-003"),
        make_allocation("alloc-002"),
        make_allocation("alloc-002"),
    ]

    result = validate_allocation_ids(allocations)

    assert [
        (violation.entity_id, violation.details) for violation in result.violations
    ] == [
        ("alloc-001", {"occurrences": 2}),
        ("alloc-002", {"occurrences": 3}),
    ]


def test_duplicate_allocation_violations_follow_first_occurrence_order() -> None:
    allocations = [
        make_allocation("alloc-002"),
        make_allocation("alloc-001"),
        make_allocation("alloc-002"),
        make_allocation("alloc-001"),
    ]

    first_run = validate_allocation_ids(allocations)
    second_run = validate_allocation_ids(allocations)

    assert first_run == second_run
    assert [violation.entity_id for violation in first_run.violations] == [
        "alloc-002",
        "alloc-001",
    ]


def test_duplicate_ids_with_valid_references_report_only_the_duplicate() -> None:
    result = validate_plan(
        resources=[make_resource()],
        allocations=[make_allocation("alloc-001"), make_allocation("alloc-001")],
        shelters=[make_shelter()],
    )

    assert result.valid is False
    assert [violation.code for violation in result.violations] == [
        "DOM-04-DUPLICATE-ALLOCATION"
    ]


def test_duplicate_allocations_are_not_merged_or_removed() -> None:
    # Both allocations still count towards stock: 600 + 600 exceeds 1000.
    result = validate_plan(
        resources=[make_resource(quantity_available=1000)],
        allocations=[
            make_allocation("alloc-001", quantity_allocated=600),
            make_allocation("alloc-001", quantity_allocated=600),
        ],
        shelters=[make_shelter()],
    )

    assert [violation.code for violation in result.violations] == [
        "DOM-04",
        "DOM-04-DUPLICATE-ALLOCATION",
    ]
    assert result.violations[0].details == {
        "quantity_available": 1000,
        "quantity_allocated": 1200,
        "excess_quantity": 200,
    }


def test_each_duplicate_allocation_is_still_checked_for_destination() -> None:
    result = validate_plan(
        resources=[make_resource()],
        allocations=[
            make_allocation("alloc-001", destination_id="shelter-001"),
            make_allocation("alloc-001", destination_id="shelter-999"),
        ],
        shelters=[make_shelter()],
    )

    assert [
        (violation.code, violation.entity_id) for violation in result.violations
    ] == [
        ("DOM-04-DUPLICATE-ALLOCATION", "alloc-001"),
        ("DOM-06-UNKNOWN-DESTINATION", "alloc-001"),
    ]


def test_destination_validation_with_unique_allocation_ids() -> None:
    result = validate_plan(
        resources=[make_resource()],
        allocations=[
            make_allocation("alloc-001", destination_id="shelter-001"),
            make_allocation("alloc-002", destination_id="shelter-999"),
        ],
        shelters=[make_shelter()],
    )

    assert [
        (violation.code, violation.entity_id) for violation in result.violations
    ] == [("DOM-06-UNKNOWN-DESTINATION", "alloc-002")]
