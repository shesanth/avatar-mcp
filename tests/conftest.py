"""Shared fixtures for avatar-mcp tests."""

from __future__ import annotations

import multiprocessing

import pytest

from avatar_mcp.state import SharedState


@pytest.fixture
def manager():
    mgr = multiprocessing.Manager()
    yield mgr
    mgr.shutdown()


@pytest.fixture
def shared_state(manager):
    return SharedState(manager)
