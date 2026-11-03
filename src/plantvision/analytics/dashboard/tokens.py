"""Theme tokens, CSS ``:root`` emitter, WCAG contrast helper and inline icons.

Every colour used by the v2 shell is declared here once. No module may
hard-code a hex value that is not a token (chart primitives reference
``var(--pv-*)`` or the gradient ids built from these colours).
"""

from __future__ import annotations

THEME: dict[str, str] = {
    "--pv-bg": "#1B1730",
    "--pv-card": "#2E2952",
    "--pv-card-2": "#37316A",
    "--pv-track": "#453E77",
    "--pv-ink": "#D6D1EC",
    "--pv-mut": "#A9A2CC",
    "--pv-head": "#FFFFFF",
    "--pv-a0": "#F5705E",
    "--pv-a1": "#FBC490",
    "--pv-b0": "#7B3FE0",
    "--pv-b1": "#C159F5",
    "--pv-pos": "#2FE3A7",
    "--pv-neg": "#F5705E",
    "--pv-grid": "rgba(255,255,255,.07)",
    "--pv-focus": "#FBC490",
    "--pv-r-card": "8px",
    "--pv-r-ctrl": "4px",
    "--pv-gap": "20px",
    "--pv-pad": "20px",
}

FONT_STACK: str = (
    'ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", '
    "Arial, sans-serif"
)

ICONS: dict[str, str] = {
    "overview": (
        "M10 3a7 7 0 1 0 0 14a7 7 0 0 0 0-14z"
        "M10 6.5v4l2.6 1.6"
    ),
    "crops": (
        "M4 16c0-6.6 5.4-12 12-12c0 6.6-5.4 12-12 12z"
        "M4 16L12 8"
    ),
    "growth": (
        "M3 16l4.6-4.6l3 3L17 7"
        "M13 7h4v4"
    ),
    "shape": "M10 2.5l7.5 7.5L10 17.5L2.5 10z",
    "quality": (
        "M5.5 18V3"
        "M5.5 4h10.5l-2.8 3.8L16 11H5.5"
    ),
    "alerts": (
        "M10 2.5L2.5 16.5h15z"
        "M10 7.2v4.2"
        "M10 13.6v.5"
    ),
    "compare": (
        "M3 7h11l-2.8-2.8"
        "M17 13H6l2.8 2.8"
    ),
    "capture": (
        "M3 3h5.5v5.5H3z"
        "M11.5 3H17v5.5h-5.5z"
        "M3 11.5h5.5V17H3z"
        "M11.5 11.5H17V17h-5.5z"
    ),
    "method": (
        "M10 3a7 7 0 1 0 0 14a7 7 0 0 0 0-14z"
        "M10 9v5"
        "M10 6.4v.5"
    ),
}


def theme() -> dict[str, str]:
    """Return a copy of the theme token dictionary.

    Returns:
        A fresh ``{token: value}`` dict in insertion order.
    """
    return dict(THEME)


def css_root() -> str:
    """Render the ``:root`` block from :data:`THEME`.

    Returns:
        One CSS rule, e.g. ``:root{--pv-bg:#1B1730;...}``.
    """
    return ":root{" + ";".join(f"{key}:{value}" for key, value in THEME.items()) + "}"


def _srgb(channel: float) -> float:
    """Linearise one sRGB channel in ``0..1``.

    Args:
        channel: Channel value in ``0..1``.

    Returns:
        The linear-light value.
    """
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def _parse_hex(hex_colour: str) -> tuple[float, float, float]:
    """Parse ``#RRGGBB`` into three ``0..1`` channels.

    Args:
        hex_colour: A six-digit hex colour.

    Returns:
        The red, green and blue channels.

    Raises:
        ValueError: If the value is not a six-digit ``#RRGGBB`` colour.
    """
    value = hex_colour.strip()
    if len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"invalid colour: {hex_colour}")
    try:
        channels = tuple(int(value[index:index + 2], 16) / 255.0 for index in (1, 3, 5))
    except ValueError as exc:
        raise ValueError(f"invalid colour: {hex_colour}") from exc
    return channels  # type: ignore[return-value]


def relative_luminance(hex_colour: str) -> float:
    """Compute WCAG 2.1 relative luminance.

    Args:
        hex_colour: A six-digit hex colour.

    Returns:
        Relative luminance in ``0..1``.

    Raises:
        ValueError: For a malformed colour.
    """
    red, green, blue = _parse_hex(hex_colour)
    return 0.2126 * _srgb(red) + 0.7152 * _srgb(green) + 0.0722 * _srgb(blue)


def contrast_ratio(fg: str, bg: str) -> float:
    """Compute the WCAG 2.1 contrast ratio between two colours.

    Args:
        fg: Foreground hex colour.
        bg: Background hex colour.

    Returns:
        The ratio, ``1.0`` for identical colours.

    Raises:
        ValueError: For a malformed colour.
    """
    first = relative_luminance(fg)
    second = relative_luminance(bg)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)
