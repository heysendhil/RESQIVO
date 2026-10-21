import copy
import json

import pytest

from app.rag.config import DEFAULT_MANIFEST_PATH
from app.rag.manifest import ManifestError, eligible_sources, load_manifest


def manifest_data() -> dict:
    return json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))


def write(tmp_path, data) -> object:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_repository_manifest_is_valid() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)

    assert len(manifest.sources) == 10


def test_only_who_01_is_eligible_for_ingestion() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)

    assert [source.id for source in eligible_sources(manifest)] == ["WHO-01"]


def test_duplicate_source_ids_are_rejected(tmp_path) -> None:
    data = manifest_data()
    data["sources"].append(copy.deepcopy(data["sources"][0]))

    with pytest.raises(ManifestError, match="Duplicate source IDs"):
        load_manifest(write(tmp_path, data))


def test_indexing_a_source_needing_permission_is_rejected(tmp_path) -> None:
    data = manifest_data()
    ndma = next(s for s in data["sources"] if s["id"] == "NDMA-03")
    ndma["include_in_index"] = True

    with pytest.raises(ManifestError, match="reuse must be 'open_licence'"):
        load_manifest(write(tmp_path, data))


def test_indexing_a_source_without_url_is_rejected(tmp_path) -> None:
    data = manifest_data()
    who = next(s for s in data["sources"] if s["id"] == "WHO-01")
    who["source_url"] = None

    with pytest.raises(ManifestError, match="official source_url is required"):
        load_manifest(write(tmp_path, data))


def test_missing_required_metadata_is_rejected(tmp_path) -> None:
    data = manifest_data()
    del data["sources"][0]["publisher"]

    with pytest.raises(ManifestError, match="publisher"):
        load_manifest(write(tmp_path, data))


@pytest.mark.parametrize("bad_id", ["SYN-001", "WHO-1", "who-01", "OTHER-01"])
def test_invalid_or_synthetic_source_ids_are_rejected(tmp_path, bad_id) -> None:
    data = manifest_data()
    data["sources"][0]["id"] = bad_id

    with pytest.raises(ManifestError):
        load_manifest(write(tmp_path, data))


def test_missing_and_malformed_manifests_are_reported(tmp_path) -> None:
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path / "missing.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid JSON"):
        load_manifest(bad)
