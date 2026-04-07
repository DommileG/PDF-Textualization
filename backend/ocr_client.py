"""GLM-OCR client — sends a PDF batch to /layout_parsing, returns per-page text."""

import asyncio
import base64
import json

import httpx

_RETRY_DELAYS = [2, 5, 15]
_TIMEOUT = 180  # larger timeout for multi-page PDF batches


async def ocr_batch(
    api_key: str,
    base_url: str,
    pdf_bytes: bytes,
    batch_start: int,
    batch_end: int,
) -> list[tuple[int, str]]:
    """
    Send a sub-PDF (batch_start..batch_end pages) to GLM-OCR layout_parsing.
    Returns [(page_num, text), ...] in page order, using layout_details for
    per-page splitting.
    Falls back to a single entry with md_results if layout_details is absent.
    """
    b64 = base64.b64encode(pdf_bytes).decode()
    file_value = f"data:application/pdf;base64,{b64}"

    url = base_url.rstrip("/") + "/layout_parsing"
    payload = {"model": "glm-ocr", "file": file_value}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            return _parse_pages(data, batch_start, batch_end)

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = e.response.text[:300]
            last_err = e
            _emit_error(batch_start, f"OCR HTTP {status} (attempt {attempt + 1}): {body}")
            if status not in (429, 500, 502, 503, 504):
                break
        except Exception as e:
            last_err = e
            _emit_error(batch_start, f"OCR attempt {attempt + 1} failed: {e}")

    _emit_error(batch_start, f"OCR gave up after retries: {last_err}")
    # Return empty strings so the pipeline can continue
    return [(pn, "") for pn in range(batch_start, batch_end + 1)]


def _parse_pages(data: dict, batch_start: int, batch_end: int) -> list[tuple[int, str]]:
    """
    Extract per-page text from the layout_parsing response.
    layout_details is a list-of-lists: outer index = page offset within batch.
    Each inner list contains elements with {index, label, content, ...}.
    """
    layout_details: list[list[dict]] = data.get("layout_details") or []

    if layout_details:
        results = []
        for page_offset, elements in enumerate(layout_details):
            page_num = batch_start + page_offset
            if page_num > batch_end:
                break
            # Sort by element index, join all content fields
            sorted_elements = sorted(elements, key=lambda e: e.get("index", 0))
            parts = []
            for e in sorted_elements:
                if e.get("label") == "image":
                    content = e.get("content", "").strip()
                    if content.startswith("http"):
                        # API returned a direct URL
                        parts.append(f"![]({content})")
                    else:
                        # API returned bbox only — embed crop placeholder
                        bbox = e.get("bbox_2d") or e.get("bbox2d") or []
                        ocr_w = e.get("width", 0)
                        ocr_h = e.get("height", 0)
                        if bbox and ocr_w and ocr_h:
                            x1, y1, x2, y2 = bbox
                            parts.append(
                                f"![](pdf_crop:{page_num}:{ocr_w}:{ocr_h}:{x1},{y1},{x2},{y2})"
                            )
                else:
                    content = e.get("content", "").strip()
                    if content:
                        parts.append(content)
            page_text = "\n\n".join(parts)
            results.append((page_num, page_text))
        return results

    # Fallback: layout_details missing — use md_results as one block
    md_results: str = data.get("md_results") or ""
    _emit_error(
        batch_start,
        f"layout_details missing for pages {batch_start}-{batch_end}, "
        "using md_results as single block",
    )
    return [(batch_start, md_results.strip())]


def _emit_error(page_num: int, message: str) -> None:
    print(
        json.dumps({"type": "error", "page": page_num, "message": message}),
        flush=True,
    )
