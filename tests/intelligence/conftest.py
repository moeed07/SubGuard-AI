import pytest


@pytest.fixture(autouse=True)
def disable_live_extraction(monkeypatch):
    """Keep fixture scans offline even on a laptop with extraction enabled."""
    monkeypatch.delenv("SUBGUARD_GEMINI_EXTRACTION", raising=False)
