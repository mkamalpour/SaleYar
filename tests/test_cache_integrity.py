from pathlib import Path
import pandas as pd
import pytest
from pipeline import runner
from models import loader


def test_cache_pair_must_match_saved_generation():
    frame = pd.DataFrame({'product': ['Tea']})
    runner._save_shop_cache('integrity', 'invoice-hash', frame, {'Tea': [1]})
    assert runner._load_shop_cache('integrity', 'invoice-hash') is not None
    path = Path(runner._shop_cache_path('integrity', runner.CACHE_FORECASTS))
    path.write_bytes(b'partial replacement')
    assert runner._load_shop_cache('integrity', 'invoice-hash') is None


def test_legacy_unverified_cache_is_recomputed():
    runner._save_shop_cache('legacy', 'invoice-hash', pd.DataFrame(), {})
    loader.save_shop_metadata('legacy', {'data_hash': 'invoice-hash'})
    assert runner._load_shop_cache('legacy', 'invoice-hash') is None


def test_failed_metadata_write_preserves_disk_and_memory():
    loader.save_shop_metadata('metadata', {'data_hash': 'good'})
    path = Path(loader.get_shop_dir('metadata')) / 'metadata.json'
    original = path.read_bytes()
    with pytest.raises(ValueError):
        loader.save_shop_metadata('metadata', {'bad': float('nan')})
    assert path.read_bytes() == original
    assert loader.get_shop_metadata('metadata') == {'data_hash': 'good'}
    assert not list(path.parent.glob('*.tmp'))
