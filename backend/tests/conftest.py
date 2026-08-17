import os

import pytest
from fastapi.testclient import TestClient

os.environ["LLM_PROVIDER"] = "mock"

from backend.app.main import app
from backend.app.store.memory_store import store


@pytest.fixture(autouse=True)
def clean_store():
    store.clear()
    yield
    store.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def source():
    return "Water freezes at zero degrees Celsius. Exercise improves cardiovascular health. Plants convert light into energy. The Moon orbits Earth. Bees pollinate many flowering plants. Regular sleep supports memory. Oceans cover 71% of Earth."
