"""Pure SVG rendering helpers for function plots."""

from __future__ import annotations

import html
import math
from typing import Any, Callable

import sympy


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def format_plot_number(value: float) -> str:
    if abs(value) < 1e-10:
        return "0"
    if abs(value) >= 10000 or abs(value) < 0.001:
        return f"{value:.3e}"
    return f"{value:.5g}"


def render_function_svg(
    expression: sympy.Expr,
    variable: sympy.Symbol,
    *,
    x_min: float,
    x_max: float,
    y_min: float | None,
    y_max: float | None,
    samples: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    x_min = finite_float(x_min)
    x_max = finite_float(x_max)
    if x_min is None or x_max is None or x_min >= x_max:
        raise ValueError("invalid x range")

    function: Callable[[float], Any] = sympy.lambdify(
        variable,
        expression,
        modules=["math"],
    )
    step = (x_max - x_min) / (samples - 1)
    sampled: list[tuple[float, float | None]] = []
    finite_values: list[float] = []
    for index in range(samples):
        x_value = x_min + step * index
        try:
            y_value = finite_float(function(x_value))
        except (TypeError, ValueError, ZeroDivisionError, OverflowError):
            y_value = None
        sampled.append((x_value, y_value))
        if y_value is not None:
            finite_values.append(y_value)

    if len(finite_values) < 2:
        raise ValueError("not enough real function values")

    y_min = finite_float(y_min)
    y_max = finite_float(y_max)
    if (y_min is None) != (y_max is None):
        raise ValueError("y_min and y_max must be provided together")
    if y_min is not None and y_max is not None and y_min >= y_max:
        raise ValueError("invalid y range")

    if y_min is None or y_max is None:
        ordered = sorted(finite_values)
        low_index = max(0, int((len(ordered) - 1) * 0.02))
        high_index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.98))
        y_min = ordered[low_index]
        y_max = ordered[high_index]
        if y_max - y_min < 1e-12:
            padding = max(abs(y_min) * 0.1, 1.0)
            y_min -= padding
            y_max += padding
        else:
            padding = (y_max - y_min) * 0.08
            y_min -= padding
            y_max += padding

    left = 58.0
    right = width - 20.0
    top = 18.0
    bottom = height - 42.0
    plot_width = right - left
    plot_height = bottom - top
    x_span = x_max - x_min
    y_span = y_max - y_min

    def to_pixel_x(value: float) -> float:
        return left + (value - x_min) / x_span * plot_width

    def to_pixel_y(value: float) -> float:
        return bottom - (value - y_min) / y_span * plot_height

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Function plot for {html.escape(str(expression))}">'
        ),
        "<defs><clipPath id=\"plot-clip\">"
        f'<rect x="{left:.2f}" y="{top:.2f}" '
        f'width="{plot_width:.2f}" height="{plot_height:.2f}"/>'
        "</clipPath></defs>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        (
            f'<rect x="{left:.2f}" y="{top:.2f}" '
            f'width="{plot_width:.2f}" height="{plot_height:.2f}" '
            'fill="#fbfdff" stroke="#dce7f5"/>'
        ),
    ]

    for index in range(7):
        x_value = x_min + x_span * index / 6
        x_pixel = to_pixel_x(x_value)
        parts.append(
            f'<line x1="{x_pixel:.2f}" y1="{top:.2f}" '
            f'x2="{x_pixel:.2f}" y2="{bottom:.2f}" '
            'stroke="#e8eff9" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x_pixel:.2f}" y="{height - 18:.2f}" '
            'text-anchor="middle" fill="#6d7a91" font-size="12">'
            f"{format_plot_number(x_value)}</text>"
        )

    for index in range(5):
        y_value = y_min + y_span * index / 4
        y_pixel = to_pixel_y(y_value)
        parts.append(
            f'<line x1="{left:.2f}" y1="{y_pixel:.2f}" '
            f'x2="{right:.2f}" y2="{y_pixel:.2f}" '
            'stroke="#e8eff9" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 10:.2f}" y="{y_pixel + 4:.2f}" '
            'text-anchor="end" fill="#6d7a91" font-size="12">'
            f"{format_plot_number(y_value)}</text>"
        )

    if x_min <= 0 <= x_max:
        axis_x = to_pixel_x(0)
        parts.append(
            f'<line x1="{axis_x:.2f}" y1="{top:.2f}" '
            f'x2="{axis_x:.2f}" y2="{bottom:.2f}" '
            'stroke="#9fb2cc" stroke-width="1.4"/>'
        )
    if y_min <= 0 <= y_max:
        axis_y = to_pixel_y(0)
        parts.append(
            f'<line x1="{left:.2f}" y1="{axis_y:.2f}" '
            f'x2="{right:.2f}" y2="{axis_y:.2f}" '
            'stroke="#9fb2cc" stroke-width="1.4"/>'
        )

    path_parts: list[str] = []
    previous_y: float | None = None
    for x_value, y_value in sampled:
        if y_value is None:
            previous_y = None
            continue
        split_segment = (
            previous_y is not None
            and abs(y_value - previous_y) > y_span * 0.8
        )
        command = "M" if split_segment or previous_y is None else "L"
        path_parts.append(
            f"{command} {to_pixel_x(x_value):.2f} {to_pixel_y(y_value):.2f}"
        )
        previous_y = y_value

    if path_parts:
        parts.append(
            '<path d="' + " ".join(path_parts) + '" fill="none" '
            'stroke="#2868d8" stroke-width="2.4" stroke-linecap="round" '
            'stroke-linejoin="round" clip-path="url(#plot-clip)"/>'
        )
    parts.append("</svg>")

    return {
        "expression": str(expression),
        "variable": str(variable),
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "svg": "".join(parts),
    }
