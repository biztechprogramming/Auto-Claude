"""
Test fixtures for Auto-Claude test suite.
"""

from .complex_spec import (
    get_complex_spec,
    create_complex_spec_files,
    get_expected_workflow_states,
    get_expected_phases,
    COMPLEX_SPEC_NAME,
    COMPLEX_SPEC_CONTENT,
    COMPLEX_IMPLEMENTATION_PLAN
)

__all__ = [
    "get_complex_spec",
    "create_complex_spec_files",
    "get_expected_workflow_states",
    "get_expected_phases",
    "COMPLEX_SPEC_NAME",
    "COMPLEX_SPEC_CONTENT",
    "COMPLEX_IMPLEMENTATION_PLAN",
]
