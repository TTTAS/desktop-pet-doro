"""Protocol defining the contract for sprite renderers."""

from __future__ import annotations

from typing import Protocol

from PySide6 import QtCore, QtGui


class SpriteRenderer(Protocol):
    """
    Abstract interface for rendering a character sprite.

    Implementations:
    - GifSpriteRenderer: QMovie-based GIF playback + fallback vector sprite
    - (future) SpineSpriteRenderer: spine-c CFFI + QPainter blit
    """

    @property
    def renderer_type(self) -> str:
        """Return the renderer type identifier (e.g. ``"gif"``, ``"spine"``)."""
        ...

    def render(
        self,
        painter: QtGui.QPainter,
        center: QtCore.QPointF,
        bob: float,
        scale: float,
    ) -> None:
        """Draw the sprite centred at *center* with animation offsets."""
        ...

    def current_size(self) -> QtCore.QSize:
        """Return the current sprite dimensions (used for layout)."""
        ...

    def is_valid(self) -> bool:
        """Return True if the renderer has content to display."""
        ...

    def current_pixmap(self) -> QtGui.QPixmap | None:
        """Return a representative frame as QPixmap (e.g. for menu avatar)."""
        ...
