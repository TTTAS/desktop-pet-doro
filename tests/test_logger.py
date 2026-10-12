"""Module loggers under ``doro_app`` must reach the log file (heartbeat decisions etc.)."""

import logging

from doro_app.utils.logger import get_logger


def test_package_module_info_lines_reach_the_doro_handlers():
    get_logger(__name__)
    module = logging.getLogger("doro_app.core.heartbeat.controller")
    assert module.isEnabledFor(logging.INFO)
    assert not module.isEnabledFor(logging.DEBUG)
    package = logging.getLogger("doro_app")
    doro = logging.getLogger("doro")
    assert doro.handlers and set(doro.handlers) <= set(package.handlers)
