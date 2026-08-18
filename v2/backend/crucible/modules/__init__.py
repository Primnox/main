"""Crucible modules.

Each exposes `run(ctx) -> ModuleResult`. A module that cannot honestly measure
its subsystem calls `result.skip(reason)` rather than inventing a score.
"""
from . import (  # noqa: F401
    m01_chat,
    m06_graph,
    m07_memory,
    m10_streaming,
    m11_ui_strings,
    m15_performance,
    m16_failure_injection,
    m_absent,
)

ORDER = [
    m01_chat,
    m06_graph,
    m07_memory,
    m10_streaming,
    m11_ui_strings,
    m15_performance,
    m16_failure_injection,
    m_absent,
]
