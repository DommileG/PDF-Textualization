"""Configuration loading: CLI args > env vars > config.yaml > defaults."""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
_OPENAI_BASE_URL = "https://api.openai.com/v1/"


@dataclass
class OcrApiConfig:
    key: str = ""
    base_url: str = _GLM_BASE_URL


@dataclass
class LlmApiConfig:
    key: str = ""
    base_url: str = _GLM_BASE_URL
    provider: str = "glm"  # "glm" or "openai"


@dataclass
class OcrConfig:
    model: str = "glm-ocr"
    batch_size: int = 10


@dataclass
class LlmConfig:
    enabled: bool = True
    model: str = "glm-4.6"
    max_concurrent: int = 3
    prompt: str = (
        "清理以下OCR文本：去除页眉页脚页码，修复错误断行，保留段落结构，"
        "只输出正文内容，不要加任何说明。"
        "保留所有 [IMG:N]（N为数字）格式的图片占位符，原样输出，不得修改、移动或删除。"
    )


@dataclass
class OutputConfig:
    heading_format: str = "# Page {n}"


@dataclass
class AppConfig:
    ocr_api: OcrApiConfig = field(default_factory=OcrApiConfig)
    llm_api: LlmApiConfig = field(default_factory=LlmApiConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    input_pdf: str = ""
    output_md: str = ""
    page_range: Optional[tuple[int, int]] = None


def _load_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def load_config(args: Optional[list[str]] = None) -> AppConfig:
    parser = argparse.ArgumentParser(
        description="Convert a scanned PDF to Markdown via GLM OCR + LLM."
    )
    parser.add_argument("input_pdf", help="Path to input PDF file")
    parser.add_argument("-o", "--output", default="", help="Output .md file path")
    parser.add_argument("-c", "--config", default="config.yaml", help="Config YAML file")

    # OCR API
    parser.add_argument("--ocr-api-key", default="", help="OCR API key (GLM)")
    parser.add_argument("--ocr-base-url", default="", help="OCR API base URL")
    parser.add_argument("--ocr-model", default="", help="OCR model name")
    parser.add_argument("--batch-size", type=int, default=0, help="Pages per OCR batch")

    # LLM API
    parser.add_argument("--llm-api-key", default="", help="LLM API key")
    parser.add_argument("--llm-base-url", default="", help="LLM API base URL")
    parser.add_argument("--llm-provider", default="", help="LLM provider: glm or openai")
    parser.add_argument("--llm-model", default="", help="LLM model name")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM cleanup step")
    parser.add_argument("--llm-max-concurrent", type=int, default=0, help="Max concurrent LLM requests")

    parser.add_argument(
        "--pages", default="",
        help="Page range to process, e.g. '1-10' or '5' (1-indexed)",
    )

    parsed = parser.parse_args(args)
    yaml_data = _load_yaml(parsed.config)
    cfg = AppConfig()

    # ── OCR API ───────────────────────────────────────────────────────
    cfg.ocr_api.key = (
        parsed.ocr_api_key
        or os.environ.get("OCR_API_KEY", "")
        or yaml_data.get("ocr_api", {}).get("key", "")
    )
    cfg.ocr_api.base_url = (
        parsed.ocr_base_url
        or yaml_data.get("ocr_api", {}).get("base_url", cfg.ocr_api.base_url)
    )

    # ── LLM API ───────────────────────────────────────────────────────
    provider = (
        parsed.llm_provider
        or yaml_data.get("llm_api", {}).get("provider", "glm")
    ).lower()
    cfg.llm_api.provider = provider

    # Default base_url based on provider
    default_llm_base_url = _OPENAI_BASE_URL if provider == "openai" else _GLM_BASE_URL
    cfg.llm_api.base_url = (
        parsed.llm_base_url
        or yaml_data.get("llm_api", {}).get("base_url", default_llm_base_url)
    )
    cfg.llm_api.key = (
        parsed.llm_api_key
        or os.environ.get("LLM_API_KEY", "")
        or yaml_data.get("llm_api", {}).get("key", "")
        or cfg.ocr_api.key  # fallback to OCR key if not separately configured
    )

    # ── OCR config ────────────────────────────────────────────────────
    cfg.ocr.model = (
        parsed.ocr_model
        or yaml_data.get("ocr", {}).get("model", cfg.ocr.model)
    )
    cfg.ocr.batch_size = (
        parsed.batch_size
        or yaml_data.get("ocr", {}).get("batch_size", cfg.ocr.batch_size)
    )

    # ── LLM config ────────────────────────────────────────────────────
    cfg.llm.enabled = (
        not parsed.no_llm
        and yaml_data.get("llm", {}).get("enabled", cfg.llm.enabled)
    )
    cfg.llm.model = (
        parsed.llm_model
        or yaml_data.get("llm", {}).get("model", cfg.llm.model)
    )
    cfg.llm.max_concurrent = (
        parsed.llm_max_concurrent
        or yaml_data.get("llm", {}).get("max_concurrent", cfg.llm.max_concurrent)
    )
    cfg.llm.prompt = yaml_data.get("llm", {}).get("prompt", cfg.llm.prompt)

    # ── Output config ─────────────────────────────────────────────────
    cfg.output.heading_format = yaml_data.get("output", {}).get(
        "heading_format", cfg.output.heading_format
    )

    # ── Paths ─────────────────────────────────────────────────────────
    cfg.input_pdf = parsed.input_pdf
    cfg.output_md = parsed.output or str(Path(parsed.input_pdf).with_suffix(".md"))

    # ── Page range ────────────────────────────────────────────────────
    if parsed.pages:
        parts = parsed.pages.split("-")
        if len(parts) == 1:
            n = int(parts[0])
            cfg.page_range = (n, n)
        else:
            cfg.page_range = (int(parts[0]), int(parts[1]))

    # ── Validation ────────────────────────────────────────────────────
    if not cfg.ocr_api.key:
        print(
            '{"type":"error","message":"OCR API key not set. Use --ocr-api-key or config.yaml ocr_api.key"}',
            flush=True,
        )
        sys.exit(1)

    return cfg
