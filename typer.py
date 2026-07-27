"""Backward-compatible launcher for Phonegeist from source.

This module allows running Phonegeist directly with `python typer.py` for development.
It is primarily used by start-phonegeist.bat for user-friendly startup.
"""

from __future__ import annotations

from phonegeist import main

if __name__ == "__main__":
    main()
