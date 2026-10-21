import json
import subprocess
import sys

import pytest

from app.rag.cli import main
from app.rag.config import DEFAULT_MANIFEST_PATH, DEFAULT_SYNTHETIC_FIXTURES_PATH
from app.rag.ingest import (
    SYNTHETIC_PUBLISHER,
    load_approved_documents,
    load_synthetic_documents,
)
from app.rag.manifest import load_manifest
from app.rag.store import IngestionError


def test_only_approved_sources_are_read(tmp_path):
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)
    (tmp_path / "WHO-01.txt").write_text("Approved text.", encoding="utf-8")
    (tmp_path / "NDMA-03.txt").write_text("Not approved.", encoding="utf-8")

    documents = load_approved_documents(manifest, tmp_path)

    assert [d.source_id for d in documents] == ["WHO-01"]
    who = next(s for s in manifest.sources if s.id == "WHO-01")
    assert documents[0].title == who.title
    assert documents[0].publisher == who.publisher
    assert documents[0].url == who.source_url
    assert documents[0].synthetic is False


def test_missing_approved_source_text_is_reported(tmp_path):
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)

    with pytest.raises(IngestionError, match="WHO-01 has no local text file"):
        load_approved_documents(manifest, tmp_path)


def test_empty_approved_source_text_is_reported(tmp_path):
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)
    (tmp_path / "WHO-01.txt").write_text("  \n", encoding="utf-8")

    with pytest.raises(IngestionError, match="empty"):
        load_approved_documents(manifest, tmp_path)


def test_synthetic_fixtures_are_clearly_labelled():
    documents = load_synthetic_documents(DEFAULT_SYNTHETIC_FIXTURES_PATH)

    assert len(documents) == 6
    for document in documents:
        assert document.synthetic is True
        assert document.source_id.startswith("SYN-")
        assert document.title.startswith("SYNTHETIC")
        assert document.publisher == SYNTHETIC_PUBLISHER
        assert document.url.startswith("urn:resqivo:synthetic:")
        for publisher in ("NDMA", "WHO", "UNDRR"):
            assert publisher not in document.publisher


def fixture_data() -> dict:
    return json.loads(DEFAULT_SYNTHETIC_FIXTURES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publisher", "World Health Organization"),
        ("title", "Drinking water storage"),
        ("url", "https://www.who.int/fake"),
        ("id", "WHO-01"),
    ],
)
def test_fixtures_imitating_real_sources_are_rejected(tmp_path, field, value):
    data = fixture_data()
    data["passages"][0][field] = value
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(IngestionError, match="Invalid synthetic fixture file"):
        load_synthetic_documents(path)


def test_fixture_file_must_declare_itself_synthetic(tmp_path):
    data = fixture_data()
    data["synthetic"] = False
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(IngestionError):
        load_synthetic_documents(path)


def test_duplicate_fixture_ids_are_rejected(tmp_path):
    data = fixture_data()
    data["passages"].append(dict(data["passages"][0]))
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(IngestionError, match="Duplicate synthetic passage IDs"):
        load_synthetic_documents(path)


def test_cli_builds_and_queries_a_synthetic_index(tmp_path, no_network, capsys):
    common = ["--chroma-dir", str(tmp_path / "idx"), "--collection", "cli_test"]

    assert (
        main([*common, "--embedding", "hashing", "build", "--corpus", "synthetic"]) == 0
    )
    assert "Indexed 6 document(s)" in capsys.readouterr().out

    assert (
        main([*common, "--embedding", "hashing", "query", "drinking water", "-k", "1"])
        == 0
    )
    output = capsys.readouterr().out
    assert "SYN-001 [SYNTHETIC - not official guidance]" in output


def test_cli_reports_errors_without_traceback(tmp_path, no_network, capsys):
    common = ["--chroma-dir", str(tmp_path / "idx"), "--collection", "empty_test"]

    assert main([*common, "--embedding", "hashing", "query", "water"]) == 1
    assert "Error: The knowledge base is empty." in capsys.readouterr().err


def test_api_startup_does_not_load_retrieval():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.main; "
            "print(any(m.startswith(('app.rag', 'chromadb')) for m in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False"
