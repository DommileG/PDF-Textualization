"""LLM text cleanup client — removes OCR noise, fixes line breaks."""

import asyncio
import json

from openai import AsyncOpenAI

_RETRY_DELAYS = [20, 40, 60]  # 429 rate-limit window is ~60s; short delays are useless


async def clean_text(
    client: AsyncOpenAI,
    raw_text: str,
    model: str,
    system_prompt: str,
    page_num: int,
) -> str:
    """Ask LLM to clean OCR text. Falls back to raw_text on failure."""
    if not raw_text.strip():
        return raw_text

    last_err = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            _emit_error(page_num, f"LLM rate-limited, waiting {delay}s before retry {attempt}...")
            await asyncio.sleep(delay)
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_text},
                ],
                max_tokens=4096,
            )
            result = resp.choices[0].message.content or ""
            return result.strip()
        except Exception as e:
            last_err = e
            _emit_error(page_num, f"LLM attempt {attempt + 1} failed: {e}")

    _emit_error(page_num, f"LLM cleanup skipped (fallback to raw OCR): {last_err}")
    return raw_text


def _emit_error(page_num: int, message: str) -> None:
    print(
        json.dumps({"type": "error", "page": page_num, "message": message}),
        flush=True,
    )
