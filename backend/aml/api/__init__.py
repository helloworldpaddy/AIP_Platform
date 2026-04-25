"""FastAPI HTTP layer for the AML Investigation Agentic Platform.

The app factory `create_app()` is the single entry point for both
production (`uvicorn backend.aml.main:app`) and tests (importing the
factory and overriding dependencies).
"""

from .app import create_app

__all__ = ["create_app"]
