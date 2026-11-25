"""Independent result verification for deterministic chapter solvers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import sympy
from sympy import (
    Abs,
    Eq,
    Function,
    Limit,
    Matrix,
    MatrixBase,
    Sum,
    acos,
    diff,
    expand,
    integrate,
    simplify,
    solve,
    sqrt,
)


class VerificationInputError(ValueError):
    """Raised when verification cannot use the original problem context."""


def verification_check(
    name: str,
    passed: Any,
    detail: str = "",
) -> dict[str, Any]:
    check: dict[str, Any] = {
        "name": str(name),
        "passed": bool(passed),
    }
    if detail:
        check["detail"] = str(detail)
    return check


def verify_chapter_calculation(
    calculation: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None,
) -> tuple[str, list[dict[str, Any]]]:
    """Recompute a chapter result from its original inputs."""
    if not isinstance(calculation, Mapping) or not calculation:
        return "chapter", [verification_check("calculation_available", False, "缺少计算明细")]
    if not isinstance(context, Mapping):
        return "chapter", [verification_check("input_context", False, "缺少原始题目条件")]

    chapter = str(context.get("chapter") or "").strip()
    topic = str(context.get("topic") or "").strip()
    inputs = context.get("inputs")
    checks = [
        verification_check(
            "input_context",
            bool(chapter and topic) and isinstance(inputs, Mapping),
            "原始章节、题型和输入条件必须完整",
        ),
        verification_check(
            "chapter_topic_match",
            chapter == str(calculation.get("chapter") or "").strip()
            and topic == str(calculation.get("topic") or "").strip(),
            "计算结果的章节和题型必须与原始请求一致",
        ),
    ]
    if not checks[0]["passed"] or not checks[1]["passed"]:
        return topic or "chapter", checks

    verifier = _VERIFIERS.get((chapter, topic))
    if verifier is None:
        checks.append(
            verification_check(
                "independent_recalculation",
                False,
                f"尚未配置独立验算：{chapter}/{topic}",
            )
        )
        return topic, checks

    result_text = str(calculation.get("result") or "").strip()
    checks.append(
        verification_check(
            "result_available",
            bool(result_text) and not _has_incomplete_marker(result_text),
            "结果不能为空，也不能保留未求值运算",
        )
    )
    if not checks[-1]["passed"]:
        return topic, checks

    try:
        checks.extend(verifier(inputs, calculation))
    except Exception as exc:
        checks.append(
            verification_check(
                "required_conditions",
                False,
                f"无法完成独立复算：{exc}",
            )
        )
    return topic, checks


def verify_generic_solve_calculation(
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Verify non-chapter solve payloads produced by the chat layer."""
    result_text = str(calculation.get("result") or "").strip()
    checks = [
        verification_check(
            "result_available",
            bool(result_text) and not _has_incomplete_marker(result_text),
        )
    ]

    try:
        if {"equation", "variable", "solutions"} <= set(calculation):
            checks.extend(_verify_equation_solution(calculation))
        elif {"matrix", "result"} <= set(calculation):
            checks.extend(_verify_determinant(calculation))
        elif {"expression", "interval", "kind", "critical_points"} <= set(calculation):
            checks.extend(_verify_interval_extrema(calculation))
        else:
            checks.append(
                verification_check(
                    "calculation_type",
                    False,
                    "无法识别通用求解结果的计算类型",
                )
            )
    except Exception as exc:
        checks.append(
            verification_check(
                "independent_recalculation",
                False,
                f"独立复算失败：{exc}",
            )
        )
    return checks


_VERIFIERS: dict[
    tuple[str, str],
    Callable[[Mapping[str, Any], Mapping[str, Any]], list[dict[str, Any]]],
] = {}


def _register(
    chapter: str,
    topic: str,
) -> Callable[
    [Callable[[Mapping[str, Any], Mapping[str, Any]], list[dict[str, Any]]]],
    Callable[[Mapping[str, Any], Mapping[str, Any]], list[dict[str, Any]]],
]:
    def decorator(
        callback: Callable[
            [Mapping[str, Any], Mapping[str, Any]],
            list[dict[str, Any]],
        ],
    ) -> Callable[[Mapping[str, Any], Mapping[str, Any]], list[dict[str, Any]]]:
        _VERIFIERS[(chapter, topic)] = callback
        return callback

    return decorator


def _text(
    inputs: Mapping[str, Any],
    key: str,
    *,
    required: bool = True,
    default: str | None = None,
) -> str | None:
    value = inputs.get(key, default)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise VerificationInputError(f"缺少输入项：{key}")
        return None
    if not isinstance(value, str):
        raise VerificationInputError(f"{key} 必须是文本")
    return value.strip()


def _integer(
    inputs: Mapping[str, Any],
    key: str,
    *,
    default: int,
) -> int:
    value = inputs.get(key, default)
    if isinstance(value, bool):
        raise VerificationInputError(f"{key} 必须是整数")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise VerificationInputError(f"{key} 必须是整数") from exc


def _items(
    inputs: Mapping[str, Any],
    key: str,
    *,
    required: bool = True,
) -> list[Any] | None:
    value = inputs.get(key)
    if value is None:
        if required:
            raise VerificationInputError(f"缺少输入项：{key}")
        return None
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list) or not value:
        raise VerificationInputError(f"{key} 必须是非空数组")
    return value


def _mapping(inputs: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = inputs.get(key)
    if not isinstance(value, Mapping):
        raise VerificationInputError(f"缺少输入项：{key}")
    return dict(value)


def _parse(value: Any) -> sympy.Expr:
    from app.main import parse_math_expression

    return parse_math_expression(str(value))


def _symbol(value: Any) -> sympy.Symbol:
    from app.main import parse_symbol

    return parse_symbol(str(value))


def _symbols(values: Sequence[Any]) -> list[sympy.Symbol]:
    return [_symbol(value) for value in values]


def _vector(values: Sequence[Any]) -> Matrix:
    return Matrix([_parse(value) for value in values])


def _result_text(calculation: Mapping[str, Any]) -> str:
    return str(calculation.get("result") or "").strip()


def _comparison_check(
    expected: Any,
    actual_text: str,
    *,
    name: str = "result_matches_recomputation",
    detail: str = "使用原始条件独立复算并比较结果",
) -> dict[str, Any]:
    try:
        actual = _parse_result(actual_text)
        passed = _objects_equal(expected, actual)
    except Exception as exc:
        return verification_check(name, False, f"结果无法解析比较：{exc}")
    return verification_check(name, passed, detail)


def _parse_result(value: str) -> Any:
    text = str(value).strip()
    if not text:
        raise ValueError("结果为空")
    local_dict: dict[str, Any] = {}
    for name in ("x", "y", "z", "t", "n", "u", "v", "r", "theta", "rho", "phi"):
        local_dict[name] = sympy.Symbol(name)
    for index in range(1, 5):
        local_dict[f"C{index}"] = sympy.Symbol(f"C{index}")
    for name in ("y", "u", "v"):
        local_dict[f"{name}_function"] = Function(name)
        if f"{name}(" in text:
            local_dict[name] = Function(name)
    local_dict.update(
        {
            "Matrix": Matrix,
            "Eq": Eq,
        }
    )
    return sympy.sympify(text, locals=local_dict, evaluate=False)


def _objects_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, str):
        return isinstance(actual, str) and expected.strip() == actual.strip()
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping) or len(expected) != len(actual):
            return False
        actual_by_name = {str(key): value for key, value in actual.items()}
        return all(
            str(key) in actual_by_name
            and _objects_equal(value, actual_by_name[str(key)])
            for key, value in expected.items()
        )
    if isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(expected) != len(actual):
            return False
        return all(
            _objects_equal(left, right)
            for left, right in zip(expected, actual, strict=True)
        )
    if isinstance(expected, MatrixBase):
        if not isinstance(actual, MatrixBase) or expected.shape != actual.shape:
            return False
        return all(
            _expressions_equal(left, right)
            for left, right in zip(expected, actual, strict=True)
        )
    if isinstance(expected, Eq):
        return (
            isinstance(actual, Eq)
            and _expressions_equal(expected.lhs, actual.lhs)
            and _expressions_equal(expected.rhs, actual.rhs)
        )
    if isinstance(expected, sympy.Basic):
        return isinstance(actual, sympy.Basic) and _expressions_equal(expected, actual)
    return expected == actual


def _expressions_equal(left: Any, right: Any) -> bool:
    try:
        difference = simplify(left - right)
    except Exception:
        try:
            return bool(left.equals(right))
        except Exception:
            return False
    if difference in {sympy.nan, sympy.zoo}:
        return False
    return bool(difference == 0 or difference.is_zero is True)


def _has_incomplete_marker(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "Integral(",
            "Derivative(",
            "Limit(",
            "Sum(",
            "Product(",
            "nan",
            "zoo",
        )
    )


def _point_substitutions(
    point: Sequence[Any],
    symbols: Sequence[sympy.Symbol],
) -> dict[sympy.Symbol, sympy.Expr]:
    if len(point) != len(symbols):
        raise VerificationInputError("point 维数与 variables 不一致")
    return {
        symbol: _parse(value)
        for symbol, value in zip(symbols, point, strict=True)
    }


# Limits


@_register("limits", "limit")
def _verify_limit(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    point = _parse(_text(inputs, "point", required=False, default="0"))
    direction = _text(inputs, "direction", required=False)
    if direction not in {None, "+", "-"}:
        raise VerificationInputError("direction 只能是 +、- 或留空")
    if direction in {"+", "-"}:
        expected = Limit(expression, variable, point, direction).doit()
    else:
        expected = Limit(expression, variable, point).doit()
    checks = [
        verification_check(
            "limit_complete",
            not expected.has(Limit),
            "极限必须完成求值",
        )
    ]
    checks.append(_comparison_check(expected, _result_text(calculation)))
    return checks


@_register("limits", "sequence_limit")
def _verify_sequence_limit(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="n"))
    expected = Limit(expression, variable, sympy.oo).doit()
    checks = [
        verification_check(
            "sequence_limit_complete",
            not expected.has(Limit),
            "数列极限必须完成求值",
        )
    ]
    checks.append(_comparison_check(expected, _result_text(calculation)))
    return checks


def _verified_infinitesimal_order(
    expression: sympy.Expr,
    variable: sympy.Symbol,
    point: sympy.Expr,
) -> tuple[int, sympy.Expr]:
    shifted = simplify(expression.subs(variable, variable + point))
    value = Limit(shifted, variable, 0).doit()
    if value.is_zero is not True:
        raise VerificationInputError(f"{expression} 在给定点不是无穷小")

    for order in range(0, 17):
        quotient = Limit(
            shifted / variable**order,
            variable,
            0,
        ).doit()
        if (
            quotient.is_finite is True
            and quotient.is_zero is False
            and quotient not in {sympy.nan, sympy.zoo}
        ):
            return order, simplify(quotient)
    raise VerificationInputError(f"{expression} 的无穷小阶数无法独立确定")


@_register("limits", "infinitesimal_comparison")
def _verify_infinitesimal_comparison(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    variable = _symbol(_text(inputs, "variable"))
    point = _parse(_text(inputs, "point"))
    relation = _text(
        inputs,
        "kind",
        required=False,
        default="high_order",
    )
    if relation not in {"high_order", "low_order"}:
        raise VerificationInputError("kind 只能是 high_order 或 low_order")
    options = _mapping(inputs, "options")
    if set(options) != {"A", "B", "C", "D"}:
        raise VerificationInputError("options 必须完整包含 A、B、C、D")

    expected_options: list[dict[str, Any]] = []
    for label in sorted(options):
        expression = _parse(options[label])
        order, coefficient = _verified_infinitesimal_order(
            expression,
            variable,
            point,
        )
        expected_options.append(
            {
                "label": label,
                "expression": str(expression),
                "order": order,
                "leading_coefficient": str(coefficient),
            }
        )

    target_order = (
        max(item["order"] for item in expected_options)
        if relation == "high_order"
        else min(item["order"] for item in expected_options)
    )
    candidates = [
        item["label"]
        for item in expected_options
        if item["order"] == target_order
    ]
    relation_text = "高阶" if relation == "high_order" else "低阶"
    checks = [
        verification_check(
            "unique_infinitesimal_answer",
            len(candidates) == 1,
            f"{relation_text}无穷小必须有且只有一个选项",
        )
    ]
    if len(candidates) != 1:
        return checks

    expected_selected = candidates[0]
    expected_orders = {
        item["label"]: item["order"]
        for item in expected_options
    }
    details = calculation.get("details")
    details_mapping = details if isinstance(details, Mapping) else {}
    checks.extend(
        [
            verification_check(
                "selected_option_matches",
                _result_text(calculation) == expected_selected,
                "最终选项必须与独立重算结果一致",
            ),
            verification_check(
                "option_orders_match",
                _objects_equal(expected_orders, details_mapping.get("orders")),
                "A-D 每一项的无穷小阶数必须与独立复算一致",
            ),
            verification_check(
                "option_derivations_match",
                _objects_equal(
                    expected_options,
                    details_mapping.get("options"),
                ),
                "逐项首项系数和阶数必须与独立复算一致",
            ),
            verification_check(
                "selected_detail_matches",
                details_mapping.get("selected") == expected_selected,
            ),
            verification_check(
                "target_order_matches",
                details_mapping.get("target_order") == target_order,
            ),
        ]
    )
    return checks


# Derivatives and derivative applications


def _verify_derivative_order(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
    *,
    default_order: int = 1,
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    order = _integer(inputs, "order", default=default_order)
    if order < 1 or order > 20:
        raise VerificationInputError("order 必须在 1 到 20 之间")
    expected = diff(expression, variable, order)
    return [
        verification_check("derivative_order", True, f"独立按 {order} 阶导数复算"),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("derivatives", "derivative")
def _verify_derivative(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return _verify_derivative_order(inputs, calculation)


@_register("derivatives", "higher_derivative")
def _verify_higher_derivative(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return _verify_derivative_order(inputs, calculation)


@_register("derivatives", "differential")
def _verify_differential(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    differential_symbol = _symbol(
        _text(
            inputs,
            "differential",
            required=False,
            default=f"d{variable}",
        )
    )
    expected = simplify(diff(expression, variable)) * differential_symbol
    return [_comparison_check(expected, _result_text(calculation))]


def _line_equation(
    inputs: Mapping[str, Any],
    *,
    normal: bool,
) -> Eq:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    point = _parse(_text(inputs, "point"))
    slope = simplify(diff(expression, variable).subs(variable, point))
    value = simplify(expression.subs(variable, point))
    if normal and slope == 0:
        return Eq(variable, point)
    if normal:
        slope = simplify(-1 / slope)
    return Eq(sympy.Symbol("y"), expand(slope * (variable - point) + value))


@_register("derivatives", "tangent")
def _verify_tangent(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected = _line_equation(inputs, normal=False)
    return [
        verification_check("tangent_point", True, "切点由原始函数和给定点复算"),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("derivatives", "normal")
def _verify_normal(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected = _line_equation(inputs, normal=True)
    return [
        verification_check("normal_slope_relation", True, "法线斜率按负倒数独立复算"),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("derivatives", "mean_value")
def _verify_mean_value(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    lower = _parse(_text(inputs, "lower"))
    upper = _parse(_text(inputs, "upper"))
    if simplify(upper - lower) == 0:
        raise VerificationInputError("区间端点不能相同")
    average_slope = simplify(
        (expression.subs(variable, upper) - expression.subs(variable, lower))
        / (upper - lower)
    )
    expected = solve(Eq(diff(expression, variable), average_slope), variable)
    candidate_check = all(
        _expressions_equal(diff(expression, variable).subs(variable, point), average_slope)
        for point in expected
    )
    return [
        verification_check("mean_value_equation", candidate_check),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("derivatives", "critical_points")
def _verify_critical_points(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    expected = solve(diff(expression, variable), variable)
    return [
        _comparison_check(expected, _result_text(calculation)),
        verification_check(
            "critical_point_residual",
            all(
                _expressions_equal(diff(expression, variable).subs(variable, point), 0)
                for point in expected
            ),
        ),
    ]


@_register("derivatives", "monotonicity")
def _verify_monotonicity(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    derivative = simplify(diff(expression, variable))
    expected = {
        "derivative": derivative,
        "critical_points": solve(derivative, variable),
    }
    return [_comparison_check(expected, _result_text(calculation))]


def _verified_real_roots(
    expression: sympy.Expr,
    variable: sympy.Symbol,
    *,
    field: str,
) -> list[sympy.Expr]:
    roots = sympy.solveset(expression, variable, domain=sympy.S.Reals)
    if roots is sympy.S.EmptySet:
        return []
    if not isinstance(roots, sympy.FiniteSet):
        raise VerificationInputError(f"{field} 的实根不是有限个")
    values = list(roots)
    if any(root.is_real is not True or root.is_infinite for root in values):
        raise VerificationInputError(f"{field} 含有不可排序的实根")
    try:
        return sorted(values, key=lambda root: float(sympy.N(root, 30)))
    except Exception as exc:
        raise VerificationInputError(f"{field} 的实根无法排序") from exc


def _verified_interval_sign(
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower: sympy.Expr,
    upper: sympy.Expr,
) -> int:
    if lower == -sympy.oo:
        sample = sympy.N(upper, 30) - 1
    elif upper == sympy.oo:
        sample = sympy.N(lower, 30) + 1
    else:
        sample = (lower + upper) / 2
    value = sympy.N(expression.subs(variable, sample), 30)
    if value.is_positive:
        return 1
    if value.is_negative:
        return -1
    if value.is_zero:
        return 0
    raise VerificationInputError("区间内导数符号无法独立判断")


def _verified_sign_intervals(
    expression: sympy.Expr,
    variable: sympy.Symbol,
    roots: Sequence[sympy.Expr],
) -> list[tuple[sympy.Expr, sympy.Expr, int]]:
    boundaries = [-sympy.oo, *roots, sympy.oo]
    return [
        (
            lower,
            upper,
            _verified_interval_sign(expression, variable, lower, upper),
        )
        for lower, upper in zip(boundaries, boundaries[1:])
    ]


def _verified_curve_details(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> dict[str, Any]:
    first = simplify(diff(expression, variable))
    second = simplify(diff(expression, variable, 2))
    first_roots = _verified_real_roots(first, variable, field="一阶导数")
    second_roots = _verified_real_roots(second, variable, field="二阶导数")
    first_signs = _verified_sign_intervals(first, variable, first_roots)
    second_signs = _verified_sign_intervals(second, variable, second_roots)

    increasing_intervals = [
        f"({lower}, {upper})"
        for lower, upper, sign in first_signs
        if sign > 0
    ]
    decreasing_intervals = [
        f"({lower}, {upper})"
        for lower, upper, sign in first_signs
        if sign < 0
    ]
    second_positive_intervals = [
        f"({lower}, {upper})"
        for lower, upper, sign in second_signs
        if sign > 0
    ]
    second_negative_intervals = [
        f"({lower}, {upper})"
        for lower, upper, sign in second_signs
        if sign < 0
    ]

    local_maxima: list[dict[str, str]] = []
    local_minima: list[dict[str, str]] = []
    for index, root in enumerate(first_roots):
        left_sign = first_signs[index][2]
        right_sign = first_signs[index + 1][2]
        value = str(simplify(expression.subs(variable, root)))
        if left_sign > 0 and right_sign < 0:
            local_maxima.append(
                {"x": str(root), "y": value, "kind": "极大值"}
            )
        elif left_sign < 0 and right_sign > 0:
            local_minima.append(
                {"x": str(root), "y": value, "kind": "极小值"}
            )

    inflection_points: list[dict[str, str]] = []
    for index, root in enumerate(second_roots):
        left_sign = second_signs[index][2]
        right_sign = second_signs[index + 1][2]
        if left_sign * right_sign < 0:
            inflection_points.append(
                {
                    "x": str(root),
                    "y": str(simplify(expression.subs(variable, root))),
                }
            )

    return {
        "expression": str(expression),
        "variable": str(variable),
        "first_derivative": str(first),
        "first_derivative_roots": [str(root) for root in first_roots],
        "increasing_intervals": increasing_intervals,
        "decreasing_intervals": decreasing_intervals,
        "local_maxima": local_maxima,
        "local_minima": local_minima,
        "local_max": local_maxima[0] if local_maxima else None,
        "local_min": local_minima[0] if local_minima else None,
        "second_derivative": str(second),
        "second_derivative_roots": [str(root) for root in second_roots],
        "second_positive_intervals": second_positive_intervals,
        "second_negative_intervals": second_negative_intervals,
        "inflection_points": inflection_points,
    }


def _verified_curve_summary(details: Mapping[str, Any]) -> str:
    parts: list[str] = []
    if details["increasing_intervals"]:
        parts.append(
            "单调递增区间：" + "、".join(details["increasing_intervals"])
        )
    if details["decreasing_intervals"]:
        parts.append(
            "单调递减区间：" + "、".join(details["decreasing_intervals"])
        )
    if details["local_maxima"]:
        parts.append(
            "极大值："
            + "；".join(
                f"f({item['x']})={item['y']}"
                for item in details["local_maxima"]
            )
        )
    if details["local_minima"]:
        parts.append(
            "极小值："
            + "；".join(
                f"f({item['x']})={item['y']}"
                for item in details["local_minima"]
            )
        )
    if details["second_positive_intervals"]:
        parts.append(
            "二阶导数为正区间："
            + "、".join(details["second_positive_intervals"])
        )
    if details["second_negative_intervals"]:
        parts.append(
            "二阶导数为负区间："
            + "、".join(details["second_negative_intervals"])
        )
    if details["inflection_points"]:
        parts.append(
            "拐点："
            + "、".join(
                f"({item['x']}, {item['y']})"
                for item in details["inflection_points"]
            )
        )
    if parts:
        return "；".join(parts) + "。"
    return "函数在实数域上无对应变化区间或极值点。"


@_register("derivatives", "curve_analysis")
def _verify_curve_analysis(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    expected = _verified_curve_details(expression, variable)
    expected_summary = _verified_curve_summary(expected)
    details = calculation.get("details")
    actual = details if isinstance(details, Mapping) else {}
    keys = (
        "first_derivative",
        "first_derivative_roots",
        "increasing_intervals",
        "decreasing_intervals",
        "local_maxima",
        "local_minima",
        "local_max",
        "local_min",
        "second_derivative",
        "second_derivative_roots",
        "second_positive_intervals",
        "second_negative_intervals",
        "inflection_points",
    )
    checks = [
        verification_check(
            "curve_summary_matches",
            _result_text(calculation) == expected_summary,
            "最终摘要必须与独立重算的完整曲线分析一致",
        )
    ]
    checks.extend(
        verification_check(
            f"{key}_matches",
            _objects_equal(expected[key], actual.get(key)),
            f"{key} 必须与独立复算一致",
        )
        for key in keys
    )
    first = _parse(expected["first_derivative"])
    second = _parse(expected["second_derivative"])
    checks.append(
        verification_check(
            "derivative_roots_residual",
            all(
                _expressions_equal(
                    first.subs(variable, _parse(root)),
                    0,
                )
                for root in expected["first_derivative_roots"]
            )
            and all(
                _expressions_equal(
                    second.subs(variable, _parse(root)),
                    0,
                )
                for root in expected["second_derivative_roots"]
            ),
            "把一、二阶导数的实根分别代回后必须为零",
        )
    )
    return checks


@_register("derivatives", "extrema")
def _verify_extrema(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    first = diff(expression, variable)
    second = diff(expression, variable, 2)
    expected = []
    for point in solve(first, variable):
        second_value = simplify(second.subs(variable, point))
        if second_value.is_positive:
            kind = "极小值"
        elif second_value.is_negative:
            kind = "极大值"
        else:
            kind = "需进一步判断"
        expected.append(
            {
                "x": point,
                "y": simplify(expression.subs(variable, point)),
                "kind": kind,
            }
        )
    residual_passed = all(
        _expressions_equal(first.subs(variable, item["x"]), 0)
        and _expressions_equal(expression.subs(variable, item["x"]), item["y"])
        for item in expected
    )
    return [
        verification_check("extrema_residual", residual_passed),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("derivatives", "taylor")
def _verify_taylor(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    point = _parse(_text(inputs, "point", required=False, default="0"))
    order = _integer(inputs, "order", default=5)
    if order < 0 or order > 20:
        raise VerificationInputError("order 必须在 0 到 20 之间")
    expected = expression.series(variable, point, order + 1).removeO()
    return [_comparison_check(expected, _result_text(calculation))]


@_register("derivatives", "curvature")
def _verify_curvature(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    first = diff(expression, variable)
    second = diff(expression, variable, 2)
    expected = Abs(second) / (1 + first**2) ** sympy.Rational(3, 2)
    point = _text(inputs, "point", required=False)
    if point is not None:
        expected = simplify(expected.subs(variable, _parse(point)))
    return [_comparison_check(simplify(expected), _result_text(calculation))]


@_register("derivatives", "parametric_derivative")
def _verify_parametric_derivative(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    x_expression = _parse(_text(inputs, "x_expression"))
    y_expression = _parse(_text(inputs, "y_expression"))
    parameter = _symbol(_text(inputs, "parameter", required=False, default="t"))
    dx_dt = simplify(diff(x_expression, parameter))
    if dx_dt == 0:
        raise VerificationInputError("dx/dt 不能为零")
    expected = simplify(diff(y_expression, parameter) / dx_dt)
    return [
        verification_check("parameter_derivative_direction", dx_dt != 0),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("derivatives", "parametric_tangent_normal")
def _verify_parametric_tangent_normal(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    x_expression = _parse(_text(inputs, "x_expression"))
    y_expression = _parse(_text(inputs, "y_expression"))
    parameter = _symbol(_text(inputs, "parameter", required=False, default="t"))
    point_text = _text(inputs, "parameter_value", required=False)
    if point_text is None:
        point_text = _text(inputs, "point", required=False)
    if point_text is None:
        raise VerificationInputError("缺少输入项：parameter_value")
    parameter_value = _parse(point_text)

    dx_value = simplify(
        diff(x_expression, parameter).subs(parameter, parameter_value)
    )
    dy_value = simplify(
        diff(y_expression, parameter).subs(parameter, parameter_value)
    )
    if dx_value == 0 and dy_value == 0:
        raise VerificationInputError("参数点处导数向量退化")
    point_x = simplify(x_expression.subs(parameter, parameter_value))
    point_y = simplify(y_expression.subs(parameter, parameter_value))
    x_symbol = sympy.Symbol("x")
    if dx_value == 0:
        tangent_kind = "vertical"
        tangent_slope = None
        normal_slope = sympy.Integer(0)
        tangent_equation = f"x = {point_x}"
        normal_equation = f"y = {point_y}"
    elif dy_value == 0:
        tangent_kind = "horizontal"
        tangent_slope = sympy.Integer(0)
        normal_slope = None
        tangent_equation = f"y = {point_y}"
        normal_equation = f"x = {point_x}"
    else:
        tangent_kind = "slope"
        tangent_slope = simplify(dy_value / dx_value)
        normal_slope = simplify(-dx_value / dy_value)
        tangent_equation = (
            f"y = {expand(tangent_slope * (x_symbol - point_x) + point_y)}"
        )
        normal_equation = (
            f"y = {expand(normal_slope * (x_symbol - point_x) + point_y)}"
        )

    details = calculation.get("details")
    details = details if isinstance(details, Mapping) else {}
    expected_details = {
        "point_x": str(point_x),
        "point_y": str(point_y),
        "tangent_kind": tangent_kind,
        "tangent_slope": (
            "不存在" if tangent_slope is None else str(tangent_slope)
        ),
        "normal_slope": "不存在" if normal_slope is None else str(normal_slope),
        "tangent_result": tangent_equation,
        "normal_result": normal_equation,
    }
    details_passed = all(
        str(details.get(key) or "").strip() == value
        for key, value in expected_details.items()
    )
    result_text = _result_text(calculation)
    result_passed = (
        tangent_equation in result_text
        and normal_equation in result_text
        and f"({point_x}, {point_y})" in result_text
    )
    geometry_passed = True
    if tangent_kind == "slope":
        geometry_passed = (
            tangent_slope is not None
            and normal_slope is not None
            and _expressions_equal(tangent_slope * normal_slope + 1, 0)
            and _expressions_equal(dy_value - tangent_slope * dx_value, 0)
        )
    elif tangent_kind == "horizontal":
        geometry_passed = _expressions_equal(dy_value, 0) and normal_slope is None
    else:
        geometry_passed = _expressions_equal(dx_value, 0) and normal_slope == 0
    return [
        verification_check("tangent_point", True, "参数值代回参数方程核对切点"),
        verification_check("tangent_direction", geometry_passed),
        verification_check(
            "normal_slope_relation",
            details_passed and geometry_passed,
        ),
        verification_check("verified_result_text", result_passed),
    ]


# Integrals


@_register("integrals", "indefinite")
def _verify_indefinite(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    expected = integrate(expression, variable)
    actual = _parse_result(_result_text(calculation))
    return [
        verification_check(
            "integral_derivative",
            isinstance(actual, sympy.Basic)
            and _expressions_equal(diff(actual, variable), expression),
            "对积分结果重新求导并与被积函数比较",
        ),
        _comparison_check(simplify(expected), _result_text(calculation)),
    ]


def _verify_definite(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    lower = _parse(_text(inputs, "lower"))
    upper = _parse(_text(inputs, "upper"))
    expected = integrate(expression, (variable, lower, upper))
    return [
        verification_check("integration_bounds", True, "上下限均从原始输入读取"),
        _comparison_check(simplify(expected), _result_text(calculation)),
    ]


@_register("integrals", "definite")
def _verify_definite_integral(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return _verify_definite(inputs, calculation)


@_register("integrals", "improper")
def _verify_improper(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return _verify_definite(inputs, calculation)


@_register("integrals", "area_between")
def _verify_area_between(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    upper_expression = _parse(_text(inputs, "upper_expression"))
    lower_expression = _parse(_text(inputs, "lower_expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    lower = _parse(_text(inputs, "lower"))
    upper = _parse(_text(inputs, "upper"))
    expected = simplify(
        integrate(
            simplify(upper_expression - lower_expression),
            (variable, lower, upper),
        )
    )
    return [_comparison_check(expected, _result_text(calculation))]


@_register("integrals", "volume_revolution")
def _verify_volume_revolution(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    lower = _parse(_text(inputs, "lower"))
    upper = _parse(_text(inputs, "upper"))
    expected = simplify(
        integrate(sympy.pi * expression**2, (variable, lower, upper))
    )
    return [_comparison_check(expected, _result_text(calculation))]


@_register("integrals", "arc_length")
def _verify_arc_length(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    lower = _parse(_text(inputs, "lower"))
    upper = _parse(_text(inputs, "upper"))
    derivative = simplify(diff(expression, variable))
    expected = simplify(
        integrate(sqrt(1 + derivative**2), (variable, lower, upper))
    )
    return [_comparison_check(expected, _result_text(calculation))]


# Differential equations


@_register("differential_equations", "dsolve")
def _verify_dsolve(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    from app.chapter_solvers import _as_solution_rhs, _parse_equation

    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    function = Function(_text(inputs, "function", required=False, default="y"))
    equation = _parse_equation(_text(inputs, "equation"), function, variable)
    expected = sympy.dsolve(equation, function(variable))
    expected_rhs = _as_solution_rhs(expected, function(variable))
    actual = _parse_result(_result_text(calculation))
    if isinstance(actual, (list, tuple)):
        if len(actual) != 1:
            return [verification_check("single_solution_equation", False)]
        actual = actual[0]
    actual_rhs = (
        actual.rhs
        if isinstance(actual, Eq) and actual.lhs == function(variable)
        else None
    )
    return [
        verification_check("ode_solution_equation", actual_rhs is not None),
        verification_check(
            "ode_recomputed",
            actual_rhs is not None
            and _expressions_equal(expected_rhs, actual_rhs),
        ),
    ]


# Vectors


@_register("vectors", "dot")
def _verify_dot(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    left = _vector(_items(inputs, "left") or [])
    right = _vector(_items(inputs, "right") or [])
    if left.rows != right.rows:
        raise VerificationInputError("向量维数不一致")
    return [_comparison_check((left.T * right)[0], _result_text(calculation))]


@_register("vectors", "cross")
def _verify_cross(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    left = _vector(_items(inputs, "left") or [])
    right = _vector(_items(inputs, "right") or [])
    if left.rows != 3 or right.rows != 3:
        raise VerificationInputError("叉积向量必须是三维")
    return [_comparison_check(left.cross(right), _result_text(calculation))]


@_register("vectors", "norm")
def _verify_norm(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    vector = _vector(_items(inputs, "vector") or [])
    expected = simplify(sqrt(sum(component**2 for component in vector)))
    return [_comparison_check(expected, _result_text(calculation))]


@_register("vectors", "angle")
def _verify_angle(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    left = _vector(_items(inputs, "left") or [])
    right = _vector(_items(inputs, "right") or [])
    if left.rows != right.rows:
        raise VerificationInputError("向量维数不一致")
    denominator = sqrt(sum(component**2 for component in left)) * sqrt(
        sum(component**2 for component in right)
    )
    if denominator == 0:
        raise VerificationInputError("零向量不能定义夹角")
    expected = acos(simplify((left.T * right)[0] / denominator))
    return [_comparison_check(expected, _result_text(calculation))]


@_register("vectors", "distance")
def _verify_distance(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    left = _vector(_items(inputs, "left") or [])
    right = _vector(_items(inputs, "right") or [])
    if left.rows != right.rows:
        raise VerificationInputError("向量维数不一致")
    difference = left - right
    expected = simplify(sqrt(sum(component**2 for component in difference)))
    return [_comparison_check(expected, _result_text(calculation))]


@_register("vectors", "projection")
def _verify_projection(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    left = _vector(_items(inputs, "left") or [])
    right = _vector(_items(inputs, "right") or [])
    if left.rows != right.rows:
        raise VerificationInputError("向量维数不一致")
    denominator = (right.T * right)[0]
    if denominator == 0:
        raise VerificationInputError("不能向零向量投影")
    expected = simplify(((left.T * right)[0] / denominator) * right)
    return [_comparison_check(expected, _result_text(calculation))]


# Multivariable calculus


@_register("multivariable_calculus", "partial")
def _verify_partial(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _items(inputs, "variables") or []
    variable = _symbol(variables[0])
    order = _integer(inputs, "order", default=1)
    if order < 1 or order > 20:
        raise VerificationInputError("order 必须在 1 到 20 之间")
    expected = diff(expression, variable, order)
    point = inputs.get("point")
    if point is not None:
        if not isinstance(point, Mapping):
            raise VerificationInputError("point 必须是对象")
        substitutions = {
            _symbol(name): _parse(value)
            for name, value in point.items()
        }
        missing_symbols = {
            str(symbol)
            for symbol in expression.free_symbols
            if symbol not in substitutions
        }
        if missing_symbols:
            missing_text = "、".join(sorted(missing_symbols))
            raise VerificationInputError(f"取值点缺少变量：{missing_text}")
        expected = simplify(expected.subs(substitutions))
        if expected.free_symbols:
            free_text = "、".join(
                sorted(str(symbol) for symbol in expected.free_symbols)
            )
            raise VerificationInputError(
                f"代入取值点后偏导数仍含自由变量：{free_text}"
            )
    return [_comparison_check(expected, _result_text(calculation))]


@_register("multivariable_calculus", "mixed_partial")
def _verify_mixed_partial(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    expected = expression
    for variable in variables:
        expected = diff(expected, variable)
    return [_comparison_check(expected, _result_text(calculation))]


@_register("multivariable_calculus", "gradient")
def _verify_gradient(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    expected = Matrix([diff(expression, variable) for variable in variables])
    point = _items(inputs, "point", required=False)
    if point is not None:
        substitutions = _point_substitutions(point, variables)
        expected = Matrix(
            [simplify(component.subs(substitutions)) for component in expected]
        )
    return [_comparison_check(expected, _result_text(calculation))]


@_register("multivariable_calculus", "hessian")
def _verify_hessian(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    expected = Matrix(
        [
            [diff(expression, left, right) for right in variables]
            for left in variables
        ]
    )
    return [_comparison_check(simplify(expected), _result_text(calculation))]


@_register("multivariable_calculus", "directional_derivative")
def _verify_directional_derivative(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    substitutions = _point_substitutions(
        _items(inputs, "point") or [],
        variables,
    )
    direction = _vector(_items(inputs, "direction") or [])
    if direction.rows != len(variables):
        raise VerificationInputError("direction 维数不一致")
    direction_norm = sqrt(sum(component**2 for component in direction))
    if direction_norm == 0:
        raise VerificationInputError("方向向量不能为零向量")
    gradient = Matrix(
        [
            simplify(diff(expression, variable).subs(substitutions))
            for variable in variables
        ]
    )
    expected = simplify((gradient.T * direction)[0] / direction_norm)
    return [_comparison_check(expected, _result_text(calculation))]


def _implicit_function(inputs: Mapping[str, Any]) -> tuple[sympy.Expr, sympy.Symbol, sympy.Symbol]:
    equation_text = _text(inputs, "equation")
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    dependent = _symbol(_text(inputs, "dependent", required=False, default="y"))
    if "=" in equation_text:
        left, right = equation_text.split("=", 1)
        function = _parse(left) - _parse(right)
    else:
        function = _parse(equation_text)
    return function, variable, dependent


@_register("multivariable_calculus", "implicit_derivative")
def _verify_implicit_derivative(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    function, variable, dependent = _implicit_function(inputs)
    denominator = diff(function, dependent)
    if simplify(denominator) == 0:
        raise VerificationInputError("隐函数定理条件不满足")
    expected = simplify(-diff(function, variable) / denominator)
    point = _items(inputs, "point", required=False)
    if point is not None:
        substitutions = _point_substitutions(point, [variable, dependent])
        expected = simplify(expected.subs(substitutions))
    return [_comparison_check(expected, _result_text(calculation))]


def _equation_function(value: str) -> sympy.Expr:
    if "=" in value:
        left, right = value.split("=", 1)
        return _parse(left) - _parse(right)
    return _parse(value)


@_register("multivariable_calculus", "system_implicit_derivative")
def _verify_system_implicit_derivative(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    equations = _items(inputs, "equations") or []
    dependents = _symbols(_items(inputs, "dependents") or [])
    if len(equations) != len(dependents):
        raise VerificationInputError("方程个数必须与因变量个数一致")
    variable = _symbol(_text(inputs, "variable", required=False, default="x"))
    target = _symbol(
        _text(
            inputs,
            "dependent",
            required=False,
            default=str(dependents[0]),
        )
    )
    if target not in dependents:
        raise VerificationInputError("dependent 必须是 dependents 中的变量")
    functions = [_equation_function(str(value)) for value in equations]
    jacobian = Matrix(
        [
            [diff(function, dependent) for dependent in dependents]
            for function in functions
        ]
    )
    if simplify(jacobian.det()) == 0:
        raise VerificationInputError("方程组雅可比行列式为零")
    right_hand_side = Matrix([-diff(function, variable) for function in functions])
    derivatives = jacobian.LUsolve(right_hand_side)
    expected = simplify(derivatives[dependents.index(target)])
    return [_comparison_check(expected, _result_text(calculation))]


@_register("multivariable_calculus", "multivariable_extrema")
def _verify_multivariable_extrema(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    if len(variables) != 2:
        raise VerificationInputError("当前多元极值需要两个变量")
    first, second = variables
    points = solve(
        [diff(expression, first), diff(expression, second)],
        variables,
        dict=True,
    )
    expected = []
    for point in points:
        f_xx = simplify(diff(expression, first, 2).subs(point))
        f_yy = simplify(diff(expression, second, 2).subs(point))
        f_xy = simplify(diff(expression, first, second).subs(point))
        determinant = simplify(f_xx * f_yy - f_xy**2)
        if determinant.is_positive and f_xx.is_positive:
            kind = "极小值"
        elif determinant.is_positive and f_xx.is_negative:
            kind = "极大值"
        elif determinant.is_negative:
            kind = "鞍点"
        else:
            kind = "需进一步判断"
        expected.append(
            {
                "point": point,
                "value": simplify(expression.subs(point)),
                "kind": kind,
            }
        )
    stationarity = all(
        _expressions_equal(diff(expression, first).subs(item["point"]), 0)
        and _expressions_equal(diff(expression, second).subs(item["point"]), 0)
        for item in expected
    )
    return [
        verification_check("stationary_point_residual", stationarity),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("multivariable_calculus", "conditional_extrema")
def _verify_conditional_extrema(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    raw_constraints = inputs.get("constraints")
    if raw_constraints is None:
        raw_constraints = [_text(inputs, "constraint")]
    elif isinstance(raw_constraints, str):
        raw_constraints = [
            part.strip()
            for part in raw_constraints.replace(";", "\n").splitlines()
            if part.strip()
        ]
    if not isinstance(raw_constraints, list) or not raw_constraints:
        raise VerificationInputError("缺少 constraints 或 constraint")
    constraints = [_equation_function(str(value)) for value in raw_constraints]
    if len(constraints) >= len(variables):
        raise VerificationInputError("等式约束数量必须少于变量数量")
    lambda_texts = _items(inputs, "lambdas", required=False)
    if lambda_texts:
        lambdas = _symbols(lambda_texts)
    elif len(constraints) == 1:
        lambdas = [
            _symbol(_text(inputs, "lambda", required=False, default="lambda"))
        ]
    else:
        lambdas = [
            _symbol(f"lambda{index}")
            for index in range(1, len(constraints) + 1)
        ]

    lagrangian = expression + sum(
        multiplier * constraint
        for multiplier, constraint in zip(lambdas, constraints, strict=True)
    )
    equations = [diff(lagrangian, variable) for variable in variables] + constraints
    solutions = solve(equations, [*variables, *lambdas], dict=True)
    if not solutions:
        raise VerificationInputError("未找到满足约束的条件驻点")
    expected = []
    for solution in solutions:
        point = {variable: simplify(solution[variable]) for variable in variables}
        lambda_values = {
            multiplier: simplify(solution[multiplier]) for multiplier in lambdas
        }
        substitutions = {**point, **lambda_values}
        jacobian = Matrix(
            [
                [diff(constraint, variable) for variable in variables]
                for constraint in constraints
            ]
        ).subs(substitutions)
        kind = "需进一步判断"
        if jacobian.rank() == len(constraints):
            basis = jacobian.nullspace()
            if basis:
                basis_matrix = Matrix.hstack(*basis)
                hessian = Matrix(
                    [
                        [
                            diff(lagrangian, left, right)
                            for right in variables
                        ]
                        for left in variables
                    ]
                ).subs(substitutions)
                projected = simplify(
                    basis_matrix.T * hessian * basis_matrix
                )
                signs: set[int] = set()
                uncertain = False
                for eigenvalue in projected.eigenvals():
                    eigenvalue = simplify(eigenvalue)
                    if eigenvalue.is_positive:
                        signs.add(1)
                    elif eigenvalue.is_negative:
                        signs.add(-1)
                    elif eigenvalue.is_zero:
                        signs.add(0)
                    else:
                        uncertain = True
                if not uncertain:
                    if signs == {1}:
                        kind = "极小值"
                    elif signs == {-1}:
                        kind = "极大值"
                    elif 1 in signs and -1 in signs:
                        kind = "非极值点"
        item: dict[str, Any] = {
            "point": point,
            "value": simplify(expression.subs(point)),
            "kind": kind,
        }
        if len(lambdas) == 1:
            item["lambda"] = lambda_values[lambdas[0]]
        else:
            item["lambdas"] = lambda_values
        expected.append(item)

    constraint_residual = all(
        all(_expressions_equal(constraint.subs(item["point"]), 0) for constraint in constraints)
        for item in expected
    )
    return [
        verification_check("constraint_residual", constraint_residual),
        _comparison_check(expected, _result_text(calculation)),
    ]


# Multiple integrals


@_register("multiple_integrals", "double")
def _verify_double_integral(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    if len(variables) != 2:
        raise VerificationInputError("二重积分需要两个积分变量")
    first, second = variables
    expected = integrate(
        integrate(
            expression,
            (
                second,
                _parse(_text(inputs, "lower_y")),
                _parse(_text(inputs, "upper_y")),
            ),
        ),
        (
            first,
            _parse(_text(inputs, "lower_x")),
            _parse(_text(inputs, "upper_x")),
        ),
    )
    return [_comparison_check(simplify(expected), _result_text(calculation))]


@_register("multiple_integrals", "double_polar")
def _verify_double_polar(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    radial = _symbol(_text(inputs, "radial_variable", required=False, default="r"))
    angle = _symbol(_text(inputs, "angle_variable", required=False, default="theta"))
    x_symbol, y_symbol = sympy.symbols("x y")
    expression = expression.subs(
        {
            x_symbol: radial * sympy.cos(angle),
            y_symbol: radial * sympy.sin(angle),
        }
    )
    expected = integrate(
        integrate(
            expression * radial,
            (angle, _parse(_text(inputs, "lower_theta")), _parse(_text(inputs, "upper_theta"))),
        ),
        (radial, _parse(_text(inputs, "lower_r")), _parse(_text(inputs, "upper_r"))),
    )
    return [_comparison_check(simplify(expected), _result_text(calculation))]


@_register("multiple_integrals", "triple")
def _verify_triple_integral(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variables = _symbols(_items(inputs, "variables") or [])
    if len(variables) != 3:
        raise VerificationInputError("三重积分需要三个积分变量")
    expected = expression
    for key, variable in zip(("x", "y", "z"), variables, strict=True):
        expected = integrate(
            expected,
            (
                variable,
                _parse(_text(inputs, f"lower_{key}")),
                _parse(_text(inputs, f"upper_{key}")),
            ),
        )
    return [_comparison_check(simplify(expected), _result_text(calculation))]


@_register("multiple_integrals", "triple_cylindrical")
def _verify_triple_cylindrical(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    radial = _symbol(_text(inputs, "radial_variable", required=False, default="r"))
    angle = _symbol(_text(inputs, "angle_variable", required=False, default="theta"))
    height = _symbol(_text(inputs, "height_variable", required=False, default="z"))
    x_symbol, y_symbol, z_symbol = sympy.symbols("x y z")
    expression = expression.subs(
        {
            x_symbol: radial * sympy.cos(angle),
            y_symbol: radial * sympy.sin(angle),
            z_symbol: height,
        }
    )
    expected = integrate(
        integrate(
            integrate(
                expression * radial,
                (height, _parse(_text(inputs, "lower_z")), _parse(_text(inputs, "upper_z"))),
            ),
            (angle, _parse(_text(inputs, "lower_theta")), _parse(_text(inputs, "upper_theta"))),
        ),
        (radial, _parse(_text(inputs, "lower_r")), _parse(_text(inputs, "upper_r"))),
    )
    return [_comparison_check(simplify(expected), _result_text(calculation))]


@_register("multiple_integrals", "triple_spherical")
def _verify_triple_spherical(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    radial = _symbol(_text(inputs, "radial_variable", required=False, default="rho"))
    polar = _symbol(_text(inputs, "polar_variable", required=False, default="phi"))
    azimuthal = _symbol(_text(inputs, "azimuthal_variable", required=False, default="theta"))
    x_symbol, y_symbol, z_symbol = sympy.symbols("x y z")
    expression = expression.subs(
        {
            x_symbol: radial * sympy.sin(polar) * sympy.cos(azimuthal),
            y_symbol: radial * sympy.sin(polar) * sympy.sin(azimuthal),
            z_symbol: radial * sympy.cos(polar),
        }
    )
    expected = integrate(
        integrate(
            integrate(
                expression * radial**2 * sympy.sin(polar),
                (
                    azimuthal,
                    _parse(_text(inputs, "lower_theta")),
                    _parse(_text(inputs, "upper_theta")),
                ),
            ),
            (polar, _parse(_text(inputs, "lower_phi")), _parse(_text(inputs, "upper_phi"))),
        ),
        (radial, _parse(_text(inputs, "lower_rho")), _parse(_text(inputs, "upper_rho"))),
    )
    return [_comparison_check(simplify(expected), _result_text(calculation))]


# Line and surface integrals


def _parameterized_curve(
    inputs: Mapping[str, Any],
) -> tuple[
    sympy.Symbol,
    sympy.Expr,
    sympy.Expr,
    dict[sympy.Symbol, sympy.Expr],
]:
    parameter = _symbol(_text(inputs, "parameter", required=False, default="t"))
    components = _mapping(inputs, "components")
    substitutions = {
        _symbol(name): _parse(value) for name, value in components.items()
    }
    return (
        parameter,
        _parse(_text(inputs, "lower")),
        _parse(_text(inputs, "upper")),
        substitutions,
    )


@_register("line_surface_integrals", "line_scalar")
def _verify_line_scalar(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    parameter, lower, upper, substitutions = _parameterized_curve(inputs)
    speed = sqrt(
        sum(diff(value, parameter) ** 2 for value in substitutions.values())
    )
    expected = simplify(
        integrate(
            simplify(expression.subs(substitutions) * speed),
            (parameter, lower, upper),
        )
    )
    return [_comparison_check(expected, _result_text(calculation))]


@_register("line_surface_integrals", "line_vector")
def _verify_line_vector(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    vector_values = _items(inputs, "vector_field") or []
    parameter, lower, upper, substitutions = _parameterized_curve(inputs)
    if len(vector_values) != len(substitutions):
        raise VerificationInputError("vector_field 维数必须与 components 一致")
    integrand = 0
    for name, raw_component in zip(
        substitutions,
        vector_values,
        strict=True,
    ):
        integrand += (
            _parse(raw_component).subs(substitutions)
            * diff(substitutions[name], parameter)
        )
    expected = simplify(
        integrate(simplify(integrand), (parameter, lower, upper))
    )
    return [_comparison_check(expected, _result_text(calculation))]


def _explicit_curve(
    inputs: Mapping[str, Any],
) -> tuple[sympy.Symbol, sympy.Symbol, sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr]:
    variables = _items(inputs, "variables", required=False) or ["x", "y"]
    if len(variables) != 2:
        raise VerificationInputError("显式曲线需要 x、y 两个变量")
    independent, dependent = _symbols(variables)
    y_expression = _parse(_text(inputs, "y_expression"))
    return (
        independent,
        dependent,
        y_expression,
        simplify(diff(y_expression, independent)),
        _parse(_text(inputs, "lower")),
        _parse(_text(inputs, "upper")),
    )


@_register("line_surface_integrals", "line_scalar_explicit")
def _verify_line_scalar_explicit(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    (
        independent,
        dependent,
        y_expression,
        y_prime,
        lower,
        upper,
    ) = _explicit_curve(inputs)
    integrand = simplify(
        expression.subs(dependent, y_expression) * sqrt(1 + y_prime**2)
    )
    expected = simplify(integrate(integrand, (independent, lower, upper)))
    return [_comparison_check(expected, _result_text(calculation))]


@_register("line_surface_integrals", "line_vector_explicit")
def _verify_line_vector_explicit(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    vector_values = _items(inputs, "vector_field") or []
    if len(vector_values) != 2:
        raise VerificationInputError("显式曲线上的向量场必须是二维")
    (
        independent,
        dependent,
        y_expression,
        y_prime,
        lower,
        upper,
    ) = _explicit_curve(inputs)
    left = _parse(vector_values[0]).subs(dependent, y_expression)
    right = _parse(vector_values[1]).subs(dependent, y_expression)
    expected = simplify(
        integrate(
            simplify(left + right * y_prime),
            (independent, lower, upper),
        )
    )
    return [_comparison_check(expected, _result_text(calculation))]


def _parameterized_surface(
    inputs: Mapping[str, Any],
) -> tuple[
    tuple[sympy.Symbol, sympy.Symbol],
    tuple[sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr],
    dict[sympy.Symbol, sympy.Expr],
]:
    parameter_values = _items(inputs, "parameters", required=False) or ["u", "v"]
    if len(parameter_values) != 2:
        raise VerificationInputError("曲面参数必须有两个")
    parameters = (_symbol(parameter_values[0]), _symbol(parameter_values[1]))
    components = _mapping(inputs, "components")
    substitutions = {
        _symbol(name): _parse(value) for name, value in components.items()
    }
    return (
        parameters,
        (
            _parse(_text(inputs, "u_lower")),
            _parse(_text(inputs, "u_upper")),
            _parse(_text(inputs, "v_lower")),
            _parse(_text(inputs, "v_upper")),
        ),
        substitutions,
    )


def _surface_cross(
    substitutions: Mapping[sympy.Symbol, sympy.Expr],
    parameters: tuple[sympy.Symbol, sympy.Symbol],
) -> Matrix:
    if len(substitutions) != 3:
        raise VerificationInputError("曲面参数化需要 x、y、z 三个分量")
    u, v = parameters
    names = list(substitutions)
    r_u = Matrix([diff(substitutions[name], u) for name in names])
    r_v = Matrix([diff(substitutions[name], v) for name in names])
    return r_u.cross(r_v)


@_register("line_surface_integrals", "surface_scalar")
def _verify_surface_scalar(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    parameters, bounds, substitutions = _parameterized_surface(inputs)
    cross = _surface_cross(substitutions, parameters)
    area_factor = sqrt(sum(component**2 for component in cross))
    u, v = parameters
    u_lower, u_upper, v_lower, v_upper = bounds
    expected = simplify(
        integrate(
            integrate(
                simplify(expression.subs(substitutions) * area_factor),
                (v, v_lower, v_upper),
            ),
            (u, u_lower, u_upper),
        )
    )
    return [_comparison_check(expected, _result_text(calculation))]


@_register("line_surface_integrals", "flux")
def _verify_flux(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    vector_values = _items(inputs, "vector_field") or []
    parameters, bounds, substitutions = _parameterized_surface(inputs)
    if len(vector_values) != len(substitutions):
        raise VerificationInputError("vector_field 维数不一致")
    field = Matrix(
        [_parse(value).subs(substitutions) for value in vector_values]
    )
    cross = _surface_cross(substitutions, parameters)
    integrand = simplify((field.T * cross)[0])
    u, v = parameters
    u_lower, u_upper, v_lower, v_upper = bounds
    expected = simplify(
        integrate(
            integrate(integrand, (v, v_lower, v_upper)),
            (u, u_lower, u_upper),
        )
    )
    return [_comparison_check(expected, _result_text(calculation))]


def _explicit_surface(
    inputs: Mapping[str, Any],
) -> tuple[
    sympy.Symbol,
    sympy.Symbol,
    sympy.Expr,
    sympy.Expr,
    sympy.Expr,
    tuple[sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr],
]:
    variable_values = _items(inputs, "variables", required=False) or ["x", "y"]
    if len(variable_values) != 2:
        raise VerificationInputError("显式曲面需要两个自变量")
    first, second = _symbols(variable_values)
    z_expression = _parse(_text(inputs, "z_expression"))
    return (
        first,
        second,
        z_expression,
        simplify(diff(z_expression, first)),
        simplify(diff(z_expression, second)),
        (
            _parse(_text(inputs, "x_lower")),
            _parse(_text(inputs, "x_upper")),
            _parse(_text(inputs, "y_lower")),
            _parse(_text(inputs, "y_upper")),
        ),
    )


@_register("line_surface_integrals", "surface_scalar_explicit")
def _verify_surface_scalar_explicit(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    (
        first,
        second,
        z_expression,
        first_partial,
        second_partial,
        bounds,
    ) = _explicit_surface(inputs)
    integrand = expression.subs(sympy.Symbol("z"), z_expression) * sqrt(
        1 + first_partial**2 + second_partial**2
    )
    first_lower, first_upper, second_lower, second_upper = bounds
    expected = simplify(
        integrate(
            integrate(
                simplify(integrand),
                (second, second_lower, second_upper),
            ),
            (first, first_lower, first_upper),
        )
    )
    return [_comparison_check(expected, _result_text(calculation))]


@_register("line_surface_integrals", "flux_explicit")
def _verify_flux_explicit(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    vector_values = _items(inputs, "vector_field") or []
    if len(vector_values) != 3:
        raise VerificationInputError("显式曲面上的向量场必须是三维")
    (
        first,
        second,
        z_expression,
        first_partial,
        second_partial,
        bounds,
    ) = _explicit_surface(inputs)
    z_symbol = sympy.Symbol("z")
    left = _parse(vector_values[0]).subs(z_symbol, z_expression)
    middle = _parse(vector_values[1]).subs(z_symbol, z_expression)
    right = _parse(vector_values[2]).subs(z_symbol, z_expression)
    integrand = simplify(-left * first_partial - middle * second_partial + right)
    orientation = _text(
        inputs,
        "orientation",
        required=False,
        default="up",
    )
    if orientation in {"down", "negative", "向下", "负向"}:
        integrand = simplify(-integrand)
    elif orientation not in {"up", "positive", "向上", "正向"}:
        raise VerificationInputError("orientation 必须表示向上或向下")
    first_lower, first_upper, second_lower, second_upper = bounds
    expected = simplify(
        integrate(
            integrate(
                integrand,
                (second, second_lower, second_upper),
            ),
            (first, first_lower, first_upper),
        )
    )
    return [_comparison_check(expected, _result_text(calculation))]


# Series


@_register("series", "sum")
def _verify_series_sum(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="n"))
    lower = _integer(inputs, "lower", default=1)
    upper = _parse(_text(inputs, "upper", required=False, default="oo"))
    expected = Sum(expression, (variable, lower, upper)).doit()
    return [
        verification_check("series_sum_complete", not expected.has(Sum)),
        _comparison_check(expected, _result_text(calculation)),
    ]


@_register("series", "convergence")
def _verify_series_convergence(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    from app.chapter_solvers import _series_convergence_fallback

    expression = _parse(_text(inputs, "expression"))
    variable = _symbol(_text(inputs, "variable", required=False, default="n"))
    lower = _integer(inputs, "lower", default=1)
    fallback = _series_convergence_fallback(expression, variable)
    if fallback is not None:
        expected = fallback[0]
    else:
        convergence = Sum(expression, (variable, lower, sympy.oo)).is_convergent()
        if convergence is True:
            expected = "收敛"
        elif convergence is False:
            expected = "发散"
        else:
            raise VerificationInputError("无法独立判定级数敛散性")
    return [
        verification_check(
            "convergence_value",
            _result_text(calculation) == expected,
        )
    ]


@_register("series", "power_radius")
def _verify_power_radius(
    inputs: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    coefficient = _parse(_text(inputs, "coefficient"))
    variable = _symbol(_text(inputs, "variable", required=False, default="n"))
    ratio_limit = Limit(
        Abs(coefficient.subs(variable, variable + 1) / coefficient),
        variable,
        sympy.oo,
    ).doit()
    if ratio_limit == 0:
        expected = sympy.oo
    elif ratio_limit in {sympy.oo, -sympy.oo}:
        expected = sympy.Integer(0)
    else:
        expected = simplify(1 / ratio_limit)
    return [_comparison_check(expected, _result_text(calculation))]


# Generic chat-layer solve calculations


def _verify_equation_solution(
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    equation_text = str(calculation.get("equation") or "").strip()
    variable = _symbol(calculation.get("variable"))
    if "=" in equation_text:
        left, right = equation_text.split("=", 1)
        difference = _parse(left) - _parse(right)
    else:
        difference = _parse(equation_text)
    expected = solve(difference, variable)
    expected_texts = [str(solution) for solution in expected]
    actual_texts = calculation.get("solutions")
    return [
        verification_check(
            "equation_residual",
            all(_expressions_equal(difference.subs(variable, point), 0) for point in expected),
        ),
        verification_check(
            "equation_solutions",
            actual_texts == expected_texts,
            f"独立求根为 {expected_texts}",
        ),
    ]


def _verify_determinant(
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    matrix_text = str(calculation.get("matrix") or "").strip()
    if not matrix_text.startswith("Matrix("):
        matrix = Matrix(sympy.sympify(matrix_text))
    else:
        matrix = _parse_result(matrix_text)
    if not isinstance(matrix, Matrix) or matrix.rows != matrix.cols:
        return [verification_check("square_matrix", False)]
    expected = simplify(matrix.det())
    return [
        verification_check("square_matrix", True),
        _comparison_check(expected, str(calculation.get("result") or "")),
    ]


def _verify_interval_extrema(
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expression = _parse(calculation.get("expression"))
    variable = _symbol(calculation.get("variable") or "x")
    interval = str(calculation.get("interval") or "").strip()
    match = __import__("re").fullmatch(
        r"(?P<left>[\(\[])\s*(?P<lower>.+?)\s*,\s*"
        r"(?P<upper>.+?)\s*(?P<right>[\)\]])",
        interval,
    )
    if match is None:
        return [verification_check("interval_format", False)]
    lower = _parse(match.group("lower"))
    upper = _parse(match.group("upper"))
    derivative = simplify(diff(expression, variable))
    critical_points = solve(derivative, variable)
    candidates = []
    for point in critical_points:
        evaluated = simplify(point.evalf())
        if evaluated.is_real is False:
            continue
        if evaluated < lower or evaluated > upper:
            continue
        candidates.append(simplify(expression.subs(variable, point)))
    if match.group("left") == "[":
        candidates.append(simplify(expression.subs(variable, lower)))
    else:
        candidates.append(
            Limit(expression, variable, lower, "+").doit()
        )
    if match.group("right") == "]":
        candidates.append(simplify(expression.subs(variable, upper)))
    else:
        candidates.append(
            Limit(expression, variable, upper, "-").doit()
        )
    candidates = [value for value in candidates if value.is_real is not False]
    if not candidates:
        return [verification_check("extrema_candidates", False)]
    kind = str(calculation.get("kind") or "")
    if kind == "最大值":
        expected = max(candidates, key=lambda value: float(value.evalf()))
    elif kind == "最小值":
        expected = min(candidates, key=lambda value: float(value.evalf()))
    else:
        return [verification_check("extrema_kind", False)]
    return [
        verification_check("extrema_candidates", True),
        _comparison_check(simplify(expected), str(calculation.get("result") or "")),
    ]
