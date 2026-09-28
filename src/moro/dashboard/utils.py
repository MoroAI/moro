"""
MoroAI Dashboard Utility Functions.

Provides filesystem and database path helpers for the dashboard subsystem.
"""

from __future__ import annotations

from pathlib import Path

from moro.core.project import find_project_root


def get_project_root() -> Path:
    """Get the current project root directory."""
    found = find_project_root()
    return found if found is not None else Path.cwd()


def get_state_db_path() -> Path:
    """Get the path to the state database."""
    return get_project_root() / ".moro" / "state.db"


def get_analytics_db_path() -> Path:
    """Get the path to the analytics database."""
    return get_project_root() / ".moro" / "analytics.db"
