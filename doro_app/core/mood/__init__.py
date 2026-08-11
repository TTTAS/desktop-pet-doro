"""Doro's dual-axis emotion model (mood + affection).

See :mod:`doro_app.core.mood.models` for the design notes.
"""

from .models import MoodEvent, MoodState

__all__ = ["MoodEvent", "MoodState"]
