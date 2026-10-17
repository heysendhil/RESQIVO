from collections import Counter
from dataclasses import dataclass

from app.models.allocation import ResourceAllocation
from app.models.resource import Resource
from app.models.shelter import Shelter


@dataclass(frozen=True)
class ValidationViolation:
    """Represents a deterministic planning constraint violation.

    The code determines what kind of entity entity_id identifies:

    - DOM-04: the over-allocated resource.
    - DOM-04-UNKNOWN-RESOURCE: the unknown resource ID referenced by
      allocations. One violation is reported per resource ID, with the
      quantities of all its allocations aggregated.
    - DOM-04-DUPLICATE-RESOURCE: the resource ID shared by more than one
      resource. One violation is reported per duplicated ID.
    - DOM-04-DUPLICATE-ALLOCATION: the allocation ID shared by more than
      one allocation. One violation is reported per duplicated ID.
    - DOM-05: the over-capacity shelter.
    - DOM-05-DUPLICATE-SHELTER: the shelter ID shared by more than one
      shelter. One violation is reported per duplicated ID.
    - DOM-06-UNKNOWN-DESTINATION: the allocation whose destination is
      unknown. One violation is reported per allocation.
    """

    code: str
    entity_id: str
    message: str
    details: dict[str, int]


@dataclass(frozen=True)
class ValidationResult:
    """Contains the outcome of deterministic validation."""

    valid: bool
    violations: list[ValidationViolation]


def _count_duplicate_ids(ids: list[str]) -> dict[str, int]:
    """Return each ID that occurs more than once, with its occurrence count.

    IDs are returned in order of their first occurrence, so the result is
    deterministic for a given input order.
    """
    return {
        entity_id: occurrences
        for entity_id, occurrences in Counter(ids).items()
        if occurrences > 1
    }


def validate_shelters(
    shelters: list[Shelter],
) -> ValidationResult:
    """Validate shelter identifiers and occupancy against capacity.

    Duplicate shelter IDs are reported first, because they make
    destination references to those shelters ambiguous. Capacity is
    still checked for every shelter entry.
    """
    violations: list[ValidationViolation] = []

    duplicate_shelter_ids = _count_duplicate_ids(
        [shelter.shelter_id for shelter in shelters]
    )

    for shelter_id, occurrences in duplicate_shelter_ids.items():
        violations.append(
            ValidationViolation(
                code="DOM-05-DUPLICATE-SHELTER",
                entity_id=shelter_id,
                message="Shelter ID is used by more than one shelter.",
                details={"occurrences": occurrences},
            )
        )

    for shelter in shelters:
        if shelter.current_occupancy > shelter.capacity:
            excess_occupancy = shelter.current_occupancy - shelter.capacity

            violations.append(
                ValidationViolation(
                    code="DOM-05",
                    entity_id=shelter.shelter_id,
                    message=("Shelter occupancy exceeds available capacity."),
                    details={
                        "capacity": shelter.capacity,
                        "current_occupancy": shelter.current_occupancy,
                        "excess_occupancy": excess_occupancy,
                    },
                )
            )

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
    )


def validate_resource_allocations(
    resources: list[Resource],
    allocations: list[ResourceAllocation],
) -> ValidationResult:
    """Validate aggregate allocations against available inventory.

    Allocation quantities are aggregated by resource ID. This ensures
    that multiple individually valid allocations cannot collectively
    exceed the available stock.

    Allocations referencing unknown resources are reported separately.

    Duplicate resource IDs are reported, and their stock is not compared
    against allocations, because the available quantity for that ID is
    ambiguous. The duplicate violation already makes the result invalid.
    """
    violations: list[ValidationViolation] = []

    duplicate_resource_ids = _count_duplicate_ids(
        [resource.resource_id for resource in resources]
    )

    for resource_id, occurrences in duplicate_resource_ids.items():
        violations.append(
            ValidationViolation(
                code="DOM-04-DUPLICATE-RESOURCE",
                entity_id=resource_id,
                message="Resource ID is used by more than one resource.",
                details={"occurrences": occurrences},
            )
        )

    known_resource_ids = {resource.resource_id for resource in resources}

    allocated_by_resource: dict[str, int] = {}

    for allocation in allocations:
        allocated_by_resource[allocation.resource_id] = (
            allocated_by_resource.get(allocation.resource_id, 0)
            + allocation.quantity_allocated
        )

    # Report allocations referencing resources that do not exist.
    for resource_id, quantity_allocated in allocated_by_resource.items():
        if resource_id not in known_resource_ids:
            violations.append(
                ValidationViolation(
                    code="DOM-04-UNKNOWN-RESOURCE",
                    entity_id=resource_id,
                    message=("Allocation references an unknown resource."),
                    details={
                        "quantity_allocated": quantity_allocated,
                    },
                )
            )

    # Compare aggregate allocations against available inventory.
    for resource in resources:
        resource_id = resource.resource_id

        if resource_id in duplicate_resource_ids:
            continue

        quantity_allocated = allocated_by_resource.get(resource_id, 0)

        if quantity_allocated > resource.quantity_available:
            excess_quantity = quantity_allocated - resource.quantity_available

            violations.append(
                ValidationViolation(
                    code="DOM-04",
                    entity_id=resource_id,
                    message=("Resource allocation exceeds available stock."),
                    details={
                        "quantity_available": resource.quantity_available,
                        "quantity_allocated": quantity_allocated,
                        "excess_quantity": excess_quantity,
                    },
                )
            )

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
    )


def validate_allocation_ids(
    allocations: list[ResourceAllocation],
) -> ValidationResult:
    """Validate that every allocation has a unique ID.

    Duplicate allocation IDs make allocation-level findings, such as
    DOM-06-UNKNOWN-DESTINATION, ambiguous. They are reported without
    removing, merging or altering any allocation, so every allocation
    still contributes to the other checks.
    """
    violations: list[ValidationViolation] = []

    duplicate_allocation_ids = _count_duplicate_ids(
        [allocation.allocation_id for allocation in allocations]
    )

    for allocation_id, occurrences in duplicate_allocation_ids.items():
        violations.append(
            ValidationViolation(
                code="DOM-04-DUPLICATE-ALLOCATION",
                entity_id=allocation_id,
                message="Allocation ID is used by more than one allocation.",
                details={"occurrences": occurrences},
            )
        )

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
    )


def validate_allocation_destinations(
    allocations: list[ResourceAllocation],
    shelters: list[Shelter],
) -> ValidationResult:
    """Validate that every allocation is sent to a known shelter.

    An allocation to an unknown destination cannot be delivered, so it
    is reported rather than silently accepted.

    Shelters are currently the only valid destinations, because the
    domain model has no other destination types. An allocation to any
    other location is reported as an unknown destination.
    """
    violations: list[ValidationViolation] = []

    shelter_ids = {shelter.shelter_id for shelter in shelters}

    for allocation in allocations:
        if allocation.destination_id not in shelter_ids:
            violations.append(
                ValidationViolation(
                    code="DOM-06-UNKNOWN-DESTINATION",
                    entity_id=allocation.allocation_id,
                    message=("Allocation references an unknown destination."),
                    details={},
                )
            )

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
    )


def validate_plan(
    resources: list[Resource],
    allocations: list[ResourceAllocation],
    shelters: list[Shelter],
) -> ValidationResult:
    """Run every deterministic check and combine the findings.

    A plan is valid only when every individual check passes.
    """
    results = [
        validate_resource_allocations(resources, allocations),
        validate_allocation_ids(allocations),
        validate_allocation_destinations(allocations, shelters),
        validate_shelters(shelters),
    ]

    violations = [violation for result in results for violation in result.violations]

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
    )
