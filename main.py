"""Convenience entry point for the QDII ETF Premium Monitor.

Usage:
    python main.py [--once] [--config CONFIG_PATH]
"""

import sys

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
