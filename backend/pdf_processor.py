"""PDF → sub-PDF bytes using PyMuPDF (batch extraction, no image rendering)."""

from typing import Iterator

import fitz  # pymupdf


def iter_batches(
    pdf_path: str,
    batch_size: int = 10,
    page_range: tuple[int, int] | None = None,
) -> Iterator[tuple[int, int, bytes, int]]:
    """
    Yield (batch_start, batch_end, sub_pdf_bytes, total_pages).
    batch_start / batch_end are 1-indexed, inclusive.
    sub_pdf_bytes is a minimal in-memory PDF containing only those pages.
    """
    doc = fitz.open(pdf_path)
    total = len(doc)

    start = 1
    end = total
    if page_range:
        start = max(1, page_range[0])
        end = min(total, page_range[1])

    for batch_start in range(start, end + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, end)

        sub_doc = fitz.open()
        # insert_pdf uses 0-indexed from_page / to_page
        sub_doc.insert_pdf(doc, from_page=batch_start - 1, to_page=batch_end - 1)
        pdf_bytes = sub_doc.tobytes()
        sub_doc.close()

        yield (batch_start, batch_end, pdf_bytes, total)

    doc.close()
