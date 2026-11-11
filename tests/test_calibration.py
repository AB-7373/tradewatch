"""Ground-truth labels and the calibration report card."""
import numpy as np
import pandas as pd
import pytest

from calibration import calibration_report, make_labels


def test_make_labels_up_down_flat_and_nan_at_end():
    close = pd.Series([100.0, 100.5, 99.0, 100.05, 100.0, 100.0])
    lab = make_labels(close, horizon=1, band=0.001)
    # 100->100.5 up, 100.5->99 down, 99->100.05 up, 100.05->100 flat (0.05%), 100->100 flat
    assert lab.iloc[:5].tolist() == ["up", "down", "up", "flat", "flat"]
    assert pd.isna(lab.iloc[-1])                      # future unknown -> not graded


def test_make_labels_horizon_leaves_last_n_ungraded():
    lab = make_labels(pd.Series(np.linspace(100, 110, 10)), horizon=3, band=0.001)
    assert lab.isna().sum() == 3 and lab.iloc[-4] == "up"


def _preds(rows):
    return pd.DataFrame(rows, columns=["p_up", "p_down", "p_flat"])


def test_report_accuracy_class_freq_and_majority():
    labels = pd.Series(["up", "up", "up", "down"])
    preds = _preds([[0.6, 0.3, 0.1], [0.2, 0.7, 0.1], [0.5, 0.4, 0.1], [0.1, 0.8, 0.1]])
    rep = calibration_report(preds, labels)
    assert rep["n"] == 4
    assert rep["accuracy"] == pytest.approx(0.75)
    assert rep["class_freq"] == pytest.approx({"up": 0.75, "down": 0.25, "flat": 0.0})
    assert rep["majority_class"] == "up" and rep["majority_accuracy"] == pytest.approx(0.75)
    assert rep["picked_freq"] == pytest.approx({"up": 0.5, "down": 0.5, "flat": 0.0})


def test_perfect_forecaster_has_zero_brier_and_full_skill():
    labels = pd.Series(["up", "down", "flat", "up"])
    preds = _preds([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]])
    rep = calibration_report(preds, labels)
    for c in ("up", "down", "flat"):
        assert rep["classes"][c]["brier"] == 0
        assert rep["classes"][c]["skill"] == pytest.approx(1.0)


def test_ungraded_rows_are_dropped():
    labels = pd.Series(["up", None, "down"])
    preds = _preds([[0.6, 0.3, 0.1]] * 3)
    assert calibration_report(preds, labels)["n"] == 2
