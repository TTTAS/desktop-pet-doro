"""Application composition root - assembles and coordinates all components."""

from __future__ import annotations

from .ui.window import DoroWindow


class DoroApp:
    """
    Application composition root.

    Responsible for:
    - Creating the main window
    - Future: Assembling services and dependencies

    This class will grow as we extract more assembly logic from DoroWindow.__init__
    """

    def __init__(self, not_topmost: bool = False):
        """
        Initialize the application.

        Args:
            not_topmost: If True, window will not stay on top
        """
        # For now, just create the window
        # Future refactoring will move assembly logic here
        self.window = DoroWindow(not_topmost=not_topmost)

    def run(self):
        """Start the application by showing the main window."""
        self.window.show()
