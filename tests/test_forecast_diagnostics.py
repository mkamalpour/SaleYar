import numpy as np
import pytest
from pipeline.forecast_baseline import scores, values


def test_bias_is_signed_and_zero_demand_does_not_fabricate_percentage():
    report = scores([0, 2, 4], [1, 3, 5], 'synthetic')
    assert report['mean_bias'] == 1 and report['bias_percent'] == 50
    assert report['rmse'] == 1 and report['zero_demand_days'] == 1
    zero = scores([0, 0], [1, 1], 'synthetic')
    assert zero['bias_percent'] is None and zero['wape_percent'] is None


def test_invalid_shapes_negative_demand_and_horizon_fail_clearly():
    for actual, predicted in [([[1]], [[1]]), ([-1], [0]), ([0], [float('nan')])]:
        with pytest.raises(ValueError):
            scores(actual, predicted, 'synthetic')
    for horizon in [0, True, 1.5, -1]:
        with pytest.raises(ValueError, match='positive integer'):
            values(np.ones(20), horizon)
