"""Generic single-variable interval extrema solver."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sympy import E, diff, latex, limit, simplify, solve, symbols
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from app.main import parse_math_expression


_REPLACEMENTS = str.maketrans(
    {
        "\u2212": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\uff0d": "-",
        "\u00d7": "*",
        "\u00b7": "*",
        "\u00f7": "/",
        "\uff08": "(",
        "\uff09": ")",
        "\uff0c": ",",
        "\uff1b": ";",
        "\u3002": ".",
    }
)

_MAX_LABEL = "\u6700\u5927\u503c"
_MIN_LABEL = "\u6700\u5c0f\u503c"
_HELP_SUGGESTIONS = [
    "\u7ed9\u6211\u4e00\u9053\u6c42\u5bfc\u9898",
    "\u8ba1\u7b97\u4e0d\u5b9a\u79ef\u5206",
    "\u6c42\u51fd\u6570\u6781\u9650",
]


def solve_interval_extrema(question: str) -> dict[str, Any] | None:
    """Parse and solve a single-variable extrema question on an interval."""
    text = _normalize_question(question)
    if not text:
        return None

    if _MAX_LABEL in text:
        kind = "max"
        kind_label = _MAX_LABEL
    elif _MIN_LABEL in text:
        kind = "min"
        kind_label = _MIN_LABEL
    else:
        return None

    interval_match = re.search(
        r"(?:\u533a\u95f4|\u5728)"
        r"(?P<left>[\(\[])(?P<lower>[^,\)\]]+),"
        r"(?P<upper>[^\)\]]+)(?P<right>[\)\]])",
        text,
    )
    if interval_match is None:
        return None

    function_match = re.search(
        r"(?:[fgh]\((?P<variable>[A-Za-z])\)|y)="
        r"(?P<expression>[^,;\uFF0C\uFF1B\u3002]*?)"
        r"[,;\uFF0C\uFF1B\u3002]?"
        r"(?=\u5728|\u533a\u95f4|\u5219|\u6c42|$)",
        text,
    )
    if function_match is None:
        return None

    variable_name = function_match.group("variable") or "x"
    # parse_math_expression returns symbols without assumptions. Reusing that
    # same symbol is required, otherwise SymPy treats x and x(real=True) as
    # different variables and the derivative becomes zero.
    variable = symbols(variable_name)

    try:
        expression = _parse_expression(
            function_match.group("expression"),
            variable,
        )
        lower = _parse_bound(interval_match.group("lower"), variable)
        upper = _parse_bound(interval_match.group("upper"), variable)
        derivative = simplify(diff(expression, variable))
        critical_points = [
            point
            for point in solve(derivative, variable)
            if point.is_real is not False
        ]
    except Exception:
        return None

    candidates: list[tuple[str, Any]] = []
    lower_value = _safe_float(lower)
    upper_value = _safe_float(upper)

    for point in critical_points:
        point_value = _safe_float(point)
        if point_value is None:
            continue
        if lower_value is not None:
            if interval_match.group("left") == "[":
                if point_value < lower_value:
                    continue
            elif point_value <= lower_value:
                continue
        if upper_value is not None:
            if interval_match.group("right") == "]":
                if point_value > upper_value:
                    continue
            elif point_value >= upper_value:
                continue
        value = simplify(expression.subs(variable, point))
        if _is_usable_value(value):
            candidates.append(
                (
                    f"\u9a7b\u70b9 {variable_name}={point}",
                    value,
                )
            )

    try:
        if interval_match.group("left") == "[":
            left_value = simplify(expression.subs(variable, lower))
            left_label = f"\u5de6\u7aef\u70b9 {variable_name}={lower}"
        else:
            left_value = limit(expression, variable, lower, dir="+")
            left_label = (
                f"\u5de6\u7aef\u70b9 {variable_name}={lower} \u7684\u6781\u9650"
            )
        if _is_usable_value(left_value):
            candidates.append((left_label, left_value))

        if interval_match.group("right") == "]":
            right_value = simplify(expression.subs(variable, upper))
            right_label = f"\u53f3\u7aef\u70b9 {variable_name}={upper}"
        else:
            right_value = limit(expression, variable, upper, dir="-")
            right_label = (
                f"\u53f3\u7aef\u70b9 {variable_name}={upper} \u7684\u6781\u9650"
            )
        if _is_usable_value(right_value):
            candidates.append((right_label, right_value))
    except Exception:
        return None

    if not candidates:
        return None

    chooser = max if kind == "max" else min
    selected_label, selected_value = chooser(
        candidates,
        key=lambda item: float(item[1].evalf()),
    )
    selected_value = simplify(selected_value)
    interval_text = (
        f"{interval_match.group('left')}{lower}, "
        f"{upper}{interval_match.group('right')}"
    )
    comparison = "\uff1b".join(
        f"{label}\uff1a"
        f"{_latex_equation(f'f({variable_name})', value)}"
        for label, value in candidates
    )
    critical_text = (
        "\u3001".join(
            _latex_equation(variable_name, point)
            for point in critical_points
        )
        if critical_points
        else "\u65e0\u5b9e\u6570\u9a7b\u70b9"
    )
    derivative_latex = _latex_equation(f"f'({variable_name})", derivative)
    formula = (
        rf"\max_{{{variable_name}\in{interval_text}}}"
        rf"\left({latex(expression)}\right)={latex(selected_value)}"
    )
    if kind == "min":
        formula = formula.replace(r"\max", r"\min", 1)

    return {
        "status": "ok",
        "intent": "solve",
        "reply": (
            f"\u51fd\u6570\u5728\u533a\u95f4 {interval_text} "
            f"\u4e0a\u7684{kind_label}\u662f "
            f"{_latex_math(selected_value)}\u3002\n"
            f"\u6c42\u5bfc\u5f97 {derivative_latex}\uff0c"
            f"\u9a7b\u70b9\u4e3a {critical_text}\u3002\n"
            f"\u6bd4\u8f83\u5019\u9009\u503c\uff1a{comparison}\u3002\n"
            f"\u56e0\u6b64\uff0c{selected_label} \u53d6\u5230"
            f"{kind_label} {_latex_math(selected_value)}\u3002"
        ),
        "formula_latex": formula,
        "formula_text": f"{kind_label} = {selected_value}",
        "calculation": {
            "expression": str(expression),
            "variable": variable_name,
            "interval": interval_text,
            "kind": kind_label,
            "derivative": str(derivative),
            "critical_points": [str(point) for point in critical_points],
            "candidates": [
                f"{label}: {simplify(value)}"
                for label, value in candidates
            ],
            "result": str(selected_value),
        },
        "suggestions": _HELP_SUGGESTIONS,
    }


def _latex_math(value: Any) -> str:
    """Wrap one SymPy value in the inline math syntax used by the demo."""
    return f"${latex(simplify(value))}$"


def _latex_equation(left: str, right: Any) -> str:
    """Render a simple equation without leaking SymPy's ``*`` syntax."""
    return f"${left}={latex(simplify(right))}$"


def _normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFKC", str(question))
    text = text.translate(_REPLACEMENTS)
    text = re.sub(
        r"\b(?:in|1n)\s*([A-Za-z])",
        r"ln(\1)",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bln\s*([A-Za-z])",
        r"ln(\1)",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", "", text).strip()


def _parse_expression(value: str, variable):
    cleaned = value.strip().rstrip(",;\uFF0C\uFF1B\u3002")
    if not cleaned:
        raise ValueError("empty expression")
    try:
        return parse_math_expression(cleaned)
    except Exception:
        return parse_expr(
            cleaned,
            transformations=(
                standard_transformations
                + (implicit_multiplication_application,)
            ),
            local_dict={
                variable.name: variable,
                "ln": __import__("sympy").log,
                "log": __import__("sympy").log,
                "exp": __import__("sympy").exp,
                "pi": __import__("sympy").pi,
                "e": E,
            },
            global_dict={"__builtins__": {}},
        )


def _parse_bound(value: str, variable):
    cleaned = value.strip()
    if cleaned.lower() in {"e", "exp(1)"}:
        return E
    return _parse_expression(cleaned, variable)


def _safe_float(value) -> float | None:
    try:
        numeric = complex(value.evalf())
    except Exception:
        return None
    if abs(numeric.imag) > 1e-12:
        return None
    return numeric.real


def _is_usable_value(value) -> bool:
    try:
        return bool(value.is_finite)
    except Exception:
        return False
