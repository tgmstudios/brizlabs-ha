import json
from pathlib import Path
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "app-writes.json"


@pytest.fixture(scope="session")
def app_writes():
    return json.loads(FIXTURE.read_text())
