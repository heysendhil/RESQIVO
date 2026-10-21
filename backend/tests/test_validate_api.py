from typing import Any

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_resource(quantity_available: int = 1000) -> dict[str, Any]:
    return {
        "resource_id": "water-001",
        "name": "Drinking Water",
        "resource_type": "drinking_water",
        "quantity_available": quantity_available,
        "unit": "litres",
        "location": "Warehouse A",
    }


def make_allocation(
    quantity_allocated: int = 400,
    destination_id: str = "shelter-001",
) -> dict[str, Any]:
    return {
        "allocation_id": "alloc-001",
        "resource_id": "water-001",
        "destination_id": destination_id,
        "quantity_allocated": quantity_allocated,
    }


def make_shelter() -> dict[str, Any]:
    return {
        "shelter_id": "shelter-001",
        "name": "Community Hall",
        "location": "Simulated Zone A",
        "capacity": 500,
        "current_occupancy": 200,
    }


def test_valid_plan_returns_valid_result() -> None:
    response = client.post(
        "/validate",
        json={
            "resources": [make_resource()],
            "allocations": [make_allocation()],
            "shelters": [make_shelter()],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"valid": True, "violations": []}


def test_overallocation_returns_dom_04_violation() -> None:
    response = client.post(
        "/validate",
        json={
            "resources": [make_resource(quantity_available=1000)],
            "allocations": [make_allocation(quantity_allocated=1100)],
            "shelters": [make_shelter()],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": False,
        "violations": [
            {
                "code": "DOM-04",
                "entity_id": "water-001",
                "message": "Resource allocation exceeds available stock.",
                "details": {
                    "quantity_available": 1000,
                    "quantity_allocated": 1100,
                    "excess_quantity": 100,
                },
            }
        ],
    }


def test_unknown_destination_returns_dom_06_violation() -> None:
    response = client.post(
        "/validate",
        json={
            "resources": [make_resource()],
            "allocations": [make_allocation(destination_id="shelter-999")],
            "shelters": [make_shelter()],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": False,
        "violations": [
            {
                "code": "DOM-06-UNKNOWN-DESTINATION",
                "entity_id": "alloc-001",
                "message": "Allocation references an unknown destination.",
                "details": {},
            }
        ],
    }


def test_violation_order_matches_validate_plan() -> None:
    response = client.post(
        "/validate",
        json={
            "resources": [make_resource(quantity_available=1000)],
            "allocations": [
                make_allocation(quantity_allocated=1100, destination_id="shelter-999")
            ],
            "shelters": [make_shelter()],
        },
    )

    assert response.status_code == 200
    assert [violation["code"] for violation in response.json()["violations"]] == [
        "DOM-04",
        "DOM-06-UNKNOWN-DESTINATION",
    ]


def test_missing_field_is_rejected_with_422() -> None:
    response = client.post(
        "/validate",
        json={"resources": [], "allocations": []},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "shelters"]


def test_invalid_model_value_is_rejected_with_422() -> None:
    response = client.post(
        "/validate",
        json={
            "resources": [make_resource(quantity_available=-1)],
            "allocations": [],
            "shelters": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == [
        "body",
        "resources",
        0,
        "quantity_available",
    ]


def test_unknown_request_field_is_rejected_with_422() -> None:
    response = client.post(
        "/validate",
        json={
            "resources": [],
            "allocations": [],
            "shelters": [],
            "notes": "not allowed",
        },
    )

    assert response.status_code == 422


def test_non_json_body_is_rejected_with_422() -> None:
    response = client.post(
        "/validate",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_empty_plan_follows_current_validate_plan_behavior() -> None:
    # Matches test_empty_plan_is_valid in test_plan_validation.py: missing-data
    # detection (DOM-06) is not implemented, so an empty plan is not flagged.
    response = client.post(
        "/validate",
        json={"resources": [], "allocations": [], "shelters": []},
    )

    assert response.status_code == 200
    assert response.json() == {"valid": True, "violations": []}
