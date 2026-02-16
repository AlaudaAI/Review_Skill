"""Vercel serverless entry point — re-exports the FastAPI app."""

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402, F401
