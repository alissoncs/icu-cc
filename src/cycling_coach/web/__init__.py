"""Server-rendered web view over saved training plans.

The plan JSON is the source of truth; this package only reads it. Nothing here writes a
plan, so the app can never be the reason a plan is wrong — worst case it renders one
badly, and the file on disk is still correct.

Deliberately dependency-light at the browser end: no CDN, no bundler, no JavaScript
framework. The rider opens this on a phone at the trailhead, often on a bad connection or
none at all, so every byte is served from this repo.
"""

from __future__ import annotations

from .app import create_app

__all__ = ["create_app"]
