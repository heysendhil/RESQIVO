"""Offline evaluation tracks, dataset validation, reporting and the CLI."""

import datetime
import json
import os
import subprocess
import sys

import pytest

from app.evaluation import drafting as drafting_module
from app.evaluation.dataset import (
    DEFAULT_DATASET_PATH,
    DEFAULT_PASSAGES_PATH,
    load_dataset,
)
from app.evaluation.drafting import run_drafting
from app.evaluation.grounding import run_grounding
from app.evaluation.metrics import Ratio
from app.evaluation.report import SkippedItem
from app.evaluation.retrieval import (
    real_source_retrieval_track,
    synthetic_retrieval_track,
)
from app.evaluation.runner import EvaluationReport, build_report, run_agentic_tracks
from app.evaluation.tool_calling import run_tool_calling
from app.rag.config import REPO_ROOT

pytestmark = pytest.mark.usefixtures("no_network")

FIXED_TIME = datetime.datetime(2026, 10, 22, 12, 0, tzinfo=datetime.UTC)


@pytest.fixture(scope="module")
def loaded():
    return load_dataset()


def _metric(track, name):
    value = track.metrics[name]
    return (value.numerator, value.denominator)


# Dataset ---------------------------------------------------------------------------


def test_dataset_is_synthetic_versioned_and_complete(loaded):
    data = loaded.dataset

    assert data.synthetic is True and data.version == 2
    assert len(loaded.sha256) == 64
    for cases in (data.grounding, data.drafting, data.tool_calling):
        assert {c.category for c in cases} == {
            "positive",
            "negative",
            "boundary",
            "adversarial",
        }
        assert all(c.success_criteria for c in cases)


def _write_dataset(tmp_path, mutate):
    data = json.loads(DEFAULT_DATASET_PATH.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["grounding"].append(dict(d["grounding"][0])),  # duplicate ID
        lambda d: d["grounding"][0]["retrieved"].append(
            {"passage": "SYN-999", "distance": 0.1}
        ),
        lambda d: d["grounding"][0].update(unexpected=True),
        lambda d: d["grounding"][0].update(category="happy"),
        lambda d: d["grounding"][0].update(id="G-1"),
        lambda d: d["grounding"][0].update(knowledge_base_empty=True),
        lambda d: d["drafting"][0].pop("success_criteria"),
        lambda d: d["tool_calling"][0].update(plan="missing_plan"),
        lambda d: d["tool_calling"][0].update(question=None),
        lambda d: d.update(synthetic=False),
        lambda d: d["grounding"][0]["retrieved"][0].update(distance=-1),
    ],
)
def test_invalid_records_are_rejected(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_dataset(_write_dataset(tmp_path, mutate))


def test_non_synthetic_passages_are_rejected(tmp_path):
    passages = json.loads(DEFAULT_PASSAGES_PATH.read_text(encoding="utf-8"))
    passages["synthetic"] = False
    path = tmp_path / "passages.json"
    path.write_text(json.dumps(passages), encoding="utf-8")

    with pytest.raises(ValueError, match="synthetic"):
        load_dataset(passages_path=path)


def test_empty_tracks_report_no_values(tmp_path):
    def empty(data):
        data["grounding"], data["drafting"], data["tool_calling"] = [], [], []

    loaded = load_dataset(_write_dataset(tmp_path, empty))

    for track in run_agentic_tracks(loaded):
        assert (track.cases, track.passed, track.failed) == (0, 0, 0)
        ratios = [m for m in track.metrics.values() if isinstance(m, Ratio)]
        assert ratios and all(m.value is None for m in ratios)


# Tracks ----------------------------------------------------------------------------


def test_grounding_track(loaded):
    track = run_grounding(loaded)

    assert track.failed == 0
    assert _metric(track, "citations_structurally_valid") == (6, 6)
    assert _metric(track, "unanswerable_declined") == (3, 3)
    assert _metric(track, "unsupported_answers_rejected") == (9, 9)
    assert _metric(track, "rejected_by_expected_rule") == (9, 9)
    assert track.metrics["grounding_rejections_by_rule"] == {
        "low_lexical_support": 1,
        "number_not_in_cited_evidence": 2,
        "suspicious_instruction": 2,
        "uncited_sentence": 2,
        "unknown_label": 2,
    }
    assert track.skipped[0].item.startswith("semantic_support")


def test_drafting_track(loaded):
    track = run_drafting(loaded)

    assert track.failed == 0
    assert _metric(track, "drafts_produced") == (12, 16)
    assert _metric(track, "inventory_and_capacity_preserved") == (12, 12)
    assert _metric(track, "validator_agreement") == (12, 12)
    assert _metric(track, "insufficient_information_handled") == (3, 3)
    assert _metric(track, "no_evidence_handled") == (2, 2)
    assert track.metrics["unresolved_violations_total"] == 7


def test_tool_calling_track(loaded):
    track = run_tool_calling(loaded)

    assert track.failed == 0
    assert track.metrics["unauthorized_tools_executed"] == 0
    assert _metric(track, "expected_unauthorized_rejected") == (5, 5)
    assert _metric(track, "tool_call_limit_enforced") == (1, 1)
    assert _metric(track, "prompt_injection_resisted") == (2, 2)
    assert _metric(track, "bound_tools_match_stage") == (17, 17)


def test_failed_cases_are_reported_not_dropped(tmp_path):
    def wrong_expectation(data):
        data["drafting"][0]["expected"]["status"] = "draft_invalid"

    track = run_drafting(load_dataset(_write_dataset(tmp_path, wrong_expectation)))

    (failed,) = [r for r in track.results if not r.passed]
    assert failed.id == "DRF-001"
    assert failed.failures == [
        "status: expected 'draft_invalid', observed 'draft_valid'"
    ]
    assert (track.cases, track.failed) == (16, 1)


def test_unexpected_exceptions_fail_the_case(loaded, monkeypatch):
    def broken(self, request, request_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(drafting_module.DraftPlanWorkflow, "run", broken)

    track = run_drafting(loaded)

    assert track.failed == track.cases
    assert all(r.observed["error"] == "unexpected:RuntimeError" for r in track.results)


# Retrieval tracks --------------------------------------------------------------------


def test_synthetic_retrieval_track_uses_existing_script_rows():
    run = {
        "corpus_passages": 6,
        "queries_detail": [
            {"id": "L01", "type": "lexical", "rank": 1},
            {"id": "P01", "type": "paraphrase", "rank": 6},
        ],
    }
    skipped = [SkippedItem(item="provider onnx-minilm", reason="not cached")]

    track = synthetic_retrieval_track({"hashing": run}, skipped, {"version": 1})

    overall = track.metrics["hashing"]["overall"]
    assert overall["recall_at"]["5"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert overall["missed_within_cutoff"]["5"] == ["P01"]
    assert [r.passed for r in track.results] == [True, False]
    assert track.synthetic is True and track.skipped == skipped


def test_real_source_track_is_separate_and_skippable():
    skipped = [SkippedItem(item="WHO-01", reason="Not requested.")]

    track = real_source_retrieval_track({}, skipped)

    assert track.status == "skipped"
    assert track.synthetic is False
    assert track.cases == 0


# Report ------------------------------------------------------------------------------


def test_report_schema_and_reproducibility(loaded):
    first = build_report(loaded, run_agentic_tracks(loaded), now=FIXED_TIME)
    second = build_report(loaded, run_agentic_tracks(loaded), now=FIXED_TIME)

    assert first.model_dump_json() == second.model_dump_json()
    parsed = EvaluationReport.model_validate_json(first.model_dump_json())
    assert parsed.mode == "offline"
    assert parsed.live_model_calls == 0
    assert parsed.datasets["agentic"]["version"] == 2
    assert parsed.summary["grounding"] == {
        "status": "completed",
        "synthetic": True,
        "cases": 19,
        "passed": 19,
        "failed": 0,
        "skipped": 1,
    }
    assert any("semantic_support" in s.item for s in parsed.skipped)
    assert any("operational safety" in text for text in parsed.limitations)


# CLI and offline behaviour --------------------------------------------------


def test_cli_runs_offline_without_credentials_or_models(tmp_path):
    output = tmp_path / "report.json"
    env = {
        **os.environ,
        "GOOGLE_API_KEY": "sk-must-not-be-used",
        "HOME": str(tmp_path),  # no cached embedding models
        "LANGSMITH_TRACING": "true",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_evaluation.py"),
            "--providers",
            "hashing,onnx-minilm",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT / "backend",
        timeout=300,
    )

    # Synthetic retrieval queries ranked outside the top 5 count as failed cases.
    assert result.returncode == 1, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["network"] == "blocked"
    assert report["live_model_calls"] == 0
    assert report["tracks"]["retrieval_synthetic"]["status"] == "completed"
    assert "hashing" in report["tracks"]["retrieval_synthetic"]["metrics"]
    skipped = {s["item"] for s in report["skipped"]}
    assert "retrieval_synthetic: provider onnx-minilm" in skipped
    assert "retrieval_real_source: WHO-01" in skipped
    assert not (tmp_path / ".cache" / "chroma" / "onnx_models").exists()
    assert "sk-must-not-be-used" not in output.read_text() + result.stderr


def test_cli_rejects_unknown_provider():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_evaluation.py"),
            "--providers",
            "x",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT / "backend",
    )

    assert result.returncode == 2


def test_api_startup_does_not_load_the_evaluation_package():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.main; "
            "print(any(m.startswith('app.evaluation') for m in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False"
