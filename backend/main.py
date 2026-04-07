#!/usr/bin/env python3
"""
PDFTextualization CLI
Usage: python main.py input.pdf [-o output.md] [--api-key KEY] [options]
"""

import asyncio
import sys
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from pipeline import run


def main() -> None:
    cfg = load_config()
    asyncio.run(run(cfg))


if __name__ == "__main__":
    main()
