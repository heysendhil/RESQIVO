"""Page-by-page text extraction from local PDF files, using pypdf.

There is no OCR: a page whose text cannot be extracted (typically a scanned
image) is reported, never indexed as empty text. pypdf is imported on first use,
so the API never loads it.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.rag.documents import PageText
from app.rag.store import IngestionError

# Bounds memory and time for a single local file; far above any manifest source.
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 2000


# A line holding only a printed page number ("14", "viii", "- 3 -", "Page 7").
_PAGE_NUMBER_LINE = re.compile(
    # At most three digits, so a year alone on a line ("2019") is kept.
    r"^\s*(?:page\s+)?[-–—]?\s*(?:\d{1,3}|[ivxlcdm]{1,7})\s*[-–—]?\s*$",
    re.IGNORECASE,
)


def strip_page_numbers(text: str) -> str:
    """Remove printed page numbers from the first and last lines of a page, so
    that they are not indexed as passage text. Other lines are kept as they are."""
    lines = text.splitlines()
    while lines and (not lines[0].strip() or _PAGE_NUMBER_LINE.match(lines[0])):
        lines.pop(0)
    while lines and (not lines[-1].strip() or _PAGE_NUMBER_LINE.match(lines[-1])):
        lines.pop()
    return "\n".join(lines)


class PdfExtractionError(IngestionError):
    """A PDF could not be read, or yielded no text."""


@dataclass(frozen=True)
class PdfText:
    pages: tuple[PageText, ...]
    page_count: int


def extract_pdf_text(path: Path) -> PdfText:
    """Extract the text of every page. Raises PdfExtractionError if the file is
    missing, too large, not a valid PDF, password protected, or has no
    extractable text on any page."""
    from pypdf import PdfReader
    from pypdf.errors import DependencyError

    name = path.name
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PdfExtractionError(f"{name}: the file cannot be read.") from exc
    if size == 0:
        raise PdfExtractionError(f"{name}: the file is empty.")
    if size > MAX_PDF_BYTES:
        raise PdfExtractionError(
            f"{name}: the file is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB."
        )

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            # Many published PDFs are encrypted only to set permissions, with an
            # empty open password; those are readable. Anything else is refused.
            try:
                opened = reader.decrypt("")
            except (DependencyError, NotImplementedError) as exc:
                raise PdfExtractionError(
                    f"{name}: the PDF is encrypted with an unsupported method."
                ) from exc
            if not opened:
                raise PdfExtractionError(
                    f"{name}: the PDF is password protected. Provide an "
                    "unprotected copy of the official document."
                )
        page_count = len(reader.pages)
    except PdfExtractionError:
        raise
    # Malformed files raise a wide range of exception types inside pypdf.
    except Exception as exc:
        raise PdfExtractionError(f"{name}: not a valid PDF file.") from exc

    if page_count == 0:
        raise PdfExtractionError(f"{name}: the PDF has no pages.")
    if page_count > MAX_PDF_PAGES:
        raise PdfExtractionError(
            f"{name}: the PDF has more than {MAX_PDF_PAGES} pages."
        )

    pages = []
    for number, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            # A malformed page stops the document: a silent gap could drop
            # guidance that citations would then appear to cover.
            raise PdfExtractionError(
                f"{name}: text extraction failed on page {number}."
            ) from exc
        text = strip_page_numbers(text)
        if text.strip():
            pages.append(PageText(page_number=number, text=text))

    if not pages:
        raise PdfExtractionError(
            f"{name}: no text could be extracted from any of its {page_count} "
            "page(s). It may be a scanned image; OCR is not supported. Provide a "
            "text-based PDF or a prepared .txt file."
        )
    return PdfText(pages=tuple(pages), page_count=page_count)
