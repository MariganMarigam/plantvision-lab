"""String-level SVG helpers: escaping, formatting, scales, paths and defs.

The v2 charts are plain strings. This module keeps every numeric format and
every reusable ``<defs>`` fragment in one place so the card and the drawer
drawer plots are geometrically identical.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence


def esc(value: object) -> str:
    """Escape a value for HTML text and attribute contexts.

    Args:
        value: Any value; ``None`` becomes an empty string.

    Returns:
        The escaped string.
    """
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def num(value: float, decimals: int = 2) -> str:
    """Format a float with fixed decimals and normalised negative zero.

    Args:
        value: The number.
        decimals: Decimal places.

    Returns:
        The formatted string; ``-0.00`` becomes ``0.00``.
    """
    text = f"{value:.{decimals}f}"
    if text.startswith("-") and float(text) == 0.0:
        return text[1:]
    return text


def fmt_value(
    value: float | None,
    decimals: int = 1,
    unit: str = "",
    *,
    missing: str = "not measured",
) -> str:
    """Format an optional measurement, never inventing a zero.

    Args:
        value: The measurement, or ``None``.
        decimals: Decimal places.
        unit: Unit suffix appended after a space when non-empty.
        missing: Text rendered when the value is absent or non-finite.

    Returns:
        The formatted value with unit, or the escaped missing label.
    """
    if value is None or not math.isfinite(value):
        return esc(missing)
    suffix = f" {unit}" if unit else ""
    return f"{num(value, decimals)}{suffix}"


def linear(
    domain: tuple[float, float], out: tuple[float, float]
) -> Callable[[float], float]:
    """Build a linear scale from a data domain to an output range.

    Args:
        domain: ``(d0, d1)`` input bounds.
        out: ``(o0, o1)`` output bounds.

    Returns:
        A callable mapping a domain value to the output range.
    """
    d0, d1 = domain
    o0, o1 = out
    if d1 == d0:
        d0, d1 = d0 - 0.5, d0 + 0.5

    def scale(value: float) -> float:
        return o0 + (value - d0) * (o1 - o0) / (d1 - d0)

    return scale


def nice_ticks(lo: float, hi: float, count: int = 4) -> tuple[list[float], float]:
    """Choose human-friendly tick positions over an interval.

    Args:
        lo: Lower bound.
        hi: Upper bound.
        count: Approximate number of intervals.

    Returns:
        ``(ticks, step)`` with ticks ascending inside ``[lo, hi]``.

    Raises:
        ValueError: If ``count <= 0``.
    """
    if count <= 0:
        raise ValueError(f"count must be positive, got {count}")
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        return [lo], 1.0
    raw = (hi - lo) / count
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = min(
        (1.0, 2.0, 2.5, 5.0, 10.0), key=lambda multip: abs(multip * magnitude - raw)
    ) * magnitude
    start = math.ceil(lo / step - 1e-9) * step
    ticks: list[float] = []
    value = start
    while value <= hi + 1e-9:
        ticks.append(round(value, 10))
        value += step
    return ticks, step


def path_polyline(points: Sequence[tuple[float, float]]) -> str:
    """Build a straight polyline path (no smoothing).

    Args:
        points: ``(x, y)`` pairs in drawing order.

    Returns:
        An SVG ``d`` attribute value, or an empty string for no points.
    """
    if not points:
        return ""
    first = points[0]
    commands = [f"M{num(first[0])} {num(first[1])}"]
    for x, y in points[1:]:
        commands.append(f"L{num(x)} {num(y)}")
    return " ".join(commands)


def chart_open(
    width: int, height: int, *, chart_id: str, title: str, desc: str
) -> str:
    """Open a chart ``<svg>`` with an accessible title and description.

    Args:
        width: ViewBox width.
        height: ViewBox height.
        chart_id: Unique chart id (also the ``data-chart`` value).
        title: Human title.
        desc: Longer description (what + now).

    Returns:
        The opening SVG markup.
    """
    return (
        f'<svg class="pv-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-labelledby="{esc(chart_id)}-t" preserveAspectRatio="xMidYMid meet" '
        f'data-chart="{esc(chart_id)}">'
        f'<title id="{esc(chart_id)}-t">{esc(title)}</title>'
        f"<desc>{esc(desc)}</desc>"
    )


def chart_close() -> str:
    """Close a chart ``<svg>`` element.

    Returns:
        The closing tag.
    """
    return "</svg>"


def defs_gradient(
    gid: str, stops: tuple[tuple[str, str], ...], *, vertical: bool = False
) -> str:
    """Build a two-colour linear gradient definition.

    Args:
        gid: Gradient id (referenced as ``url(#gid)``).
        stops: ``(offset, colour)`` pairs rendered in order.
        vertical: Draw bottom-to-top when ``True`` (bar/ring lighting).

    Returns:
        The ``<linearGradient>`` markup.

    Raises:
        ValueError: If no stops are supplied.
    """
    if not stops:
        raise ValueError("gradient needs at least one stop")
    if vertical:
        coords = 'x1="0%" y1="100%" x2="0%" y2="0%"'
    else:
        coords = 'x1="0%" y1="0%" x2="100%" y2="0%"'
    children = "".join(
        f'<stop offset="{esc(offset)}" stop-color="{esc(colour)}"/>'
        for offset, colour in stops
    )
    return f'<linearGradient id="{esc(gid)}" {coords}>{children}</linearGradient>'


def defs_hatch(pid: str, colour: str, *, angle: int = 45) -> str:
    """Build a diagonal hatch pattern (second series, D14).

    Args:
        pid: Pattern id.
        colour: Stroke colour.
        angle: Rotation in degrees.

    Returns:
        The ``<pattern>`` markup.
    """
    return (
        f'<pattern id="{esc(pid)}" width="8" height="8" '
        f'patternUnits="userSpaceOnUse" patternTransform="rotate({angle})">'
        '<rect width="8" height="8" fill="none"/>'
        f'<line x1="0" y1="0" x2="0" y2="8" stroke="{esc(colour)}" '
        'stroke-width="2" opacity="0.55"/>'
        "</pattern>"
    )


def defs_band(bid: str, colour: str, opacity: float = 0.12) -> str:
    """Build the soft band gradient used for warn/critical corridors.

    Args:
        bid: Gradient id.
        colour: Fill colour.
        opacity: Opacity at the top stop.

    Returns:
        The ``<linearGradient>`` markup.
    """
    return (
        f'<linearGradient id="{esc(bid)}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{esc(colour)}" '
        f'stop-opacity="{num(opacity, 2)}"/>'
        "</linearGradient>"
    )


def text(
    x: float, y: float, content: str, *, cls: str = "pv-ax", anchor: str = "start"
) -> str:
    """Render one SVG text node.

    Args:
        x: X coordinate.
        y: Y coordinate.
        content: Text (escaped).
        cls: CSS class.
        anchor: ``text-anchor`` value.

    Returns:
        The ``<text>`` markup.
    """
    return (
        f'<text x="{num(x)}" y="{num(y)}" class="{esc(cls)}" '
        f'text-anchor="{esc(anchor)}">{esc(content)}</text>'
    )
