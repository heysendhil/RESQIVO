"""PDF ingestion: extraction, metadata, chunking, indexing, retrieval, citations
and failure handling. PDFs are generated in temporary directories; nothing is
downloaded and no model is called."""

import dataclasses
import subprocess
import sys

import pytest
from langchain_core.messages import AIMessage
from pypdf import PageObject, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.qa.service import QuestionAnsweringService
from app.rag.chunking import chunk_document
from app.rag.cli import main
from app.rag.config import DEFAULT_MANIFEST_PATH
from app.rag.embeddings import EmbeddingModelUnavailableError, HashingEmbeddings
from app.rag.ingest import load_approved_documents
from app.rag.manifest import load_manifest
from app.rag.pdf import PdfExtractionError, extract_pdf_text, strip_page_numbers
from app.rag.store import IngestionError, KnowledgeStore

pytestmark = pytest.mark.usefixtures("no_network")

WHO_URL = next(
    source.source_url
    for source in load_manifest(DEFAULT_MANIFEST_PATH).sources
    if source.id == "WHO-01"
)

WATER = "Store drinking water in clean covered containers at every shelter."
TRIAGE = "Health teams triage casualties at the field hospital entrance."
TRIAGE_ANSWER = "Health teams triage casualties at the field hospital entrance [P1]."


def make_pdf(path, pages, user_password=None):
    """Write a PDF with one Helvetica text line per page; None is a page with no
    text, as a scanned image yields."""
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for text in pages:
        page = writer.add_blank_page(612, 792)
        if text is None:
            continue
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 10 Tf 40 700 Td ({escaped}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
    if user_password is not None:
        writer.encrypt(
            user_password=user_password, owner_password="owner", algorithm="RC4-128"
        )
    with open(path, "wb") as handle:
        writer.write(handle)
    return path


def words(count, prefix="word"):
    return " ".join(f"{prefix}{i}" for i in range(count))


def who_pdf(tmp_path, pages):
    local = tmp_path / "local"
    local.mkdir(exist_ok=True)
    make_pdf(local / "WHO-01.pdf", pages)
    return local


def load_who(local):
    return load_approved_documents(load_manifest(DEFAULT_MANIFEST_PATH), local)[0]


@pytest.fixture
def pdf_store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(HashingEmbeddings(), "pdf_test", tmp_path / "chroma")


# Extraction


def test_text_is_extracted_page_by_page(tmp_path):
    path = make_pdf(tmp_path / "doc.pdf", [WATER, TRIAGE])

    extracted = extract_pdf_text(path)

    assert extracted.page_count == 2
    assert [p.page_number for p in extracted.pages] == [1, 2]
    assert "clean covered containers" in extracted.pages[0].text
    assert "field hospital" in extracted.pages[1].text


def test_pages_without_text_are_skipped_not_indexed_as_empty(tmp_path):
    path = make_pdf(tmp_path / "doc.pdf", [WATER, None, TRIAGE])

    extracted = extract_pdf_text(path)

    assert extracted.page_count == 3
    assert [p.page_number for p in extracted.pages] == [1, 3]


def test_pdf_without_any_text_is_reported_as_possibly_scanned(tmp_path):
    path = make_pdf(tmp_path / "scan.pdf", [None, None])

    with pytest.raises(PdfExtractionError, match="OCR is not supported") as error:
        extract_pdf_text(path)
    assert "2 page(s)" in str(error.value)


def test_password_protected_pdf_is_rejected(tmp_path):
    path = make_pdf(tmp_path / "locked.pdf", [WATER], user_password="secret")

    with pytest.raises(PdfExtractionError, match="password protected"):
        extract_pdf_text(path)


def test_pdf_encrypted_with_an_empty_open_password_is_read(tmp_path):
    path = make_pdf(tmp_path / "permissions.pdf", [WATER], user_password="")

    extracted = extract_pdf_text(path)

    assert "covered containers" in extracted.pages[0].text


@pytest.mark.parametrize(
    "content",
    [b"This is not a PDF at all.", b"%PDF-1.7\n1 0 obj << /Type /Catalog"],
    ids=["not-a-pdf", "truncated"],
)
def test_invalid_pdf_is_rejected(tmp_path, content):
    path = tmp_path / "broken.pdf"
    path.write_bytes(content)

    with pytest.raises(PdfExtractionError, match="not a valid PDF"):
        extract_pdf_text(path)


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    with pytest.raises(PdfExtractionError, match="the file is empty"):
        extract_pdf_text(path)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(PdfExtractionError, match="cannot be read"):
        extract_pdf_text(tmp_path / "absent.pdf")


def test_extraction_failure_names_the_page(tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "doc.pdf", [WATER, TRIAGE])
    original = PageObject.extract_text
    calls = []

    def failing(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("corrupt content stream")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", failing)

    with pytest.raises(PdfExtractionError, match="failed on page 2"):
        extract_pdf_text(path)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("14\nAn EOC should be established.\n", "An EOC should be established."),
        ("viii\nABBREVIATIONS\n- 3 -", "ABBREVIATIONS"),
        ("Page 7\nAbout 190 million people\n2019", "About 190 million people\n2019"),
        (
            "Line one\n12 people waited\nLine three",
            "Line one\n12 people waited\nLine three",
        ),
    ],
)
def test_printed_page_numbers_are_not_indexed(text, expected):
    assert strip_page_numbers(text) == expected


def test_a_page_with_only_a_page_number_has_no_text(tmp_path):
    path = make_pdf(tmp_path / "doc.pdf", [WATER, "14"])

    extracted = extract_pdf_text(path)

    assert [p.page_number for p in extracted.pages] == [1]
    assert extracted.page_count == 2


def test_extraction_errors_are_ingestion_errors():
    assert issubclass(PdfExtractionError, IngestionError)


# Loading approved sources


def test_approved_source_is_loaded_from_its_pdf(tmp_path):
    local = who_pdf(tmp_path, [WATER, None, TRIAGE])
    make_pdf(local / "NDMA-03.pdf", ["Not approved for indexing."])

    documents = load_approved_documents(load_manifest(DEFAULT_MANIFEST_PATH), local)

    assert [d.source_id for d in documents] == ["WHO-01"]
    document = documents[0]
    assert document.url == WHO_URL
    assert document.publisher == "World Health Organization"
    assert document.source_file == "WHO-01.pdf"
    assert document.page_count == 3
    assert [p.page_number for p in document.pages] == [1, 3]
    assert document.pages_without_text() == [2]
    assert document.synthetic is False


def test_text_and_pdf_for_the_same_source_are_ambiguous(tmp_path):
    local = who_pdf(tmp_path, [WATER])
    (local / "WHO-01.txt").write_text("Prepared text.", encoding="utf-8")

    with pytest.raises(IngestionError, match="both WHO-01.txt and WHO-01.pdf"):
        load_who(local)


def test_missing_source_message_mentions_pdf(tmp_path):
    with pytest.raises(IngestionError, match="or PDF at"):
        load_who(tmp_path)


def test_scanned_approved_pdf_is_reported(tmp_path):
    local = who_pdf(tmp_path, [None])

    with pytest.raises(PdfExtractionError, match="WHO-01.pdf: no text"):
        load_who(local)


# Chunking and metadata


def test_chunks_never_span_pages_and_carry_page_metadata(tmp_path):
    document = load_who(who_pdf(tmp_path, [words(200, "a"), words(40, "b")]))

    chunks = chunk_document(document)

    assert [c.page for c in chunks] == [1, 1, 2]
    assert [c.chunk_id for c in chunks] == ["WHO-01:0000", "WHO-01:0001", "WHO-01:0002"]
    assert all(" b" not in f" {c.text}" for c in chunks[:2])
    metadata = chunks[2].metadata()
    assert metadata["page"] == 2
    assert metadata["source_file"] == "WHO-01.pdf"
    assert metadata["url"] == f"{WHO_URL}#page=2"
    assert metadata["source_id"] == "WHO-01"


def test_text_documents_keep_their_existing_metadata(tmp_path):
    (tmp_path / "WHO-01.txt").write_text(WATER, encoding="utf-8")

    metadata = chunk_document(load_who(tmp_path))[0].metadata()

    assert "page" not in metadata
    assert metadata["url"] == WHO_URL
    assert metadata["source_file"] == "WHO-01.txt"


# Indexing and retrieval


def test_retrieved_pdf_passage_cites_file_and_page(tmp_path, pdf_store):
    pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER, None, TRIAGE]))])

    passage = pdf_store.retrieve("field hospital triage casualties", k=1)[0]

    assert passage.source_id == "WHO-01"
    assert passage.page == 3
    assert passage.source_file == "WHO-01.pdf"
    assert passage.url == f"{WHO_URL}#page=3"
    assert "field hospital" in passage.text


def test_reindexing_the_same_pdf_does_not_duplicate_chunks(tmp_path, pdf_store):
    document = load_who(who_pdf(tmp_path, [words(200), TRIAGE]))

    first = pdf_store.ingest([document])
    second = pdf_store.ingest([document])

    assert first == second == pdf_store.count() == 3


def test_reindexing_a_shorter_pdf_removes_stale_chunks(tmp_path, pdf_store):
    pdf_store.ingest([load_who(who_pdf(tmp_path, [words(200), words(200), TRIAGE]))])
    assert pdf_store.count() == 5

    pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER]))])

    assert pdf_store.count() == 1
    assert pdf_store.retrieve("water", k=5)[0].page == 1


def test_sources_summary_lists_file_and_pages(tmp_path, pdf_store):
    pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER, None, TRIAGE]))])

    [source] = pdf_store.sources()

    assert source.source_id == "WHO-01"
    assert source.chunks == 2
    assert source.source_file == "WHO-01.pdf"
    assert source.pages == (1, 3)
    assert source.synthetic is False


class FailingEmbeddings(HashingEmbeddings):
    def embed_documents(self, texts):
        raise RuntimeError("embedding service down")


def test_embedding_failure_leaves_the_index_unchanged(tmp_path):
    directory = tmp_path / "chroma"
    document = load_who(who_pdf(tmp_path, [WATER]))
    KnowledgeStore(HashingEmbeddings(), "pdf_test", directory).ingest([document])
    failing = KnowledgeStore(FailingEmbeddings(), "pdf_test", directory)
    changed = dataclasses.replace(document, pages=document.pages[:0], text=TRIAGE)

    with pytest.raises(IngestionError, match="Embedding failed; the index was not"):
        failing.ingest([changed])

    assert failing.count() == 1
    assert "covered containers" in failing._collection.get()["documents"][0]


class UncachedEmbeddings(HashingEmbeddings):
    def embed_documents(self, texts):
        raise EmbeddingModelUnavailableError("model not cached")


def test_unavailable_embedding_model_keeps_its_actionable_error(tmp_path):
    store = KnowledgeStore(UncachedEmbeddings(), "pdf_test", tmp_path / "chroma")

    with pytest.raises(EmbeddingModelUnavailableError):
        store.ingest([load_who(who_pdf(tmp_path, [WATER]))])


def test_vector_database_failure_is_reported(tmp_path, pdf_store, monkeypatch):
    def failing_upsert(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pdf_store._collection, "upsert", failing_upsert)

    with pytest.raises(IngestionError, match="Writing to the vector database failed"):
        pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER]))])


# Grounded answers cite the page


class CitingModel:
    def invoke(self, messages, **kwargs):
        return AIMessage(
            content=TRIAGE_ANSWER,
            response_metadata={"finish_reason": "STOP"},
        )


def test_answer_citation_points_to_the_pdf_page(tmp_path, pdf_store):
    pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER, TRIAGE]))])
    service = QuestionAnsweringService(
        retriever=pdf_store, model=CitingModel(), top_k=1
    )

    result = service.answer("Where do health teams triage casualties?")

    assert result.status == "answered"
    [citation] = result.citations
    assert citation.source_id == "WHO-01"
    assert citation.url == f"{WHO_URL}#page=2"
    assert citation.synthetic is False


class InsufficientModel:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return AIMessage(
            content="INSUFFICIENT_EVIDENCE", response_metadata={"finish_reason": "STOP"}
        )


def test_empty_pdf_index_reports_an_empty_knowledge_base(pdf_store):
    model = InsufficientModel()

    result = QuestionAnsweringService(retriever=pdf_store, model=model).answer("Water?")

    assert (result.status, result.reason) == (
        "insufficient_evidence",
        "knowledge_base_empty",
    )
    assert result.citations == []
    assert model.calls == 0


def test_unsupported_question_returns_insufficient_evidence(tmp_path, pdf_store):
    pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER, TRIAGE]))])

    result = QuestionAnsweringService(
        retriever=pdf_store, model=InsufficientModel()
    ).answer("How many shelter beds are free right now?")

    assert result.status == "insufficient_evidence"
    assert result.reason == "model_reported_insufficient_evidence"
    assert result.answer is None
    assert result.citations == []


def test_distant_passages_are_never_shown_to_the_model(tmp_path, pdf_store):
    pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER]))])
    model = InsufficientModel()

    result = QuestionAnsweringService(
        retriever=pdf_store, model=model, max_distance=0.01
    ).answer("Volcanic ash aviation advisories")

    assert result.reason == "no_relevant_passages"
    assert model.calls == 0


def test_an_answer_citing_an_unprovided_page_is_withheld(tmp_path, pdf_store):
    pdf_store.ingest([load_who(who_pdf(tmp_path, [WATER, TRIAGE]))])

    class InventingModel:
        def invoke(self, messages, **kwargs):
            return AIMessage(
                content=f"{TRIAGE[:-1]} [P7].",
                response_metadata={"finish_reason": "STOP"},
            )

    result = QuestionAnsweringService(
        retriever=pdf_store, model=InventingModel(), top_k=1
    ).answer("Where do health teams triage casualties?")

    assert (result.status, result.reason) == (
        "insufficient_evidence",
        "answer_not_grounded",
    )
    assert result.citations == []


# Command line


def cli(tmp_path, *args):
    common = [
        "--chroma-dir",
        str(tmp_path / "idx"),
        "--collection",
        "cli_pdf",
        "--embedding",
        "hashing",
    ]
    return main([*common, *args])


def build(tmp_path, local):
    return cli(tmp_path, "build", "--corpus", "approved", "--local-dir", str(local))


def test_cli_indexes_lists_and_queries_a_pdf(tmp_path, capsys):
    local = who_pdf(tmp_path, [WATER, None, None, TRIAGE])

    assert build(tmp_path, local) == 0
    output = capsys.readouterr().out
    assert "WHO-01: WHO-01.pdf, text extracted from 2 of 4 page(s)." in output
    assert "no text on page(s) 2-3" in output
    assert "Indexed 1 document(s) as 2 chunk(s)." in output

    assert cli(tmp_path, "sources") == 0
    output = capsys.readouterr().out
    assert "WHO-01: 2 chunk(s)" in output
    assert "file: WHO-01.pdf" in output
    assert "pages: 1, 4" in output

    assert cli(tmp_path, "query", "field hospital triage", "-k", "1") == 0
    output = capsys.readouterr().out
    assert f"{WHO_URL}#page=4" in output
    assert "page 4 of WHO-01.pdf" in output


def test_cli_reports_an_invalid_pdf_without_traceback(tmp_path, capsys):
    local = tmp_path / "local"
    local.mkdir()
    (local / "WHO-01.pdf").write_bytes(b"not a pdf")

    assert build(tmp_path, local) == 1
    error = capsys.readouterr().err
    assert "Error: WHO-01.pdf: not a valid PDF file." in error
    assert "Traceback" not in error


def test_cli_sources_on_an_empty_collection(tmp_path, capsys):
    assert cli(tmp_path, "sources") == 0
    assert "The collection is empty" in capsys.readouterr().out


def test_api_startup_does_not_load_pypdf():
    result = subprocess.run(
        [sys.executable, "-c", "import sys, app.main; print('pypdf' in sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"
