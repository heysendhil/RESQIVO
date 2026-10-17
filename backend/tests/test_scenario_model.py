import pytest
from pydantic import ValidationError

from app.models.scenario import (
    DisasterScenario,
    DisasterSeverity,
    DisasterType,
)


def test_valid_disaster_scenario() -> None:
    scenario = DisasterScenario(
        scenario_id="scenario-001",
        name="Bengaluru Flood Simulation",
        disaster_type=DisasterType.FLOOD,
        severity=DisasterSeverity.HIGH,
        affected_population=5000,
        location="Simulated Zone A",
        description="Synthetic flood scenario for testing.",
    )

    assert scenario.scenario_id == "scenario-001"
    assert scenario.disaster_type == DisasterType.FLOOD
    assert scenario.affected_population == 5000


def test_negative_affected_population_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DisasterScenario(
            scenario_id="scenario-002",
            name="Invalid Scenario",
            disaster_type=DisasterType.EARTHQUAKE,
            severity=DisasterSeverity.MODERATE,
            affected_population=-100,
            location="Simulated Zone B",
        )


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        DisasterScenario(
            scenario_id="scenario-003",
            name="Unknown Field Test",
            disaster_type=DisasterType.FLOOD,
            severity=DisasterSeverity.LOW,
            affected_population=100,
            location="Simulated Zone C",
            unexpected_field="not allowed",
        )
