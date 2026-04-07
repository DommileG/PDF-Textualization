"""Main processing pipeline: PDF batches → GLM-OCR → parallel LLM cleanup → Markdown."""

import asyncio
import json
import re

from openai import AsyncOpenAI

_IMG_TAG_RE = re.compile(r'!\[\]\([^)]+\)')

from config import AppConfig
from image_downloader import localize_images
from llm_client import clean_text
from md_generator import write_markdown
from ocr_client import ocr_batch
from pdf_processor import iter_batches

def _emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)


async def _llm_clean_all(
    page_texts: list[tuple[int, str]],
    total: int,
    llm_client: AsyncOpenAI,
    cfg: AppConfig,
) -> list[tuple[int, str]]:
    """
    Sliding-window LLM cleanup: at most cfg.llm.max_concurrent requests in-flight.
    Each slot frees as soon as a request completes; the next queued page starts immediately.
    """
    semaphore = asyncio.Semaphore(cfg.llm.max_concurrent)

    async def clean_one(page_num: int, raw_text: str) -> tuple[int, str]:
        async with semaphore:
            # Replace image tags with [IMG:N] placeholders so LLM preserves positions
            images: list[str] = []

            def _to_placeholder(m: re.Match) -> str:
                images.append(m.group(0))
                return f"[IMG:{len(images) - 1}]"

            text_with_placeholders = _IMG_TAG_RE.sub(_to_placeholder, raw_text)

            if cfg.llm.enabled and text_with_placeholders.strip():
                cleaned = await clean_text(
                    llm_client, text_with_placeholders, cfg.llm.model, cfg.llm.prompt, page_num
                )
            else:
                cleaned = text_with_placeholders

            # Restore placeholders → actual image tags
            restored: set[int] = set()

            def _from_placeholder(m: re.Match) -> str:
                idx = int(m.group(1))
                restored.add(idx)
                return images[idx] if idx < len(images) else ""

            cleaned = re.sub(r'\[IMG:(\d+)\]', _from_placeholder, cleaned)

            # Append any images the LLM dropped (fallback: add to page end)
            dropped = [img for i, img in enumerate(images) if i not in restored]
            if dropped:
                cleaned = cleaned.rstrip() + '\n\n' + '\n\n'.join(dropped)

            _emit({"type": "progress", "page": page_num, "total": total, "status": "llm_done"})
            return (page_num, cleaned)

    return list(await asyncio.gather(*[clean_one(pn, rt) for pn, rt in page_texts]))


async def run(cfg: AppConfig) -> None:
    # OCR uses GLM's layout_parsing — separate key/url
    # LLM uses OpenAI-compatible /chat/completions — separate key/url/provider
    llm_client = AsyncOpenAI(
        api_key=cfg.llm_api.key,
        base_url=cfg.llm_api.base_url,
    )
    all_results: list[tuple[int, str]] = []

    for batch_start, batch_end, pdf_bytes, total in iter_batches(
        cfg.input_pdf,
        batch_size=cfg.ocr.batch_size,
        page_range=cfg.page_range,
    ):
        # Step 1: OCR — one API call for the entire batch
        page_texts = await ocr_batch(
            api_key=cfg.ocr_api.key,
            base_url=cfg.ocr_api.base_url,
            pdf_bytes=pdf_bytes,
            batch_start=batch_start,
            batch_end=batch_end,
        )
        for page_num, _ in page_texts:
            _emit({"type": "progress", "page": page_num, "total": total, "status": "ocr_done"})

        # Step 2: LLM cleanup — sliding window, max _LLM_MAX_CONCURRENT in-flight
        batch_cleaned = await _llm_clean_all(page_texts, total, llm_client, cfg)
        all_results.extend(batch_cleaned)

    write_markdown(all_results, cfg.output_md, cfg.output.heading_format)
    localize_images(cfg.output_md, cfg.input_pdf)
    _emit({"type": "done", "output": cfg.output_md, "pages": len(all_results)})
