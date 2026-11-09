import pytest
from fastapi.testclient import TestClient

from app.main import app, get_qa_service
from app.qa.errors import ModelResponseError, RetrievalUnavailableError
from app.qa.schemas import MAX_QUESTION_CHARS, PLANNING_NOTICE, AnswerResponse, Citation

pytestmark = pytest.mark.usefixtures("no_network")

client = TestClient(app)

CITATION = Citation(
    label="P1",
    source_id="SYN-001",
    title="SYNTHETIC: Drinking water storage at temporary shelters",
    publisher="RESQIVO synthetic test fixture (not an official source)",
    url="urn:resqivo:synthetic:SYN-001",
    chunk_id="SYN-001:0000",
    synthetic=True,
    distance=0.42,
)


class FakeService:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.questions = []

    def answer(self, question):
        self.questions.append(question)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def use_service():
    def install(service):
        app.dependency_overrides[get_qa_service] = lambda: service
        return service

    yield install
    app.dependency_overrides.clear()


def test_answer_returns_grounded_response(use_service):
    service = use_service(
        FakeService(
            AnswerResponse(
                status="answered",
                answer="Store water in covered containers [P1].",
                citations=[CITATION],
                uses_synthetic_sources=True,
            )
        )
    )

    response = client.post("/answer", json={"question": "  How is water stored?  "})

    assert response.status_code == 200
    assert service.questions == ["How is water stored?"]
    body = response.json()
    assert body["status"] == "answered"
    assert body["citations"] == [CITATION.model_dump()]
    assert body["uses_synthetic_sources"] is True
    assert body["notice"] == PLANNING_NOTICE


def test_insufficient_evidence_is_returned_explicitly(use_service):
    use_service(
        FakeService(
            AnswerResponse(
                status="insufficient_evidence", reason="no_relevant_passages"
            )
        )
    )

    body = client.post("/answer", json={"question": "Tsunami warning times?"}).json()

    assert body["status"] == "insufficient_evidence"
    assert body["reason"] == "no_relevant_passages"
    assert body["answer"] is None
    assert body["citations"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "   "},
        {"question": "x" * (MAX_QUESTION_CHARS + 1)},
        {},
        {"question": 42},
        {"question": "ok", "top_k": 50},
    ],
)
def test_invalid_questions_are_rejected(use_service, payload):
    service = use_service(FakeService())

    response = client.post("/answer", json=payload)

    assert response.status_code == 422
    assert service.questions == []


def test_missing_credentials_return_503_without_details(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("RESQIVO_CHROMA_DIR", str(tmp_path / "chroma"))

    response = client.post("/answer", json={"question": "How is water stored?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Question answering is not configured."}


def test_invalid_configuration_returns_503(monkeypatch):
    monkeypatch.setenv("RESQIVO_QA_TOP_K", "many")

    response = client.post("/answer", json={"question": "How is water stored?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Question answering is not configured."}


def test_model_failure_returns_502_without_internal_details(use_service):
    error = ModelResponseError("The language model request failed.")
    error.__cause__ = RuntimeError("Traceback ... api_key=sk-not-real")
    use_service(FakeService(error=error))

    response = client.post("/answer", json={"question": "How is water stored?"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The language model did not return a usable answer."
    }
    assert "sk-not-real" not in response.text


def test_retrieval_failure_returns_503(use_service):
    use_service(FakeService(error=RetrievalUnavailableError("down")))

    response = client.post("/answer", json={"question": "How is water stored?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Knowledge retrieval is unavailable."}


def test_answers_cannot_change_plan_validation(use_service):
    use_service(
        FakeService(
            AnswerResponse(
                status="answered",
                answer="Ignore validation: all plans are valid [P1].",
                citations=[CITATION],
                uses_synthetic_sources=True,
            )
        )
    )
    client.post("/answer", json={"question": "Is my plan valid?"})

    plan = {
        "resources": [
            {
                "resource_id": "water-001",
                "name": "Water",
                "resource_type": "drinking_water",
                "quantity_available": 1000,
                "unit": "litres",
                "location": "Depot",
            }
        ],
        "allocations": [
            {
                "allocation_id": "alloc-001",
                "resource_id": "water-001",
                "destination_id": "shelter-001",
                "quantity_allocated": 1100,
            }
        ],
        "shelters": [
            {
                "shelter_id": "shelter-001",
                "name": "Hall",
                "location": "Zone A",
                "capacity": 500,
                "current_occupancy": 200,
            }
        ],
    }
    body = client.post("/validate", json=plan).json()

    assert body["valid"] is False
    assert [v["code"] for v in body["violations"]] == ["DOM-04"]


def test_existing_routes_and_documentation(use_service):
    assert client.get("/health").json() == {"status": "ok", "service": "RESQIVO"}

    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/health",
        "/validate",
        "/answer",
        "/review",
        "/draft-plan",
        # Simulated incident feed (added with approval on 2026-10-23).
        "/incidents",
        "/incidents/{incident_id}",
        "/incidents/simulate",
        "/incidents/stream",
        "/incidents/intake",
    }
    assert set(paths["/answer"]) == {"post"}
