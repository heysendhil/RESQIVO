import pytest
from pydantic import ValidationError

from app.models.shelter import Shelter


def test_valid_shelter() -> None:
    shelter = Shelter(
        shelter_id="shelter-001",
        name="Community Hall",
        location="Simulated Zone A",
        capacity=500,
        current_occupancy=250,
    )

    assert shelter.capacity == 500
    assert shelter.current_occupancy == 250


def test_occupancy_exceeding_capacity_is_representable() -> None:
    # Capacity violations are reported by the validation engine,
    # not rejected by the data model.
    shelter = Shelter(
        shelter_id="shelter-002",
        name="Community Hall",
        location="Simulated Zone A",
        capacity=500,
        current_occupancy=501,
    )

    assert shelter.current_occupancy > shelter.capacity


def test_negative_capacity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Shelter(
            shelter_id="shelter-003",
            name="Community Hall",
            location="Simulated Zone A",
            capacity=-100,
            current_occupancy=0,
        )


def test_negative_occupancy_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Shelter(
            shelter_id="shelter-004",
            name="Community Hall",
            location="Simulated Zone A",
            capacity=500,
            current_occupancy=-1,
        )
