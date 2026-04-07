#!/usr/bin/env python3
"""
Quick OCR test: send first batch of book.pdf to GLM-OCR and save raw JSON.
Usage: python3 test_ocr.py
Output: ocr_raw.json
"""

import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx
import yaml

PDF_PATH = "book.pdf"
OUTPUT_JSON = "ocr_raw.json"
BATCH_PAGES = 3  # how many pages to send


def load_api_key() -> str:
    try:
        with open("config.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        key = data.get("ocr_api", {}).get("key", "")
        if key:
            return key
    except FileNotFoundError:
        pass
    print("ERROR: could not read ocr_api.key from config.yaml")
    sys.exit(1)


async def main():
    api_key = load_api_key()

    pdf_bytes = Path(PDF_PATH).read_bytes()
    # Only encode first BATCH_PAGES pages — use full file for simplicity
    b64 = base64.b64encode(pdf_bytes).decode()

    payload = {"model": "glm-ocr", "file": f"data:application/pdf;base64,{b64}"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"Sending {PDF_PATH} to GLM-OCR ...")
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            "https://open.bigmodel.cn/api/paas/v4/layout_parsing",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    # Save full raw JSON
    Path(OUTPUT_JSON).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw JSON saved to {OUTPUT_JSON}")

    # Print top-level keys so we can see field naming convention
    print("\n=== Top-level keys ===")
    for k in data.keys():
        v = data[k]
        if isinstance(v, list):
            print(f"  {k!r}: list[{len(v)}]")
        elif isinstance(v, str):
            print(f"  {k!r}: str (first 80 chars): {v[:80]!r}")
        else:
            print(f"  {k!r}: {type(v).__name__} = {str(v)[:80]}")

    # Check which variant of layout_details key exists
    print("\n=== Key name check ===")
    for candidate in ("layoutDetails", "layout_details", "mdResults", "md_results"):
        val = data.get(candidate)
        if val is not None:
            print(f"  FOUND: {candidate!r}")
        else:
            print(f"  missing: {candidate!r}")

    # Count image elements
    layout = data.get("layoutDetails") or data.get("layout_details") or []
    image_count = sum(
        1 for page in layout for e in page if e.get("label") == "image"
    )
    print(f"\n=== Image elements found: {image_count} ===")


if __name__ == "__main__":
    asyncio.run(main())
