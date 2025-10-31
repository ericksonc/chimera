#!/usr/bin/env python3
"""Entry point script for Chimera CLI."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
