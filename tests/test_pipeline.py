"""Preserve the original 17 integration checks with real pytest failures."""
import pytest
from tests import smoke_pipeline

CASES = [getattr(smoke_pipeline, name) for name in vars(smoke_pipeline) if name.startswith("test_")]

@pytest.mark.parametrize("check", CASES, ids=[f"pipeline_{i}" for i in range(len(CASES))])
def test_pipeline_components(check):
    assert check(), "Synthetic pipeline check failed; inspect captured output"
