"""Pytest global configuration and path setup."""

import sys
from pathlib import Path

# Add src directory to sys.path so modules under hr_chatbot can be imported directly
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
