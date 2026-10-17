from fastapi import FastAPI

app = FastAPI(
    title="RESQIVO",
    description="Disaster-response planning and resource optimization.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {
        "status": "ok",
        "service": "RESQIVO",
    }
