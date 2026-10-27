"""Metric math and promotion-gate tests."""

from __future__ import annotations

import numpy as np
import pytest

from plantvision.ml.eval import (
    area_error_pct,
    dice_score,
    gate_verdict,
    iou_score,
    precision_recall,
    summarize,
)

GATE = {
    "min_val_dice": 0.85,
    "min_test_dice": 0.85,
    "min_test_iou": 0.75,
    "min_test_recall": 0.90,
    "max_area_abs_pct_error_median": 5.0,
    "max_area_abs_pct_error_p90": 10.0,
}


def _passing_summary() -> dict[str, dict[str, object]]:
    """Summary fixture that passes every frozen threshold."""
    return {
        "val": {"dice": 0.90},
        "test": {
            "dice": 0.90,
            "iou": 0.80,
            "recall": 0.95,
            "area_abs_pct_error_median": 2.0,
            "area_abs_pct_error_p90": 5.0,
        },
    }


def test_dice_cases() -> None:
    """Perfect, disjoint, and empty-over-empty Dice values."""
    mask = np.array([[1, 1], [0, 0]], dtype=bool)
    assert dice_score(mask, mask) == pytest.approx(1.0)
    assert dice_score(mask, ~mask) == pytest.approx(0.0, abs=1e-6)
    empty = np.zeros((4, 4), dtype=bool)
    assert dice_score(empty, empty) == pytest.approx(1.0)


def test_iou_cases() -> None:
    """Perfect and empty-over-empty IoU values."""
    mask = np.array([[1, 1], [0, 0]], dtype=bool)
    assert iou_score(mask, mask) == pytest.approx(1.0)
    empty = np.zeros((4, 4), dtype=bool)
    assert iou_score(empty, empty) == pytest.approx(1.0)
    assert iou_score(mask, ~mask) == pytest.approx(0.0, abs=1e-6)


def test_precision_recall_cases() -> None:
    """Hand-computed precision/recall on a 2x2 mask."""
    pred = np.array([[1, 1], [0, 0]], dtype=bool)
    gt = np.array([[1, 0], [1, 0]], dtype=bool)
    precision, recall = precision_recall(pred, gt)
    assert precision == pytest.approx(0.5)
    assert recall == pytest.approx(0.5)
    empty = np.zeros((2, 2), dtype=bool)
    assert precision_recall(empty, gt) == (0.0, 0.0)
    assert precision_recall(empty, empty) == (1.0, 1.0)


def test_area_error_pct() -> None:
    """Signed area error and the empty-ground-truth guard."""
    assert area_error_pct(110, 100) == pytest.approx(10.0)
    assert area_error_pct(90, 100) == pytest.approx(-10.0)
    with pytest.raises(ValueError):
        area_error_pct(10, 0)


def test_summarize() -> None:
    """Median and linear-interpolated p90 match hand values."""
    stats = summarize([1.0, 2.0, 3.0, 100.0])
    assert stats["median"] == pytest.approx(2.5)
    assert stats["p90"] == pytest.approx(70.9, abs=1e-6)
    assert stats["n"] == 4
    empty = summarize([])
    assert empty["mean"] == 0.0
    assert empty["n"] == 0


def test_gate_promote() -> None:
    """A summary above every threshold promotes."""
    assert gate_verdict(_passing_summary(), GATE) == ("promote", [])


@pytest.mark.parametrize(
    "field,value,name",
    [
        ("dice", 0.80, "dice"),
        ("iou", 0.70, "iou"),
        ("recall", 0.80, "recall"),
        ("area_abs_pct_error_median", 6.0, "area_abs_pct_error_median"),
        ("area_abs_pct_error_p90", 20.0, "area_abs_pct_error_p90"),
    ],
)
def test_gate_rollback_reasons(field: str, value: float, name: str) -> None:
    """Each violated threshold produces a reason naming the field."""
    summary = _passing_summary()
    summary["test"][field] = value
    verdict, reasons = gate_verdict(summary, GATE)
    assert verdict == "rollback"
    assert any(name in reason for reason in reasons)


def test_gate_requires_test_summary() -> None:
    """A summary without a test split is a programming error."""
    with pytest.raises(ValueError, match="test split summary required"):
        gate_verdict({"val": {"dice": 0.9}}, GATE)


def test_gate_val_failure_rolls_back() -> None:
    """A low validation Dice blocks promotion even when test passes."""
    summary = _passing_summary()
    summary["val"]["dice"] = 0.5
    verdict, reasons = gate_verdict(summary, GATE)
    assert verdict == "rollback"
    assert any("val_dice" in reason for reason in reasons)
