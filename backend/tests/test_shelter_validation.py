from app.models.shelter import Shelter
from app.services.validation import validate_shelters


def test_shelter_within_capacity_is_valid() -> None:
    shelter = Shelter(
        shelter_id="shelter-001",
        name="Community Hall",
        location="Simulated Zone A",
        capacity=500,
        current_occupancy=200,
    )

    result = validate_shelters([shelter])

    assert result.valid is True
    assert result.violations == []


def test_full_shelter_is_valid() -> None:
    shelter = Shelter(
        shelter_id="shelter-002",
        name="Community Hall",
        location="Simulated Zone A",
        capacity=500,
        current_occupancy=500,
    )

    result = validate_shelters([shelter])

    assert result.valid is True
    assert result.violations == []


def test_overcapacity_shelter_reports_dom_05() -> None:
    shelter = Shelter(
        shelter_id="shelter-003",
        name="Community Hall",
        location="Simulated Zone A",
        capacity=300,
        current_occupancy=400,
    )

    result = validate_shelters([shelter])

    assert result.valid is False
    assert len(result.violations) == 1

    violation = result.violations[0]

    assert violation.code == "DOM-05"
    assert violation.entity_id == "shelter-003"
    assert violation.details == {
        "capacity": 300,
        "current_occupancy": 400,
        "excess_occupancy": 100,
    }


def test_multiple_shelters_report_only_violations() -> None:
    shelters = [
        Shelter(
            shelter_id="shelter-001",
            name="Shelter A",
            location="Zone A",
            capacity=500,
            current_occupancy=200,
        ),
        Shelter(
            shelter_id="shelter-002",
            name="Shelter B",
            location="Zone B",
            capacity=300,
            current_occupancy=400,
        ),
        Shelter(
            shelter_id="shelter-003",
            name="Shelter C",
            location="Zone C",
            capacity=200,
            current_occupancy=250,
        ),
    ]

    result = validate_shelters(shelters)

    assert result.valid is False
    assert len(result.violations) == 2

    assert {violation.entity_id for violation in result.violations} == {
        "shelter-002",
        "shelter-003",
    }

    assert all(violation.code == "DOM-05" for violation in result.violations)
