"""Conformance tests for the frozen perception/fiducial/measurement contract."""

import inspect

import cv2
import numpy as np
import pytest

from plantvision.vision import interfaces
from plantvision.vision.interfaces import (
    ContractError,
    check_mask,
    check_measurement_result,
    check_px_per_mm,
    perception,
    fiducial as classical_fiducial,
)
from plantvision.vision.segmentation import segment_plant
from plantvision.vision.scale import px_per_mm as scale_px_per_mm

IMPLEMENTERS: dict[str, object] = {"classical": interfaces}


def _green_blob_image() -> np.ndarray:
    """Build a gray (128, 128, 128) canvas with a filled green circle at center."""
    img = np.full((120, 120, 3), 128, np.uint8)
    cv2.circle(img, (60, 60), 20, (0, 200, 0), -1)
    return img


def _marker_canvas() -> np.ndarray:
    """White 400x400 grayscale canvas with a 200 px id=1 DICT_5X5_50 marker."""
    canvas = np.full((400, 400), 255, np.uint8)
    canvas[100:300, 100:300] = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 1, 200
    )
    return canvas


@pytest.mark.parametrize("name,impl", list(IMPLEMENTERS.items()))
def test_implementer_perception_signature(name: str, impl: object) -> None:
    """Every perception implementer takes exactly one ``image`` parameter."""
    assert list(inspect.signature(impl.perception).parameters) == ["image"]


@pytest.mark.parametrize("name,impl", list(IMPLEMENTERS.items()))
def test_implementer_fiducial_signature(name: str, impl: object) -> None:
    """Every fiducial implementer takes exactly one ``image`` parameter."""
    assert list(inspect.signature(impl.fiducial).parameters) == ["image"]


@pytest.mark.parametrize("name,impl", list(IMPLEMENTERS.items()))
def test_implementer_measurement_signature(name: str, impl: object) -> None:
    """Every measurement implementer takes exactly (mask, px_per_mm, ts)."""
    assert list(inspect.signature(impl.measurement).parameters) == [
        "mask",
        "px_per_mm",
        "ts",
    ]


@pytest.mark.parametrize("name,impl", list(IMPLEMENTERS.items()))
def test_implementer_perception_contract(name: str, impl: object) -> None:
    """The implementer's mask passes check_mask and is non-empty on a green blob."""
    img = _green_blob_image()
    mask = impl.perception(img)
    check_mask(mask, img)
    assert cv2.countNonZero(mask) > 0


@pytest.mark.parametrize("name,impl", list(IMPLEMENTERS.items()))
def test_implementer_fiducial_contract_scaled(name: str, impl: object) -> None:
    """The implementer's scale passes check_px_per_mm and matches the marker size."""
    v = impl.fiducial(_marker_canvas())
    check_px_per_mm(v)
    assert v == pytest.approx(200 / 45, rel=0.05)


@pytest.mark.parametrize("name,impl", list(IMPLEMENTERS.items()))
def test_implementer_fiducial_contract_unscaled(name: str, impl: object) -> None:
    """A frame without a marker yields None (ADR 0002), never a fabricated number."""
    assert impl.fiducial(np.full((400, 400, 3), 255, np.uint8)) is None


@pytest.mark.parametrize("name,impl", list(IMPLEMENTERS.items()))
def test_implementer_measurement_contract(name: str, impl: object) -> None:
    """A real implementer result passes the dict check with hand-computed geometry."""
    mask = np.zeros((100, 100), np.uint8)
    mask[10:30, 10:30] = 255
    result = impl.measurement(mask, 4.0, "2026-10-16T00:00:00Z")
    check_measurement_result(result)
    assert result["projected_area_px"] == 400
    assert result["projected_area_cm2"] == pytest.approx(400 / (4.0**2) / 100)
    assert result["roi_fraction_pct"] == pytest.approx(4.0)


def test_perception_binding_faithful_to_segment_plant() -> None:
    """The classical perception slot is exactly segment_plant(method="hsv")."""
    img = _green_blob_image()
    assert np.array_equal(perception(img), segment_plant(img, method="hsv"))


def test_fiducial_binding_faithful_to_px_per_mm() -> None:
    """The classical fiducial slot is exactly scale.px_per_mm."""
    canvas = _marker_canvas()
    assert classical_fiducial(canvas) == scale_px_per_mm(canvas)


def test_measurement_unscaled_returns_none_cm() -> None:
    """Without a scale the cm metrics are None (pixel-only metrics, ADR 0002)."""
    mask = np.zeros((100, 100), np.uint8)
    mask[10:30, 10:30] = 255
    assert interfaces.measurement(mask, None, None)["projected_area_cm2"] is None


def test_measurement_rejects_nonpositive_scale() -> None:
    """A non-positive scale is rejected before it can divide by zero."""
    mask = np.zeros((100, 100), np.uint8)
    mask[10:30, 10:30] = 255
    with pytest.raises(ContractError):
        interfaces.measurement(mask, 0.0, None)


def test_check_mask_rejects_non_ndarray() -> None:
    """A list masquerading as a mask is rejected."""
    with pytest.raises(ContractError):
        check_mask([[0]], _green_blob_image())


def test_check_mask_rejects_float_dtype() -> None:
    """A non-uint8 mask is rejected."""
    with pytest.raises(ContractError):
        check_mask(np.zeros((120, 120), np.float32), _green_blob_image())


def test_check_mask_rejects_wrong_shape() -> None:
    """A mask whose (H, W) differs from the image is rejected."""
    with pytest.raises(ContractError):
        check_mask(np.zeros((10, 10), np.uint8), _green_blob_image())


def test_check_mask_rejects_non_binary_values() -> None:
    """A mask with values outside {0, 255} is rejected."""
    with pytest.raises(ContractError):
        check_mask(np.full((120, 120), 128, np.uint8), _green_blob_image())


def test_check_px_per_mm_accepts_none() -> None:
    """None (no marker in frame) is a valid scale per ADR 0002."""
    check_px_per_mm(None)


def test_check_px_per_mm_rejects_zero() -> None:
    """Zero scale would divide by zero downstream and is rejected."""
    with pytest.raises(ContractError):
        check_px_per_mm(0.0)


def test_check_px_per_mm_rejects_negative() -> None:
    """A negative scale is physically meaningless and is rejected."""
    with pytest.raises(ContractError):
        check_px_per_mm(-1.0)


def test_check_measurement_result_rejects_missing_key() -> None:
    """A result dict missing required keys is rejected."""
    with pytest.raises(ContractError):
        check_measurement_result({"ts": None})


def test_check_measurement_result_rejects_bad_type() -> None:
    """A result dict with a wrongly typed metric value is rejected."""
    mask = np.zeros((100, 100), np.uint8)
    mask[10:30, 10:30] = 255
    result = interfaces.measurement(mask, 4.0, "t")
    result["projected_area_px"] = "x"
    with pytest.raises(ContractError):
        check_measurement_result(result)
