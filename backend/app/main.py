from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.plan import PlanValidationRequest
from app.services.validation import ValidationResult, validate_plan

# Local Next.js development server. Hosted origins are added when deployed.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app = FastAPI(
    title="RESQIVO",
    description="Disaster-response planning and resource optimization.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {
        "status": "ok",
        "service": "RESQIVO",
    }


@app.post("/validate")
def validate(request: PlanValidationRequest) -> ValidationResult:
    """Run deterministic validation on a resource-allocation plan.

    Returns 200 with the validation result, whether or not the plan is
    valid. Malformed request bodies are rejected with 422.
    """
    return validate_plan(
        resources=request.resources,
        allocations=request.allocations,
        shelters=request.shelters,
    )
