"""Process entry-point.

Run with:

    uvicorn backend.aml.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os

from .api import create_app

_origins = os.environ.get("AML_CORS_ORIGINS", "http://localhost:5173").split(",")

app = create_app(cors_origins=[o.strip() for o in _origins if o.strip()])
