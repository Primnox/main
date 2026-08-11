"""Regression test for a real, currently-active production bug: every
distinct get_logger(name) call used to build its OWN RotatingFileHandler on
the same primnox.log path. With 20+ named loggers across the app, that meant
20+ independent open file handles on one file — the moment it hit its 5MB
rollover threshold, Windows refused every rename() because some other
logger's handle was still open, so rotation silently and permanently broke
for the rest of the process's life (every log call afterward printed a
PermissionError traceback to stderr). Confirmed reproducing on a completely
fresh process start, not something caused by this session's own work.

Fix: all named loggers share one singleton set of handler instances.
"""
import logging

import logger as logger_module


def test_distinct_logger_names_share_the_same_handler_instances():
    a = logger_module.get_logger("test_shared_handlers_a")
    b = logger_module.get_logger("test_shared_handlers_b")

    assert a is not b  # genuinely different logger objects...
    assert len(a.handlers) == len(b.handlers) > 0
    # ...but every handler on one is the exact same object as on the other,
    # so there is exactly one open file handle on primnox.log no matter how
    # many named loggers the app creates.
    assert list(a.handlers) == list(b.handlers)
    for h in a.handlers:
        assert isinstance(h, (logging.Handler,))


def test_only_one_rotating_file_handler_exists_across_all_loggers():
    from logging.handlers import RotatingFileHandler

    logger_module.get_logger("test_shared_handlers_c")
    logger_module.get_logger("test_shared_handlers_d")
    logger_module.get_logger("test_shared_handlers_e")

    seen_file_handlers = set()
    for name in ("test_shared_handlers_c", "test_shared_handlers_d", "test_shared_handlers_e"):
        lg = logging.getLogger(f"primnox.{name}")
        for h in lg.handlers:
            if isinstance(h, RotatingFileHandler):
                seen_file_handlers.add(id(h))

    assert len(seen_file_handlers) == 1


def test_get_logger_called_twice_with_same_name_does_not_duplicate_handlers():
    first = logger_module.get_logger("test_shared_handlers_f")
    handler_count = len(first.handlers)
    second = logger_module.get_logger("test_shared_handlers_f")

    assert first is second
    assert len(second.handlers) == handler_count
