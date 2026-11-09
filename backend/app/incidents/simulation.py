"""Synthetic incident generator for Chennai flood and cyclone exercises.

Incidents are fictional. Areas are real Chennai neighbourhoods, placed at
approximate neighbourhood centres with a small random offset, so that the
simulation can be shown on a real map; the coordinates are labelled
"simulated" and do not identify any real address or event.
"""

import random

from app.incidents.models import Coordinates, IncidentFields
from app.models.scenario import DisasterSeverity, DisasterType

# Approximate neighbourhood centres (latitude, longitude).
INLAND_AREAS = {
    "Velachery": (12.9815, 80.2180),
    "Mudichur": (12.9126, 80.0697),
    "Tambaram": (12.9249, 80.1000),
    "Pallikaranai": (12.9349, 80.2137),
    "Saidapet": (13.0213, 80.2231),
    "Kotturpuram": (13.0185, 80.2400),
    "Adyar": (13.0012, 80.2565),
    "Perungudi": (12.9654, 80.2461),
    "K.K. Nagar": (13.0410, 80.1990),
    "T. Nagar": (13.0418, 80.2341),
    "Anna Nagar": (13.0850, 80.2101),
}
COASTAL_AREAS = {
    "Royapuram": (13.1137, 80.2954),
    "Ennore": (13.2146, 80.3203),
    "Besant Nagar": (12.9990, 80.2668),
    "Triplicane": (13.0588, 80.2756),
    "Mylapore": (13.0339, 80.2619),
    "Adyar": (13.0012, 80.2565),
}

# (situation, needs) pairs. Needs use the resource types of the planning model.
FLOOD_SITUATIONS = [
    ("Waterlogged street, residents stranded", ["rescue_personnel", "food"]),
    ("Ground-floor homes flooded", ["drinking_water", "food"]),
    ("Elderly residents need evacuation", ["rescue_personnel", "emergency_vehicles"]),
    ("Medical camp requests supplies", ["medical_supplies"]),
    ("Road submerged, vehicles stalled", ["emergency_vehicles"]),
    ("Drinking water contamination reported", ["drinking_water", "medical_supplies"]),
]
CYCLONE_SITUATIONS = [
    ("Uprooted trees block the road", ["rescue_personnel", "emergency_vehicles"]),
    ("Roof damage at a community hall", ["rescue_personnel"]),
    ("Power outage, residents request water", ["drinking_water"]),
    ("Fishing families moved to a shelter", ["food", "drinking_water"]),
    (
        "Injury reported after a wall collapse",
        ["medical_supplies", "emergency_vehicles"],
    ),
    ("Coastal flooding near the seafront", ["rescue_personnel", "food"]),
]
POSSIBLY_MISSING = ["callback number", "exact address", "number of injured"]

SEVERITIES = list(DisasterSeverity)
# A simulation of at least this many incidents always includes a critical one,
# so that exercises reliably test the critical-incident alarm.
GUARANTEED_CRITICAL_FROM = 3
SEVERITY_WEIGHTS = [15, 35, 35, 15]
JITTER_DEGREES = 0.004


def simulate_incidents(
    scenario: str, count: int, seed: int | None = None
) -> list[IncidentFields]:
    """Generate count fictional incidents for a flood or cyclone exercise.
    From GUARANTEED_CRITICAL_FROM incidents upwards, at least one is critical."""
    rng = random.Random(seed)
    if scenario == "flood":
        disaster, areas, situations = DisasterType.FLOOD, INLAND_AREAS, FLOOD_SITUATIONS
    elif scenario == "cyclone":
        disaster, areas, situations = (
            DisasterType.CYCLONE,
            COASTAL_AREAS,
            CYCLONE_SITUATIONS,
        )
    else:
        raise ValueError(f"Unknown simulation scenario: {scenario!r}")

    incidents = []
    for _ in range(count):
        area = rng.choice(sorted(areas))
        lat, lon = areas[area]
        situation, needs = rng.choice(situations)
        people = rng.randint(2, 120) * 5
        incidents.append(
            IncidentFields(
                title=f"SIMULATED: {situation}",
                disaster_type=disaster,
                severity=rng.choices(SEVERITIES, SEVERITY_WEIGHTS)[0],
                summary=(
                    f"Synthetic training report: {situation.lower()} in {area}. "
                    f"About {people} people affected (synthetic figure)."
                ),
                location=f"{area}, Chennai (simulated)",
                coordinates=Coordinates(
                    lat=round(lat + rng.uniform(-JITTER_DEGREES, JITTER_DEGREES), 5),
                    lon=round(lon + rng.uniform(-JITTER_DEGREES, JITTER_DEGREES), 5),
                ),
                affected_people=people,
                needs=needs,
                missing_fields=rng.sample(POSSIBLY_MISSING, rng.randint(0, 2)),
            )
        )
    if count >= GUARANTEED_CRITICAL_FROM and not any(
        i.severity == DisasterSeverity.CRITICAL for i in incidents
    ):
        index = rng.randrange(count)
        incidents[index] = incidents[index].model_copy(
            update={"severity": DisasterSeverity.CRITICAL}
        )
    return incidents
