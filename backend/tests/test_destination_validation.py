from app.models.allocation import ResourceAllocation
from app.models.shelter import Shelter
from app.services.validation import validate_allocation_destinations


def make_allocation(
    allocation_id: str = "allocation-001",
    destination_id: str = "shelter-001",
) -> ResourceAllocation:
    return ResourceAllocation(
        allocation_id=allocation_id,
        resource_id="resource-001",
        destination_id=destination_id,
        quantity_allocated=50,
    )


def make_shelter(shelter_id: str = "shelter-001") -> Shelter:
    return Shelter(
        shelter_id=shelter_id,
        name="Emergency Shelter",
        location="Relief Camp A",
        capacity=100,
        current_occupancy=50,
    )


def test_allocation_to_known_shelter_is_valid() -> None:
    result = validate_allocation_destinations(
        allocations=[make_allocation()],
        shelters=[make_shelter()],
    )

    assert result.valid is True
    assert result.violations == []


def test_allocation_to_unknown_destination_reports_dom_06() -> None:
    result = validate_allocation_destinations(
        allocations=[make_allocation(destination_id="shelter-999")],
        shelters=[make_shelter()],
    )

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-06-UNKNOWN-DESTINATION"
    assert violation.entity_id == "allocation-001"


def test_each_allocation_to_unknown_destination_is_reported() -> None:
    result = validate_allocation_destinations(
        allocations=[
            make_allocation("allocation-001", "shelter-001"),
            make_allocation("allocation-002", "shelter-998"),
            make_allocation("allocation-003", "shelter-999"),
        ],
        shelters=[make_shelter()],
    )

    assert result.valid is False
    assert {violation.entity_id for violation in result.violations} == {
        "allocation-002",
        "allocation-003",
    }


def test_allocations_without_shelters_are_reported() -> None:
    result = validate_allocation_destinations(
        allocations=[make_allocation()],
        shelters=[],
    )

    assert result.valid is False
    assert result.violations[0].code == "DOM-06-UNKNOWN-DESTINATION"
