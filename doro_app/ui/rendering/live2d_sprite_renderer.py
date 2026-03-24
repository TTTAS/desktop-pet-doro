"""Live2D sprite renderer — offscreen FBO rendering to QImage.

Renders a Live2D Cubism model (via live2d-py) into a QOpenGLFramebufferObject,
then converts the result to a QImage for compositing in the QPainter pipeline.

Requires: ``pip install live2d-py``
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtOpenGL

if TYPE_CHECKING:
    from ..viewmodels.doro_viewmodel import DoroViewModel

try:
    import live2d.v3 as live2d
    from OpenGL.GL import (
        GL_BLEND,
        GL_COLOR_BUFFER_BIT,
        GL_DEPTH_BUFFER_BIT,
        GL_ONE_MINUS_SRC_ALPHA,
        GL_SRC_ALPHA,
        glBlendFunc,
        glClearColor,
        glEnable,
        glViewport,
    )

    _LIVE2D_AVAILABLE = True
except ImportError:
    _LIVE2D_AVAILABLE = False

logger = logging.getLogger(__name__)

# FBO dimensions — large enough for crisp rendering; the final image is scaled
# by QPainter so this acts as the "render resolution".
_FBO_WIDTH = 512
_FBO_HEIGHT = 512

_FALLBACK_SIZE = QtCore.QSize(180, 180)


class Live2DSpriteRenderer:
    """SpriteRenderer implementation backed by live2d-py + offscreen FBO.

    Lifecycle
    ---------
    1. ``load_model(path)`` — call once with the ``.model3.json`` path.
    2. Every tick the owner calls ``update(dt)`` then ``render()``.
    3. ``dispose()`` — release GL resources (call before context destruction).
    """

    def __init__(self, view_model: DoroViewModel) -> None:
        self._view_model = view_model

        # GL resources (created lazily on first render)
        self._gl_context: QtGui.QOpenGLContext | None = None
        self._surface: QtGui.QOffscreenSurface | None = None
        self._fbo: QtOpenGL.QOpenGLFramebufferObject | None = None
        self._gl_initialised = False

        # Live2D model
        self._model: object | None = None  # live2d.v3.LAppModel
        self._model_path: str | None = None

        # Cached QImage from last draw
        self._current_image: QtGui.QImage | None = None
        self._model_size = QtCore.QSize(_FBO_WIDTH, _FBO_HEIGHT)

    # ── SpriteRenderer protocol ────────────────────────────────

    @property
    def renderer_type(self) -> str:  # noqa: D401
        """Renderer type identifier."""
        return "live2d"

    def render(
        self,
        painter: QtGui.QPainter,
        center: QtCore.QPointF,
        bob: float,
        scale: float,
    ) -> None:
        """Draw the current Live2D frame via QPainter."""
        image = self._current_image
        if image is None or image.isNull():
            return

        painter.save()
        painter.translate(center.x(), center.y() + bob)
        painter.scale(scale, scale)
        painter.translate(-image.width() / 2.0, -image.height() / 2.0)
        painter.drawImage(0, 0, image)
        painter.restore()

    def current_size(self) -> QtCore.QSize:
        if self._current_image and not self._current_image.isNull():
            return self._current_image.size()
        return _FALLBACK_SIZE

    def is_valid(self) -> bool:
        return self._model is not None and self._current_image is not None

    def current_pixmap(self) -> QtGui.QPixmap | None:
        if self._current_image and not self._current_image.isNull():
            return QtGui.QPixmap.fromImage(self._current_image)
        return None

    # ── Model management ───────────────────────────────────────

    def load_model(self, path: str | Path) -> bool:
        """Load a ``.model3.json`` file.  Returns True on success."""
        if not _LIVE2D_AVAILABLE:
            logger.error("live2d-py is not installed — cannot load Live2D model")
            return False

        path_str = str(path)
        self._ensure_gl_context()

        # Activate GL context before any Live2D calls
        if not self._make_current():
            return False

        try:
            # First-time global init
            if not self._gl_initialised:
                live2d.init()
                live2d.glInit()
                self._gl_initialised = True

            model = live2d.LAppModel()
            model.LoadModelJson(path_str)
            model.Resize(_FBO_WIDTH, _FBO_HEIGHT)

            self._model = model
            self._model_path = path_str
            self._model_size = QtCore.QSize(_FBO_WIDTH, _FBO_HEIGHT)
            logger.info("Live2D model loaded: %s", path_str)
            return True
        except Exception:
            logger.exception("Failed to load Live2D model: %s", path_str)
            self._model = None
            return False
        finally:
            self._done_current()

    def update(self, dt: float) -> None:
        """Advance model animation and render a new frame into the FBO."""
        if self._model is None or not _LIVE2D_AVAILABLE:
            return

        if not self._make_current():
            return

        try:
            self._ensure_fbo()

            # Bind FBO
            self._fbo.bind()

            # Clear to fully transparent
            glClearColor(0.0, 0.0, 0.0, 0.0)
            from OpenGL.GL import glClear

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glViewport(0, 0, _FBO_WIDTH, _FBO_HEIGHT)

            # Advance & draw
            self._model.Update()
            self._model.Draw()

            self._fbo.release()

            # Read FBO as QImage (Format_ARGB32_Premultiplied keeps alpha)
            image = self._fbo.toImage()
            if not image.isNull():
                # OpenGL Y-axis is flipped relative to Qt — mirror vertically
                image = image.mirrored(horizontally=False, vertically=True)
                # Ensure premultiplied alpha for correct QPainter compositing
                if image.format() != QtGui.QImage.Format.Format_ARGB32_Premultiplied:
                    image = image.convertToFormat(
                        QtGui.QImage.Format.Format_ARGB32_Premultiplied
                    )
                self._current_image = image

        except Exception:
            logger.exception("Error during Live2D frame update")
        finally:
            self._done_current()

    def dispose(self) -> None:
        """Release all GL / Live2D resources."""
        if self._make_current():
            try:
                if self._model is not None:
                    self._model = None
                if self._gl_initialised and _LIVE2D_AVAILABLE:
                    live2d.glRelease()
                    live2d.dispose()
                    self._gl_initialised = False
                self._fbo = None
            finally:
                self._done_current()

        self._current_image = None
        self._surface = None
        self._gl_context = None

    # ── Private helpers ────────────────────────────────────────

    def _ensure_gl_context(self) -> None:
        """Create (or reuse) the offscreen GL context + surface."""
        if self._gl_context is not None:
            return

        # Request an OpenGL context with alpha
        fmt = QtGui.QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        fmt.setVersion(3, 3)
        fmt.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.CoreProfile)

        ctx = QtGui.QOpenGLContext()
        ctx.setFormat(fmt)
        if not ctx.create():
            logger.error("Failed to create QOpenGLContext")
            return

        surface = QtGui.QOffscreenSurface()
        surface.setFormat(ctx.format())
        surface.create()
        if not surface.isValid():
            logger.error("Failed to create QOffscreenSurface")
            return

        self._gl_context = ctx
        self._surface = surface

    def _ensure_fbo(self) -> None:
        """Create (or recreate) the FBO at the current render size."""
        if self._fbo is not None:
            return
        fbo_fmt = QtOpenGL.QOpenGLFramebufferObjectFormat()
        fbo_fmt.setAttachment(
            QtOpenGL.QOpenGLFramebufferObject.Attachment.CombinedDepthStencil
        )
        fbo_fmt.setInternalTextureFormat(0x8058)  # GL_RGBA8
        self._fbo = QtOpenGL.QOpenGLFramebufferObject(
            QtCore.QSize(_FBO_WIDTH, _FBO_HEIGHT), fbo_fmt
        )
        if not self._fbo.isValid():
            logger.error("Failed to create FBO")
            self._fbo = None

    def _make_current(self) -> bool:
        """Activate the GL context.  Returns False on failure."""
        if self._gl_context is None or self._surface is None:
            self._ensure_gl_context()
        if self._gl_context is None or self._surface is None:
            return False
        return self._gl_context.makeCurrent(self._surface)

    def _done_current(self) -> None:
        if self._gl_context is not None:
            self._gl_context.doneCurrent()
