"""Vercel serverless entry point.

Vercel's Python runtime imports `app` from this module and serves it as an ASGI
app. We add the backend root to sys.path so `from app.main import app` resolves
the same way it does when running uvicorn locally. `vercel.json` rewrites every
path here.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.main import app  # noqa: E402  (must follow the sys.path tweak)

__all__ = ["app"]
