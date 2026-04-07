"""Assembles per-page texts into a final Markdown file."""

import re
from pathlib import Path


def _shift_headings(text: str) -> str:
    """Shift all Markdown headings in text down one level (# → ##, ## → ###, etc.)."""
    return re.sub(r'^(#{1,5})(\s)', r'#\1\2', text, flags=re.MULTILINE)


def build_markdown(
    pages: list[tuple[int, str]],
    heading_format: str = "# Page {n}",
) -> str:
    """
    pages: sorted list of (page_num, text)
    Page headings are H1; any headings inside the content are shifted down one level.
    Returns the full Markdown string.
    """
    parts = []
    for page_num, text in sorted(pages, key=lambda x: x[0]):
        heading = heading_format.format(n=page_num)
        if text.strip():
            parts.append(f"{heading}\n\n{_shift_headings(text.strip())}")
        else:
            parts.append(f"{heading}\n\n[OCR failed - no text recognized]")
    return "\n\n---\n\n".join(parts) + "\n"


def write_markdown(
    pages: list[tuple[int, str]],
    output_path: str,
    heading_format: str = "# Page {n}",
) -> None:
    content = build_markdown(pages, heading_format)
    Path(output_path).write_text(content, encoding="utf-8")
