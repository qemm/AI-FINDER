"""Shared pytest fixtures for the AI-FINDER test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Replace asyncio.sleep with an instant no-op for all tests.

    This prevents rate-limiting delays from inflating test run time while
    still allowing tests to assert that sleep is called when needed.
    """
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
