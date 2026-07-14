from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def silence_detector() -> Path:
    """Root of the SDK-convention example project fixture."""
    return FIXTURES / "silence_detector"
