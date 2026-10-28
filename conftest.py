"""Root conftest for the ATC Cala integration tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/atc_cala loadable in every test."""
    yield
