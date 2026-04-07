"""Localize images in a Markdown file: download URLs or crop from PDF, rewrite to relative paths."""

import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

_IMG_URL_RE = re.compile(r'!\[\]\((https?://[^)]+)\)')
# Format: ![](pdf_crop:PAGE_1IDX:OCR_W:OCR_H:x1,y1,x2,y2)
_IMG_CROP_RE = re.compile(
    r'!\[\]\(pdf_crop:(\d+):(\d+):(\d+):(\d+),(\d+),(\d+),(\d+)\)'
)


def localize_images(md_path: str, pdf_path: str = "") -> int:
    """
    Replace all image references in *md_path* with local files:
    - ![](https://...) → download to {stem}_images/img_N.ext
    - ![](pdf_crop:...) → crop region from *pdf_path* using PyMuPDF

    Returns number of images successfully saved.
    """
    md_file = Path(md_path)
    content = md_file.read_text(encoding="utf-8")

    has_urls = bool(_IMG_URL_RE.search(content))
    has_crops = bool(_IMG_CROP_RE.search(content))

    if not has_urls and not has_crops:
        return 0

    img_dir = md_file.parent / f"{md_file.stem}_images"
    img_dir.mkdir(exist_ok=True)

    replacements: dict[str, str] = {}
    count = 0

    # ── URL images ────────────────────────────────────────────────────────────
    if has_urls:
        for idx, url in enumerate(dict.fromkeys(_IMG_URL_RE.findall(content))):
            ext = _guess_ext(url)
            local_name = f"img_{idx}{ext}"
            local_path = img_dir / local_name
            try:
                urllib.request.urlretrieve(url, local_path)
                replacements[f"![]({url})"] = f"![]({img_dir.name}/{local_name})"
                count += 1
            except Exception as e:
                _log_error(0, f"Image download failed ({url[:60]}): {e}")

    # ── PDF crop images ───────────────────────────────────────────────────────
    if has_crops and pdf_path:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            _log_error(0, "PyMuPDF not installed — run: pip install pymupdf")
            fitz = None  # type: ignore

        if fitz is not None:
            doc = fitz.open(pdf_path)
            page_crop_counts: dict[int, int] = {}
            for m in _IMG_CROP_RE.finditer(content):
                placeholder = m.group(0)
                if placeholder in replacements:
                    continue
                page_num  = int(m.group(1))   # 1-indexed
                ocr_w     = int(m.group(2))
                ocr_h     = int(m.group(3))
                x1, y1, x2, y2 = int(m.group(4)), int(m.group(5)), int(m.group(6)), int(m.group(7))
                try:
                    page = doc[page_num - 1]
                    pw, ph = page.rect.width, page.rect.height  # PDF points
                    pad = 10  # points padding to avoid clipping edges
                    clip = fitz.Rect(
                        max(0, x1 * pw / ocr_w - pad),
                        max(0, y1 * ph / ocr_h - pad),
                        min(pw, x2 * pw / ocr_w + pad),
                        min(ph, y2 * ph / ocr_h + pad),
                    )
                    pix = page.get_pixmap(clip=clip, dpi=150)
                    # Per-page subfolder
                    page_dir = img_dir / f"page_{page_num}"
                    page_dir.mkdir(exist_ok=True)
                    crop_idx = page_crop_counts.get(page_num, 0)
                    local_name = f"crop_{crop_idx}.png"
                    local_path = page_dir / local_name
                    pix.save(str(local_path))
                    replacements[placeholder] = f"![]({img_dir.name}/page_{page_num}/{local_name})"
                    page_crop_counts[page_num] = crop_idx + 1
                    count += 1
                except Exception as e:
                    _log_error(page_num, f"PDF crop failed (page {page_num}, bbox {x1},{y1},{x2},{y2}): {e}")
            doc.close()

    # ── Rewrite markdown ──────────────────────────────────────────────────────
    for old, new in replacements.items():
        content = content.replace(old, new)
    md_file.write_text(content, encoding="utf-8")
    return count


def _guess_ext(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"} else ".png"


def _log_error(page_num: int, message: str) -> None:
    print(json.dumps({"type": "error", "page": page_num, "message": message}), flush=True)


# ── Legacy alias ──────────────────────────────────────────────────────────────
def download_images(md_path: str) -> int:
    return localize_images(md_path)
