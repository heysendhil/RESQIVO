import pytest
from fastapi.testclient import TestClient

from app.main import app, get_review_workflow
from app.qa.errors import ModelResponseError
from app.qa.schemas import AnswerResponse
from app.services.validation import validate_plan
from app.workflow.schemas import PlanReview, ReviewResponse
from tests.test_workflow import plan

pytestmark = pytest.mark.usefixtures("no_network")

client = TestClient(app)


class FakeWorkflow:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def run(self, question, plan=None):
        self.calls.append((question, plan))
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def use_workflow():
    def install(fake):
        app.dependency_overrides[get_review_workflow] = lambda: fake
        return fake

    yield install
    app.dependency_overrides.clear()


def test_review_returns_answer_and_plan_review(use_workflow):
    submitted = plan(quantity=1100)
    validation = validate_plan(
        submitted.resources, submitted.allocations, submitted.shelters
    )
    fake = use_workflow(
        FakeWorkflow(
            ReviewResponse(
                answer=AnswerResponse(
                    status="insufficient_evidence", reason="no_relevant_passages"
                ),
                plan_review=PlanReview(
                    original_validation=validation,
                    final_plan=submitted,
                    final_validation=validation,
                    correction_attempts=2,
                    corrected=False,
                    uncorrectable_codes=[],
                ),
            )
        )
    )

    response = client.post(
        "/review", json={"question": " Review this ", "plan": submitted.model_dump()}
    )

    assert response.status_code == 200
    assert fake.calls[0][0] == "Review this"
    body = response.json()
    assert body["plan_review"]["final_validation"]["valid"] is False
    assert body["plan_review"]["final_validation"]["violations"][0]["code"] == "DOM-04"
    assert body["plan_review"]["max_correction_attempts"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {},
        {"question": "ok", "extra": 1},
        {"question": "ok", "plan": {}},
    ],
)
def test_invalid_review_requests_are_rejected(use_workflow, payload):
    fake = use_workflow(FakeWorkflow())

    assert client.post("/review", json=payload).status_code == 422
    assert fake.calls == []


def test_review_errors_hide_internal_details(use_workflow):
    error = ModelResponseError("The language model request failed.")
    error.__cause__ = RuntimeError("Traceback api_key=sk-not-real")
    use_workflow(FakeWorkflow(error=error))

    response = client.post("/review", json={"question": "Review"})

    assert response.status_code == 502
    assert "sk-not-real" not in response.text


def test_review_without_credentials_returns_503(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RESQIVO_CHROMA_DIR", str(tmp_path / "chroma"))

    response = client.post("/review", json={"question": "Review"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Question answering is not configured."}
