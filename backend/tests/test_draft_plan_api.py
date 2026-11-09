import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_draft_workflow, get_qa_service, get_review_workflow
from app.qa.errors import ModelResponseError, RetrievalUnavailableError
from app.qa.schemas import AnswerResponse
from app.workflow.schemas import MAX_DRAFT_CONSTRAINTS, ReviewResponse
from tests.test_draft_plan import DraftModel, draft_request, workflow
from tests.test_workflow import plan

pytestmark = pytest.mark.usefixtures("no_network")

client = TestClient(app)


class FakeDraftWorkflow:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def run(self, request, request_id):
        self.calls.append((request, request_id))
        if self.error:
            raise self.error
        return workflow(model=DraftModel()).run(request, request_id)


@pytest.fixture
def use_workflow():
    def install(fake):
        app.dependency_overrides[get_draft_workflow] = lambda: fake
        return fake

    yield install
    app.dependency_overrides.clear()


def payload(**overrides):
    return {**draft_request().model_dump(mode="json"), **overrides}


def test_draft_plan_returns_validated_proposal(use_workflow):
    fake = use_workflow(FakeDraftWorkflow())

    response = client.post("/draft-plan", json=payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft_valid"
    assert body["request_id"] == fake.calls[0][1]
    assert len(body["request_id"]) == 32
    assert body["plan_review"]["final_validation"] == {"valid": True, "violations": []}
    assert body["plan_review"]["max_correction_attempts"] == 2
    assert body["input_validation"] == {"valid": True, "violations": []}
    assert body["guidance"]["citations"][0]["source_id"] == "SYN-001"
    assert "draft proposal for human review" in body["notice"]


def test_request_ids_differ_between_requests(use_workflow):
    fake = use_workflow(FakeDraftWorkflow())

    client.post("/draft-plan", json=payload())
    client.post("/draft-plan", json=payload())

    assert fake.calls[0][1] != fake.calls[1][1]


def test_insufficient_information_is_a_200_without_a_draft(use_workflow):
    use_workflow(FakeDraftWorkflow())

    body = client.post("/draft-plan", json=payload(resources=[])).json()

    assert body["status"] == "insufficient_information"
    assert body["reason"] == "no_available_resources"
    assert body["plan_review"] is None
    assert body["guidance"] is None


def _with(path, value):
    data = payload()
    target = data
    *parents, last = path
    for key in parents:
        target = target[key]
    target[last] = value
    return data


@pytest.mark.parametrize(
    "body",
    [
        {},
        {k: v for k, v in payload().items() if k != "scenario"},
        {k: v for k, v in payload().items() if k != "resources"},
        {k: v for k, v in payload().items() if k != "shelters"},
        payload(extra=1),
        payload(allocations=[]),
        _with(("resources", 0, "quantity_available"), -1),
        _with(("shelters", 0, "capacity"), -1),
        _with(("scenario", "affected_population"), -1),
        _with(("scenario", "disaster_type"), "meteor"),
        _with(("needs", 0, "destination_id"), "shelter-999"),
        _with(("needs", 0, "quantity_needed"), -5),
        payload(constraints=["   "]),
        payload(constraints=["x" * 501]),
        payload(constraints=["ok"] * (MAX_DRAFT_CONSTRAINTS + 1)),
        payload(resources="water"),
    ],
)
def test_malformed_requests_are_rejected(use_workflow, body):
    fake = use_workflow(FakeDraftWorkflow())

    assert client.post("/draft-plan", json=body).status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (
            ModelResponseError("The language model did not return a usable draft."),
            502,
            "The language model did not return a usable answer.",
        ),
        (
            RetrievalUnavailableError("Knowledge retrieval failed."),
            503,
            "Knowledge retrieval is unavailable.",
        ),
    ],
)
def test_errors_hide_internal_details(use_workflow, error, status, detail):
    error.__cause__ = RuntimeError("Traceback api_key=sk-not-real prompt=SYSTEM")
    use_workflow(FakeDraftWorkflow(error=error))

    response = client.post("/draft-plan", json=payload())

    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "sk-not-real" not in response.text


def test_draft_plan_without_credentials_returns_503(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("RESQIVO_CHROMA_DIR", str(tmp_path / "chroma"))

    response = client.post("/draft-plan", json=payload())

    assert response.status_code == 503
    assert response.json() == {"detail": "Question answering is not configured."}


# Regression: existing endpoints are unchanged -----------------------------------


def test_existing_endpoints_still_behave_the_same():
    class Service:
        def answer(self, question):
            return AnswerResponse(
                status="insufficient_evidence", reason="no_relevant_passages"
            )

    class Review:
        def run(self, question, plan=None):
            return ReviewResponse(answer=Service().answer(question))

    app.dependency_overrides[get_qa_service] = Service
    app.dependency_overrides[get_review_workflow] = Review
    try:
        assert client.get("/health").json() == {"status": "ok", "service": "RESQIVO"}

        body = client.post("/validate", json=plan(quantity=1100).model_dump()).json()
        assert body["valid"] is False
        assert [v["code"] for v in body["violations"]] == ["DOM-04"]

        answer = client.post("/answer", json={"question": "Water?"})
        assert answer.status_code == 200
        assert answer.json()["reason"] == "no_relevant_passages"

        review = client.post("/review", json={"question": "Review"})
        assert review.status_code == 200
        assert review.json()["plan_review"] is None
    finally:
        app.dependency_overrides.clear()


def test_startup_does_not_load_langgraph_chromadb_or_the_model_client():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.main; print(sorted(m for m in sys.modules if "
            "m.startswith(('langgraph', 'chromadb', 'langchain_google_genai', "
            "'google.genai', 'app.rag', 'app.workflow.graph', "
            "'app.workflow.drafting'))))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "[]"
