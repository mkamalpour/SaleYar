import os
os.environ["API_KEY"] = "saleyar-test-key-not-a-secret"
os.environ["LLM_ENABLED"] = "no"
import pytest
import config
from models import loader

@pytest.fixture(autouse=True)
def isolate_shop_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SHOPS_DIR", str(tmp_path / "shops"))
    monkeypatch.setattr(config, "SAVED_REPORTS_DIR", str(tmp_path / "reports"))
    loader._SHOP_MODELS.clear()
    loader._LOAD_STATUS.clear()
    yield
    loader._SHOP_MODELS.clear()
    loader._LOAD_STATUS.clear()
