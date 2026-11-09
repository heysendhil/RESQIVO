"""Offline components for concurrency tests and benchmarks.

The fake model's replies are derived from each request's own prompt, so a
response can be checked against the request that produced it: answers echo the
request's passage, drafts allocate the request's own stock, and corrections
clamp the request's own allocations. An optional fixed delay simulates a slow
model; it says nothing about real model latency.

install_offline_overrides() replaces the per-request service and workflow
factories in app.main, so every request builds fresh components, as in
production. No network, credentials, model downloads or persistent index.
"""

import html
import json
import re
import time
from typing import Any

from langchain_core.messages import AIMessage

from app.qa.prompt import SYSTEM_PROMPT
from app.qa.service import QuestionAnsweringService
from app.rag.store import RetrievalError, RetrievedPassage
from app.workflow.correction import CORRECTION_SYSTEM_PROMPT
from app.workflow.drafting import DRAFT_SYSTEM_PROMPT, DraftPlanWorkflow
from app.workflow.graph import ReviewWorkflow
from app.workflow.tools import make_search_guidance_tool, make_validate_plan_tool

_PASSAGE = re.compile(
    r'<retrieved_passage label="(P\d+)"[^>]*>\n(.*?)\n</retrieved_passage>', re.S
)
_SECTION = re.compile(r"<(\w+)>\n(.*?)\n</\1>", re.S)
_TOKEN = re.compile(r"\b(case-\d+)\b")
FAIL_MARKER = "FAIL-RETRIEVAL"


def _sections(text: str) -> dict[str, Any]:
    return {
        name: json.loads(html.unescape(body)) for name, body in _SECTION.findall(text)
    }


class DeterministicModel:
    """Content-driven fake chat model. One instance per request."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay = delay_seconds
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        system, user = messages[0].content, messages[-1].content
        if system == SYSTEM_PROMPT:
            label, text = _PASSAGE.search(user).groups()
            sentence = html.unescape(text).split(". ")[0].rstrip(".")
            return AIMessage(content=f"{sentence} [{label}].")
        if system == DRAFT_SYSTEM_PROMPT:
            data = _sections(user)
            shelter = data["shelters"][0]["shelter_id"]
            allocations = [
                {
                    "allocation_id": f"a-{i}",
                    "resource_id": r["resource_id"],
                    "destination_id": shelter,
                    "quantity_allocated": r["quantity_available"],
                }
                for i, r in enumerate(data["resources"])
            ]
            return AIMessage(content=json.dumps({"allocations": allocations}))
        if system == CORRECTION_SYSTEM_PROMPT:
            plan = _sections(user)["plan"]
            stock = {
                r["resource_id"]: r["quantity_available"] for r in plan["resources"]
            }
            allocations = [
                {
                    **a,
                    "quantity_allocated": min(
                        a["quantity_allocated"], stock.get(a["resource_id"], 0)
                    ),
                }
                for a in plan["allocations"]
            ]
            return AIMessage(content=json.dumps({"allocations": allocations}))
        raise RuntimeError("Unexpected prompt.")


class EchoRetriever:
    """Returns one synthetic passage naming the query's case token, so evidence
    from one request is recognisable in another. Queries containing
    FAIL_MARKER raise a retrieval failure."""

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedPassage]:
        if FAIL_MARKER in query:
            raise RetrievalError("Scripted retrieval failure.")
        token = (_TOKEN.search(query) or [None, "general"])[1]
        return [
            RetrievedPassage(
                text=(
                    f"Shelter teams store drinking water for {token} "
                    "in covered containers."
                ),
                source_id="SYN-LOAD",
                title="SYNTHETIC: load-test passage",
                publisher="RESQIVO synthetic test fixture (not an official source)",
                url="urn:resqivo:synthetic:SYN-LOAD",
                chunk_id="SYN-LOAD:0000",
                chunk_index=0,
                synthetic=True,
                distance=0.2,
            )
        ]


def _components(delay: float):
    retriever, model = EchoRetriever(), DeterministicModel(delay)
    service = QuestionAnsweringService(retriever, model)
    tools = {
        "search_tool": make_search_guidance_tool(retriever),
        "validate_tool": make_validate_plan_tool(),
        "answer_service": service,
        "model": model,
    }
    return service, tools


def install_offline_overrides(app, delay_seconds: float = 0.0) -> None:
    """Make /answer, /review and /draft-plan use fresh offline components for
    every request."""
    from app.main import get_draft_workflow, get_qa_service, get_review_workflow

    app.dependency_overrides[get_qa_service] = lambda: _components(delay_seconds)[0]
    app.dependency_overrides[get_review_workflow] = lambda: ReviewWorkflow(
        **_components(delay_seconds)[1]
    )
    app.dependency_overrides[get_draft_workflow] = lambda: DraftPlanWorkflow(
        **_components(delay_seconds)[1]
    )


# Synthetic request bodies ------------------------------------------------------


def plan_body(quantity: int, stock: int = 1000) -> dict[str, Any]:
    return {
        "resources": [
            {
                "resource_id": "water-001",
                "name": "Water",
                "resource_type": "drinking_water",
                "quantity_available": stock,
                "unit": "litres",
                "location": "Depot",
            }
        ],
        "allocations": [
            {
                "allocation_id": "alloc-001",
                "resource_id": "water-001",
                "destination_id": "shelter-001",
                "quantity_allocated": quantity,
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


def draft_body(stock: int) -> dict[str, Any]:
    plan = plan_body(0, stock)
    return {
        "scenario": {
            "scenario_id": "LOAD-SCN",
            "name": "Synthetic load scenario",
            "disaster_type": "flood",
            "severity": "high",
            "affected_population": 100,
            "location": "Simulated Zone",
            "description": "Synthetic load-test scenario.",
        },
        "resources": plan["resources"],
        "shelters": plan["shelters"],
    }
