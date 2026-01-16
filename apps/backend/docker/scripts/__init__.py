"""
Container Agent Scripts Package
================================

This package contains standalone Python scripts designed to run inside Docker containers
as part of the Auto Claude multi-agent orchestration system.

Scripts:
    - developer_agent.py: Implements code based on implementation plans
    - evaluator_agent.py: Reviews code quality and best practices
    - qa_agent.py: Runs automated tests and validation

Each script is designed to be executed independently in its own container,
with all configuration passed via environment variables.

Usage:
    See README.md for detailed documentation and examples.
"""

__all__ = [
    "developer_agent",
    "evaluator_agent",
    "qa_agent",
]
