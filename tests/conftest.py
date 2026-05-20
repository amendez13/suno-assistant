"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_data() -> dict:
    """Provide sample data for tests.

    Returns:
        A dictionary with sample test data.
    """
    return {
        "key": "value",
        "number": 42,
        "items": ["a", "b", "c"],
    }
