"""Deterministic chapter solvers for the unified math workflow."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import sympy
from sympy import (
    Abs,
    Derivative,
    Eq,
    Function,
    Limit,
    Matrix,
    Sum,
    acos,
    diff,
    integrate,
    latex,
    simplify,
    solve,
    sqrt,
    sympify,
)
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)


MAX_INPUT_FIELDS = 32
MAX_VECTOR_LENGTH = 8

SUPPORTED_TOPICS: dict[str, frozenset[str]] = {
    "limits": frozenset({"limit", "sequence_limit"}),
    "derivatives": frozenset(
        {
            "derivative",
            "higher_derivative",
            "differential",
            "tangent",
            "normal",
            "mean_value",
            "critical_points",
            "monotonicity",
            "extrema",
            "taylor",
            "curvature",
            "parametric_derivative",
        }
    ),
    "integrals": frozenset({"indefinite", "definite", "improper"}),
    "differential_equations": frozenset({"dsolve"}),
    "vectors": frozenset(
        {"dot", "cross", "norm", "angle", "distance", "projection"}
    ),
    "multivariable_calculus": frozenset(
        {
            "partial",
            "mixed_partial",
            "gradient",
            "hessian",
            "directional_derivative",
            "implicit_derivative",
            "system_implicit_derivative",
            "multivariable_extrema",
            "conditional_extrema",
        }
    ),
    "multiple_integrals": frozenset({"double", "double_polar", "triple"}),
    "line_surface_integrals": frozenset(
        {"line_scalar", "line_vector", "surface_scalar", "flux"}
    ),
    "series": frozenset({"sum", "convergence", "power_radius"}),
}


class SolveError(ValueError):
    """Raised when a chapter request cannot be solved deterministically."""


def solve_chapter(
    chapter: str,
    topic: str,
    inputs: Mapping[str, Any] | None,
    candidate: str | None = None,
) -> dict[str, Any]:
    """Solve one supported chapter topic and return a serializable result."""

    if chapter not in SUPPORTED_TOPICS:
        raise SolveError(f"不支持的章节：{chapter}")
    if topic not in SUPPORTED_TOPICS[chapter]:
        raise SolveError(f"章节 {chapter} 不支持题目类型：{topic}")
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, Mapping):
        raise SolveError("inputs 必须是对象")
    if len(inputs) > MAX_INPUT_FIELDS:
        raise SolveError("inputs 字段过多")

    solver = _SOLVERS.get((chapter, topic))
    if solver is None:
        raise SolveError(f"尚未实现：{chapter}/{topic}")

    outcome = solver(_InputView(inputs))
    result = outcome["result"]
    result_latex = outcome.get("latex") or _safe_latex(result)
    comparison_value = outcome.get("comparison_value")
    is_correct = None
    candidate_text = candidate.strip() if isinstance(candidate, str) else None
    if candidate_text:
        if comparison_value is None:
            raise SolveError("该题型暂不支持候选答案自动判题")
        candidate_value = _parse_expression(candidate_text, "candidate")
        is_correct = _expressions_equal(comparison_value, candidate_value)

    return {
        "chapter": chapter,
        "topic": topic,
        "method": outcome["method"],
        "result": _stringify(result),
        "latex": result_latex,
        "candidate": candidate_text or None,
        "is_correct": is_correct,
        "notes": outcome.get("notes", []),
    }


class _InputView:
    def __init__(self, values: Mapping[str, Any]):
        self.values = values

    def text(
        self,
        key: str,
        *,
        required: bool = True,
        default: str | None = None,
    ) -> str | None:
        value = self.values.get(key, default)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                raise SolveError(f"缺少输入项：{key}")
            return None
        if not isinstance(value, str):
            raise SolveError(f"{key} 必须是文本")
        if "__" in value:
            raise SolveError(f"{key} 包含不支持的标识符")
        if len(value) > 300:
            raise SolveError(f"{key} 过长")
        return value.strip()

    def integer(
        self,
        key: str,
        *,
        required: bool = True,
        default: int | None = None,
    ) -> int | None:
        value = self.values.get(key, default)
        if value is None:
            if required:
                raise SolveError(f"缺少输入项：{key}")
            return None
        try:
            if isinstance(value, bool):
                raise ValueError
            return int(value)
        except (TypeError, ValueError) as exc:
            raise SolveError(f"{key} 必须是整数") from exc

    def items(
        self,
        key: str,
        *,
        required: bool = True,
    ) -> list[Any] | None:
        value = self.values.get(key)
        if value is None:
            if required:
                raise SolveError(f"缺少输入项：{key}")
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                if required:
                    raise SolveError(f"缺少输入项：{key}")
                return None
            value = [part.strip() for part in normalized.split(",") if part.strip()]
        if not isinstance(value, list):
            raise SolveError(f"{key} 必须是数组")
        if not value:
            raise SolveError(f"{key} 不能为空")
        if len(value) > MAX_VECTOR_LENGTH:
            raise SolveError(f"{key} 长度不能超过 {MAX_VECTOR_LENGTH}")
        return value

    def mapping(
        self,
        key: str,
        *,
        required: bool = True,
    ) -> dict[str, str] | None:
        value = self.values.get(key)
        if value is None:
            if required:
                raise SolveError(f"缺少输入项：{key}")
            return None
        if not isinstance(value, Mapping):
            raise SolveError(f"{key} 必须是对象")
        if len(value) > MAX_VECTOR_LENGTH:
            raise SolveError(f"{key} 字段过多")
        result: dict[str, str] = {}
        for raw_name, raw_expression in value.items():
            name = _parse_symbol(raw_name, f"{key}.name")
            expression = _parse_expression(raw_expression, f"{key}.{name}")
            result[str(name)] = str(expression)
        return result


def _solver(*, method: str):
    def decorator(callback: Callable[[_InputView], Any]):
        def wrapped(view: _InputView) -> dict[str, Any]:
            outcome = callback(view)
            if isinstance(outcome, dict) and "result" in outcome:
                return {**outcome, "method": method}
            return {"method": method, "result": outcome}

        return wrapped

    return decorator


def _parse_expression(value: Any, field_name: str) -> sympy.Expr:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return sympify(value)
    if not isinstance(value, str) or not value.strip():
        raise SolveError(f"{field_name} 必须是非空表达式")
    if len(value) > 300:
        raise SolveError(f"{field_name} 过长")
    if "__" in value:
        raise SolveError(f"{field_name} 包含不支持的标识符")

    # Import lazily to avoid a circular import with app.main.
    from app.main import parse_math_expression

    try:
        return parse_math_expression(value)
    except Exception as exc:
        raise SolveError(f"{field_name} 无法解析：{exc}") from exc


def _parse_symbol(value: Any, field_name: str) -> sympy.Symbol:
    from app.main import parse_symbol

    try:
        return parse_symbol(str(value))
    except Exception as exc:
        raise SolveError(f"{field_name} 无法解析：{exc}") from exc


def _parse_vector(
    values: Sequence[Any],
    field_name: str,
    expected_length: int | None = None,
) -> Matrix:
    if expected_length is not None and len(values) != expected_length:
        raise SolveError(f"{field_name} 必须是 {expected_length} 维向量")
    return Matrix(
        [
            _parse_expression(value, f"{field_name}[{index}]")
            for index, value in enumerate(values)
        ]
    )


def _parse_symbol_list(
    values: Sequence[Any],
    field_name: str,
) -> list[sympy.Symbol]:
    symbols = [
        _parse_symbol(value, f"{field_name}[{index}]")
        for index, value in enumerate(values)
    ]
    if len(set(symbols)) != len(symbols):
        raise SolveError(f"{field_name} 不能重复")
    return symbols


def _point_values(
    point: Sequence[Any] | None,
    symbols: Sequence[sympy.Symbol],
    field_name: str = "point",
) -> dict[sympy.Symbol, sympy.Expr] | None:
    if point is None:
        return None
    if len(point) != len(symbols):
        raise SolveError(f"{field_name} 的维数与 variables 不一致")
    return {
        symbol: _parse_expression(value, f"{field_name}[{index}]")
        for index, (symbol, value) in enumerate(zip(symbols, point, strict=True))
    }


def _parse_equation(
    value: str,
    function: sympy.Function,
    variable: sympy.Symbol,
) -> Eq:
    if len(value) > 300:
        raise SolveError("equation 过长")
    if "__" in value:
        raise SolveError("equation 包含不支持的标识符")

    if "=" in value:
        left_text, right_text = value.split("=", 1)
        return Eq(
            _parse_ode_side(left_text, function, variable),
            _parse_ode_side(right_text, function, variable),
        )
    return Eq(_parse_ode_side(value, function, variable), 0)


def _parse_ode_side(
    value: str,
    function: sympy.Function,
    variable: sympy.Symbol,
) -> sympy.Expr:
    normalized = value.strip()
    if not normalized:
        raise SolveError("方程两边不能为空")
    if not re.fullmatch(r"[A-Za-z0-9_+\-*/^()., '\s]+", normalized):
        raise SolveError("方程包含不支持的字符")

    function_name = str(function)
    escaped_name = re.escape(function_name)

    def replace_derivative(match: re.Match[str]) -> str:
        order = len(match.group(1))
        suffix = "" if order == 1 else f", {order}"
        return f"Derivative({function_name}({variable}), {variable}{suffix})"

    normalized = re.sub(
        rf"\b{escaped_name}\s*('+)",
        replace_derivative,
        normalized,
    )
    normalized = re.sub(
        rf"\b{escaped_name}\b(?!\s*\()",
        f"{function_name}({variable})",
        normalized,
    )
    normalized = normalized.replace("^", "**")

    from app.main import SAFE_LOCAL_DICT

    local_dict = {
        **SAFE_LOCAL_DICT,
        "Derivative": Derivative,
        "Function": Function,
        function_name: Function(function_name),
        str(variable): variable,
    }
    transformations = standard_transformations + (
        implicit_multiplication_application,
    )
    try:
        return parse_expr(
            normalized,
            transformations=transformations,
            local_dict=local_dict,
            global_dict={"__builtins__": {}},
        )
    except Exception as exc:
        raise SolveError(f"方程无法解析：{exc}") from exc


def _expressions_equal(left: Any, right: Any) -> bool:
    try:
        if left == right:
            return True
        return simplify(left - right) == 0
    except Exception:
        return False


def _stringify(value: Any) -> str:
    return str(value)


def _safe_latex(value: Any) -> str:
    try:
        return latex(value)
    except Exception:
        return str(value)


def _as_solution_rhs(solution: Any, function: sympy.Function) -> sympy.Expr:
    if isinstance(solution, (list, tuple)):
        if len(solution) != 1:
            raise SolveError("方程返回多个解，暂不支持候选答案自动判题")
        solution = solution[0]
    if isinstance(solution, Eq):
        if solution.lhs == function:
            return solution.rhs
        if solution.rhs == function:
            return solution.lhs
        difference = simplify(solution.lhs - solution.rhs)
        if difference == 0:
            return sympy.Integer(0)
    return solution


def _evaluate_at(expression: Any, substitutions: Mapping[sympy.Symbol, Any]) -> Any:
    return simplify(expression.subs(substitutions))


# Limits


@_solver(method="极限的确定性计算")
def _limit(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    point = _parse_expression(
        view.text("point", required=False, default="0"),
        "point",
    )
    direction_text = view.text("direction", required=False)
    direction = direction_text if direction_text in {"+", "-"} else None
    if direction_text and direction is None:
        raise SolveError("direction 只能是 +、- 或留空")
    if direction is None:
        value = Limit(expression, variable, point).doit()
    else:
        value = Limit(expression, variable, point, direction).doit()
    if getattr(value, "has", lambda *_: False)(Limit):
        raise SolveError("极限无法确定性求出，请补充条件或改写表达式")
    return {"result": value, "comparison_value": value}


@_solver(method="数列极限的确定性计算")
def _sequence_limit(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="n"),
        "variable",
    )
    value = Limit(expression, variable, sympy.oo).doit()
    if getattr(value, "has", lambda *_: False)(Limit):
        raise SolveError("数列极限无法确定性求出")
    return {"result": value, "comparison_value": value}


# Derivatives


@_solver(method="显函数求导")
def _derivative(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    order = view.integer("order", required=False, default=1)
    if order is None or order < 1 or order > 20:
        raise SolveError("order 必须在 1 到 20 之间")
    value = diff(expression, variable, order)
    return {"result": value, "comparison_value": value}


@_solver(method="高阶导数")
def _higher_derivative(view: _InputView) -> dict[str, Any]:
    return _derivative(view)


@_solver(method="微分")
def _differential(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    differential_symbol = _parse_symbol(
        view.text("differential", required=False, default=f"d{variable}"),
        "differential",
    )
    derivative = diff(expression, variable)
    return {
        "result": derivative * differential_symbol,
        "latex": latex(derivative * differential_symbol),
        "notes": [f"dy = f'({variable}) d{variable}"],
    }


@_solver(method="切线方程")
def _tangent(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    point = _parse_expression(view.text("point"), "point")
    slope = diff(expression, variable).subs(variable, point)
    y_value = expression.subs(variable, point)
    equation = Eq(
        sympy.Symbol("y"),
        slope * (variable - point) + y_value,
    )
    return {"result": equation, "comparison_value": equation.rhs}


@_solver(method="法线方程")
def _normal(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    point = _parse_expression(view.text("point"), "point")
    slope = simplify(diff(expression, variable).subs(variable, point))
    y_value = expression.subs(variable, point)
    if slope == 0:
        equation = Eq(sympy.Symbol("y"), y_value)
    else:
        normal_slope = -1 / slope
        equation = Eq(
            sympy.Symbol("y"),
            normal_slope * (variable - point) + y_value,
        )
    return {"result": equation, "comparison_value": equation.rhs}


@_solver(method="拉格朗日中值定理")
def _mean_value(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    lower = _parse_expression(view.text("lower"), "lower")
    upper = _parse_expression(view.text("upper"), "upper")
    if simplify(upper - lower) == 0:
        raise SolveError("区间端点不能相同")
    average_slope = simplify(
        (expression.subs(variable, upper) - expression.subs(variable, lower))
        / (upper - lower)
    )
    equation = Eq(diff(expression, variable), average_slope)
    solutions = solve(equation, variable)
    return {
        "result": solutions,
        "latex": latex(Matrix(solutions)),
        "notes": [f"平均变化率：{average_slope}"],
    }


@_solver(method="驻点求解")
def _critical_points(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    derivative = diff(expression, variable)
    points = solve(derivative, variable)
    return {
        "result": points,
        "latex": latex(Matrix(points)),
        "notes": ["驻点由 f'(x)=0 求得"],
    }


@_solver(method="单调区间分析")
def _monotonicity(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    derivative = simplify(diff(expression, variable))
    points = solve(derivative, variable)
    return {
        "result": {"derivative": derivative, "critical_points": points},
        "latex": latex(derivative),
        "notes": ["先求 f'(x)，再按驻点和不可导点划分区间并判断符号"],
    }


@_solver(method="极值判定")
def _extrema(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    first = diff(expression, variable)
    second = diff(expression, variable, 2)
    points = solve(first, variable)
    classified = []
    for point in points:
        second_value = simplify(second.subs(variable, point))
        if second_value.is_positive:
            kind = "极小值"
        elif second_value.is_negative:
            kind = "极大值"
        else:
            kind = "需进一步判断"
        classified.append(
            {
                "x": point,
                "y": simplify(expression.subs(variable, point)),
                "kind": kind,
            }
        )
    return {
        "result": classified,
        "latex": latex(Matrix(points)) if points else "",
        "notes": ["二阶导数大于零为极小值，小于零为极大值"],
    }


@_solver(method="泰勒展开")
def _taylor(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    point = _parse_expression(
        view.text("point", required=False, default="0"),
        "point",
    )
    order = view.integer("order", required=False, default=5)
    if order is None or order < 0 or order > 20:
        raise SolveError("order 必须在 0 到 20 之间")
    result = expression.series(variable, point, order + 1).removeO()
    return {"result": result, "comparison_value": result}


@_solver(method="曲率计算")
def _curvature(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    point = view.text("point", required=False)
    first = diff(expression, variable)
    second = diff(expression, variable, 2)
    curvature = Abs(second) / (1 + first**2) ** sympy.Rational(3, 2)
    result = curvature
    if point is not None:
        result = simplify(curvature.subs(variable, _parse_expression(point, "point")))
    return {"result": result, "comparison_value": result, "latex": latex(result)}


@_solver(method="参数方程求导")
def _parametric_derivative(view: _InputView) -> dict[str, Any]:
    x_expression = _parse_expression(view.text("x_expression"), "x_expression")
    y_expression = _parse_expression(view.text("y_expression"), "y_expression")
    parameter = _parse_symbol(
        view.text("parameter", required=False, default="t"),
        "parameter",
    )
    dx_dt = simplify(diff(x_expression, parameter))
    dy_dt = simplify(diff(y_expression, parameter))
    if dx_dt == 0:
        raise SolveError("dx/dt = 0，不能直接使用 dy/dx = (dy/dt)/(dx/dt)")
    result = simplify(dy_dt / dx_dt)
    return {
        "result": result,
        "comparison_value": result,
        "notes": [f"dy/dx = (dy/dt)/(dx/dt)，其中 dx/dt = {dx_dt}，dy/dt = {dy_dt}"],
    }


# Integrals


@_solver(method="不定积分")
def _indefinite_integral(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    result = integrate(expression, variable)
    return {
        "result": result,
        "comparison_value": result,
        "notes": ["不定积分结果需另加任意常数 C"],
    }


@_solver(method="定积分")
def _definite_integral(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    lower = _parse_expression(view.text("lower"), "lower")
    upper = _parse_expression(view.text("upper"), "upper")
    result = integrate(expression, (variable, lower, upper))
    return {"result": result, "comparison_value": result}


@_solver(method="反常积分")
def _improper_integral(view: _InputView) -> dict[str, Any]:
    result = _definite_integral(view)
    result["notes"] = ["已按广义积分计算；若发散，结果会显示发散值或未求值形式"]
    return result


# Differential equations


@_solver(method="常微分方程求解")
def _dsolve(view: _InputView) -> dict[str, Any]:
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    function_name = view.text("function", required=False, default="y") or "y"
    function_symbol = _parse_symbol(function_name, "function")
    function = Function(str(function_symbol))
    equation = _parse_equation(view.text("equation"), function, variable)
    solution = sympy.dsolve(equation, function(variable))
    rhs = _as_solution_rhs(solution, function(variable))
    return {
        "result": solution,
        "comparison_value": rhs,
        "notes": ["结果中的 C1、C2 等表示任意常数"],
    }


# Vectors


@_solver(method="向量数量积")
def _dot(view: _InputView) -> dict[str, Any]:
    left = _parse_vector(view.items("left"), "left")
    right = _parse_vector(view.items("right"), "right", left.rows)
    result = (left.T * right)[0]
    return {"result": result, "comparison_value": result}


@_solver(method="向量向量积")
def _cross(view: _InputView) -> dict[str, Any]:
    left = _parse_vector(view.items("left"), "left", 3)
    right = _parse_vector(view.items("right"), "right", 3)
    result = left.cross(right)
    return {"result": result, "latex": latex(result)}


@_solver(method="向量模")
def _norm(view: _InputView) -> dict[str, Any]:
    vector = _parse_vector(view.items("vector"), "vector")
    result = simplify(sqrt(sum(component**2 for component in vector)))
    return {"result": result, "comparison_value": result}


@_solver(method="向量夹角")
def _angle(view: _InputView) -> dict[str, Any]:
    left = _parse_vector(view.items("left"), "left")
    right = _parse_vector(view.items("right"), "right", left.rows)
    left_norm = sqrt(sum(component**2 for component in left))
    right_norm = sqrt(sum(component**2 for component in right))
    cosine = (left.T * right)[0] / (left_norm * right_norm)
    result = acos(simplify(cosine))
    return {"result": result, "comparison_value": result}


@_solver(method="两点距离")
def _distance(view: _InputView) -> dict[str, Any]:
    left = _parse_vector(view.items("left"), "left")
    right = _parse_vector(view.items("right"), "right", left.rows)
    difference = left - right
    result = simplify(sqrt(sum(component**2 for component in difference)))
    return {"result": result, "comparison_value": result}


@_solver(method="向量投影")
def _projection(view: _InputView) -> dict[str, Any]:
    left = _parse_vector(view.items("left"), "left")
    right = _parse_vector(view.items("right"), "right", left.rows)
    denominator = (right.T * right)[0]
    if denominator == 0:
        raise SolveError("不能向零向量投影")
    result = simplify(((left.T * right)[0] / denominator) * right)
    return {"result": result, "latex": latex(result)}


# Multivariable calculus


@_solver(method="偏导数")
def _partial(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables_value = view.items("variables")
    variable = _parse_symbol(variables_value[0], "variables[0]")
    order = view.integer("order", required=False, default=1)
    if order is None or order < 1 or order > 20:
        raise SolveError("order 必须在 1 到 20 之间")
    result = diff(expression, variable, order)
    return {"result": result, "comparison_value": result}


@_solver(method="混合偏导数")
def _mixed_partial(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    result = expression
    for variable in variables:
        result = diff(result, variable)
    return {"result": result, "comparison_value": result}


def _gradient_components(
    expression: sympy.Expr,
    variables: Sequence[sympy.Symbol],
) -> list[sympy.Expr]:
    return [diff(expression, variable) for variable in variables]


@_solver(method="梯度")
def _gradient(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    point = view.items("point", required=False)
    substitutions = _point_values(point, variables) if point is not None else None
    result = _gradient_components(expression, variables)
    if substitutions is not None:
        result = [_evaluate_at(component, substitutions) for component in result]
    matrix = Matrix(result)
    return {"result": matrix, "latex": latex(matrix)}


@_solver(method="海森矩阵")
def _hessian(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    matrix = Matrix(
        [[diff(expression, left, right) for right in variables] for left in variables]
    )
    return {"result": simplify(matrix), "latex": latex(matrix)}


@_solver(method="方向导数")
def _directional_derivative(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    point_values = view.items("point")
    direction_values = view.items("direction")
    substitutions = _point_values(point_values, variables)
    direction = _parse_vector(direction_values, "direction", len(variables))
    direction_norm = sqrt(sum(component**2 for component in direction))
    if direction_norm == 0:
        raise SolveError("方向向量不能为零向量")
    gradient = Matrix(
        [
            _evaluate_at(diff(expression, variable), substitutions)
            for variable in variables
        ]
    )
    result = simplify((gradient.T * direction)[0] / direction_norm)
    return {"result": result, "comparison_value": result}


@_solver(method="隐函数求导")
def _implicit_derivative(view: _InputView) -> dict[str, Any]:
    equation_text = view.text("equation")
    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    dependent = _parse_symbol(
        view.text("dependent", required=False, default="y"),
        "dependent",
    )
    if "=" in equation_text:
        left_text, right_text = equation_text.split("=", 1)
        function = _parse_expression(
            left_text,
            "equation.left",
        ) - _parse_expression(right_text, "equation.right")
    else:
        function = _parse_expression(equation_text, "equation")
    denominator = diff(function, dependent)
    if simplify(denominator) == 0:
        raise SolveError("隐函数定理条件不满足：分母偏导数为零")
    result = simplify(-diff(function, variable) / denominator)
    point = view.items("point", required=False)
    if point is not None:
        substitutions = _point_values(point, [variable, dependent])
        result = simplify(result.subs(substitutions))
    return {"result": result, "comparison_value": result}


@_solver(method="方程组确定函数求偏导")
def _system_implicit_derivative(view: _InputView) -> dict[str, Any]:
    equation_values = view.items("equations")
    dependent_values = view.items("dependents")
    if len(equation_values) != len(dependent_values):
        raise SolveError("方程个数必须与因变量个数一致")

    variable = _parse_symbol(
        view.text("variable", required=False, default="x"),
        "variable",
    )
    dependents = _parse_symbol_list(dependent_values, "dependents")
    if variable in dependents:
        raise SolveError("自变量不能同时作为因变量")

    target = _parse_symbol(
        view.text("dependent", required=False, default=str(dependents[0])),
        "dependent",
    )
    if target not in dependents:
        raise SolveError("dependent 必须是 dependents 中的一个")

    functions: list[sympy.Expr] = []
    for index, raw_equation in enumerate(equation_values):
        if not isinstance(raw_equation, str) or not raw_equation.strip():
            raise SolveError(f"equations[{index}] 必须是方程文本")
        equation_text = raw_equation.strip()
        if "=" in equation_text:
            left_text, right_text = equation_text.split("=", 1)
            if not left_text.strip() or not right_text.strip():
                raise SolveError(f"equations[{index}] 两边都不能为空")
            left = _parse_expression(left_text, f"equations[{index}].left")
            right = _parse_expression(right_text, f"equations[{index}].right")
        else:
            left = _parse_expression(equation_text, f"equations[{index}]")
            right = sympy.Integer(0)
        functions.append(left - right)

    jacobian = Matrix(
        [[diff(function, dependent) for dependent in dependents] for function in functions]
    )
    determinant = simplify(jacobian.det())
    if determinant == 0:
        raise SolveError("方程组雅可比行列式为零，不能唯一确定隐函数")

    right_hand_side = Matrix([-diff(function, variable) for function in functions])
    try:
        derivatives = jacobian.LUsolve(right_hand_side)
    except Exception as exc:
        raise SolveError("方程组线性求解失败，请检查方程和变量设置") from exc

    result = simplify(derivatives[dependents.index(target)])
    return {
        "result": result,
        "comparison_value": result,
        "notes": [
            "由 F_i(...)=0 对自变量求导，再用因变量雅可比矩阵求解目标偏导"
        ],
    }


@_solver(method="多元函数极值")
def _multivariable_extrema(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    if len(variables) != 2:
        raise SolveError("当前多元极值支持二元函数")
    first, second = variables
    gradient = [diff(expression, first), diff(expression, second)]
    points = solve(gradient, variables, dict=True)
    classified = []
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
        classified.append(
            {
                "point": point,
                "value": simplify(expression.subs(point)),
                "kind": kind,
            }
        )
    return {"result": classified, "notes": ["使用二元函数极值判别法"]}


@_solver(method="条件极值（拉格朗日乘数法）")
def _conditional_extrema(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    if len(variables) != 2:
        raise SolveError("当前条件极值支持二元函数和一条等式约束")

    constraint_text = view.text("constraint", required=True)
    if constraint_text.count("=") != 1:
        raise SolveError("constraint 必须是包含一个等号的等式")
    left_text, right_text = constraint_text.split("=", 1)
    constraint = simplify(
        _parse_expression(left_text, "constraint.left")
        - _parse_expression(right_text, "constraint.right")
    )
    if constraint == 0:
        raise SolveError("constraint 不能是恒等式")

    declared_symbols = set(variables)
    actual_symbols = expression.free_symbols | constraint.free_symbols
    undeclared = actual_symbols - declared_symbols
    if undeclared:
        raise SolveError(
            f"expression 或 constraint 包含未声明变量：{sorted(map(str, undeclared))}"
        )

    lambda_symbol = _parse_symbol(
        view.text("lambda", required=False, default="lambda"),
        "lambda",
    )
    if lambda_symbol in declared_symbols:
        raise SolveError("lambda 不能与 variables 重复")

    lagrangian = expression + lambda_symbol * constraint
    equations = [diff(lagrangian, variable) for variable in variables] + [constraint]
    solutions = solve(equations, [*variables, lambda_symbol], dict=True)
    if not solutions:
        raise SolveError("未找到满足约束的条件驻点")

    classified = []
    for solution in solutions:
        point = {variable: simplify(solution[variable]) for variable in variables}
        lambda_value = simplify(solution[lambda_symbol])
        substitutions = {**point, lambda_symbol: lambda_value}
        first, second = variables
        bordered_hessian = Matrix(
            [
                [0, diff(constraint, first), diff(constraint, second)],
                [
                    diff(constraint, first),
                    diff(lagrangian, first, 2),
                    diff(lagrangian, first, second),
                ],
                [
                    diff(constraint, second),
                    diff(lagrangian, second, first),
                    diff(lagrangian, second, 2),
                ],
            ]
        )
        determinant = simplify(bordered_hessian.subs(substitutions).det())
        if determinant.is_positive:
            kind = "极大值"
        elif determinant.is_negative:
            kind = "极小值"
        else:
            kind = "需进一步判断"
        classified.append(
            {
                "point": point,
                "lambda": lambda_value,
                "value": simplify(expression.subs(point)),
                "kind": kind,
            }
        )

    latex_parts = []
    for item in classified:
        coordinates = ", ".join(
            f"{variable} = {latex(item['point'][variable])}" for variable in variables
        )
        latex_parts.append(
            f"{coordinates},\\quad \\lambda = {latex(item['lambda'])},"
            f"\\quad f = {latex(item['value'])},\\quad \\text{{{item['kind']}}}"
        )
    return {
        "result": classified,
        "latex": ",\\quad ".join(latex_parts),
        "notes": ["使用拉格朗日乘数法和加边海森矩阵判断条件极值"],
    }


# Multiple integrals


@_solver(method="二重积分")
def _double_integral(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    if len(variables) != 2:
        raise SolveError("二重积分需要两个积分变量")
    first, second = variables
    lower_first = _parse_expression(view.text("lower_x"), "lower_x")
    upper_first = _parse_expression(view.text("upper_x"), "upper_x")
    lower_second = _parse_expression(view.text("lower_y"), "lower_y")
    upper_second = _parse_expression(view.text("upper_y"), "upper_y")
    result = integrate(
        integrate(expression, (second, lower_second, upper_second)),
        (first, lower_first, upper_first),
    )
    result = simplify(result)
    return {"result": result, "comparison_value": result}


@_solver(method="二重积分（极坐标）")
def _double_polar_integral(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    radial = _parse_symbol(
        view.text("radial_variable", required=False, default="r"),
        "radial_variable",
    )
    angle = _parse_symbol(
        view.text("angle_variable", required=False, default="theta"),
        "angle_variable",
    )
    if radial == angle:
        raise SolveError("极坐标的两个变量不能相同")

    x_symbol = sympy.Symbol("x")
    y_symbol = sympy.Symbol("y")
    cartesian_symbols = {x_symbol, y_symbol}
    if expression.free_symbols & cartesian_symbols:
        expression = expression.subs(
            {
                x_symbol: radial * sympy.cos(angle),
                y_symbol: radial * sympy.sin(angle),
            }
        )

    lower_radius = _parse_expression(view.text("lower_r"), "lower_r")
    upper_radius = _parse_expression(view.text("upper_r"), "upper_r")
    lower_angle = _parse_expression(view.text("lower_theta"), "lower_theta")
    upper_angle = _parse_expression(view.text("upper_theta"), "upper_theta")
    integrand = simplify(expression * radial)
    result = integrate(
        integrate(integrand, (angle, lower_angle, upper_angle)),
        (radial, lower_radius, upper_radius),
    )
    result = simplify(result)
    return {
        "result": result,
        "comparison_value": result,
        "notes": ["已使用极坐标变换并乘以雅可比因子 r"],
    }


@_solver(method="三重积分")
def _triple_integral(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variables = _parse_symbol_list(view.items("variables"), "variables")
    if len(variables) != 3:
        raise SolveError("三重积分需要三个积分变量")
    bounds = {}
    for key, variable in zip(
        ("x", "y", "z"),
        variables,
        strict=True,
    ):
        bounds[variable] = (
            _parse_expression(view.text(f"lower_{key}"), f"lower_{key}"),
            _parse_expression(view.text(f"upper_{key}"), f"upper_{key}"),
        )
    result = expression
    for variable in reversed(variables):
        result = integrate(result, (variable, *bounds[variable]))
    result = simplify(result)
    return {"result": result, "comparison_value": result}


# Line and surface integrals


def _parameterized_curve(
    view: _InputView,
) -> tuple[sympy.Symbol, sympy.Expr, sympy.Expr, dict[sympy.Symbol, sympy.Expr]]:
    parameter = _parse_symbol(
        view.text("parameter", required=False, default="t"),
        "parameter",
    )
    components = view.mapping("components")
    substitutions = {
        _parse_symbol(name, f"components.{name}"): _parse_expression(
            value,
            f"components.{name}",
        )
        for name, value in components.items()
    }
    lower = _parse_expression(view.text("lower"), "lower")
    upper = _parse_expression(view.text("upper"), "upper")
    return parameter, lower, upper, substitutions


@_solver(method="第一类曲线积分")
def _line_scalar(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    parameter, lower, upper, substitutions = _parameterized_curve(view)
    substituted = expression.subs(substitutions)
    speed = sqrt(
        sum(diff(value, parameter) ** 2 for value in substitutions.values())
    )
    result = integrate(simplify(substituted * speed), (parameter, lower, upper))
    result = simplify(result)
    return {"result": result, "comparison_value": result}


@_solver(method="第二类曲线积分")
def _line_vector(view: _InputView) -> dict[str, Any]:
    vector_values = view.items("vector_field")
    parameter, lower, upper, substitutions = _parameterized_curve(view)
    if len(vector_values) != len(substitutions):
        raise SolveError("vector_field 维数必须与 components 一致")
    ordered_names = list(substitutions)
    result = 0
    for name, value in zip(ordered_names, vector_values, strict=True):
        field_component = _parse_expression(value, "vector_field")
        result += field_component.subs(substitutions) * diff(
            substitutions[name],
            parameter,
        )
    result = integrate(simplify(result), (parameter, lower, upper))
    result = simplify(result)
    return {"result": result, "comparison_value": result}


def _parameterized_surface(
    view: _InputView,
) -> tuple[
    tuple[sympy.Symbol, sympy.Symbol],
    tuple[sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr],
    dict[sympy.Symbol, sympy.Expr],
]:
    parameters_value = view.items("parameters", required=False) or ["u", "v"]
    parameters = _parse_symbol_list(parameters_value, "parameters")
    if len(parameters) != 2:
        raise SolveError("曲面参数必须有两个")
    u, v = parameters
    components = view.mapping("components")
    substitutions = {
        _parse_symbol(name, f"components.{name}"): _parse_expression(
            value,
            f"components.{name}",
        )
        for name, value in components.items()
    }
    bounds = (
        _parse_expression(view.text("u_lower"), "u_lower"),
        _parse_expression(view.text("u_upper"), "u_upper"),
        _parse_expression(view.text("v_lower"), "v_lower"),
        _parse_expression(view.text("v_upper"), "v_upper"),
    )
    return (u, v), bounds, substitutions


def _surface_cross(
    substitutions: Mapping[sympy.Symbol, sympy.Expr],
    parameters: tuple[sympy.Symbol, sympy.Symbol],
) -> Matrix:
    ordered_names = list(substitutions)
    if len(ordered_names) != 3:
        raise SolveError("曲面参数化需要 x、y、z 三个分量")
    u, v = parameters
    r_u = Matrix([diff(substitutions[name], u) for name in ordered_names])
    r_v = Matrix([diff(substitutions[name], v) for name in ordered_names])
    return r_u.cross(r_v)


@_solver(method="第一类曲面积分")
def _surface_scalar(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    parameters, bounds, substitutions = _parameterized_surface(view)
    cross = _surface_cross(substitutions, parameters)
    area_factor = sqrt(sum(component**2 for component in cross))
    u, v = parameters
    u_lower, u_upper, v_lower, v_upper = bounds
    result = integrate(
        integrate(
            simplify(expression.subs(substitutions) * area_factor),
            (v, v_lower, v_upper),
        ),
        (u, u_lower, u_upper),
    )
    result = simplify(result)
    return {"result": result, "comparison_value": result}


@_solver(method="第二类曲面积分")
def _flux(view: _InputView) -> dict[str, Any]:
    vector_values = view.items("vector_field")
    parameters, bounds, substitutions = _parameterized_surface(view)
    ordered_names = list(substitutions)
    if len(vector_values) != len(ordered_names):
        raise SolveError("vector_field 维数必须与 components 一致")
    field = Matrix(
        [
            _parse_expression(value, "vector_field").subs(substitutions)
            for value in vector_values
        ]
    )
    cross = _surface_cross(substitutions, parameters)
    integrand = simplify((field.T * cross)[0])
    u, v = parameters
    u_lower, u_upper, v_lower, v_upper = bounds
    result = integrate(
        integrate(integrand, (v, v_lower, v_upper)),
        (u, u_lower, u_upper),
    )
    result = simplify(result)
    return {"result": result, "comparison_value": result}


# Series


@_solver(method="级数求和")
def _series_sum(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="n"),
        "variable",
    )
    lower = view.integer("lower", required=False, default=1)
    if lower is None:
        lower = 1
    upper = _parse_expression(
        view.text("upper", required=False, default="oo"),
        "upper",
    )
    result = Sum(expression, (variable, lower, upper)).doit()
    if getattr(result, "has", lambda *_: False)(Sum):
        raise SolveError("级数无法确定性求和")
    return {"result": result, "comparison_value": result}


@_solver(method="级数敛散性")
def _series_convergence(view: _InputView) -> dict[str, Any]:
    expression = _parse_expression(view.text("expression"), "expression")
    variable = _parse_symbol(
        view.text("variable", required=False, default="n"),
        "variable",
    )
    lower = view.integer("lower", required=False, default=1)
    if lower is None:
        lower = 1
    fallback = _series_convergence_fallback(expression, variable)
    if fallback is not None:
        result, method = fallback
        return {"result": result, "notes": [method]}

    convergence = Sum(expression, (variable, lower, sympy.oo)).is_convergent()
    if convergence is True:
        result = "收敛"
    elif convergence is False:
        result = "发散"
    else:
        raise SolveError("暂时无法判定该级数的敛散性")
    return {"result": result, "notes": ["判定基于 SymPy 的级数敛散性分析"]}


def _series_convergence_fallback(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> tuple[str, str] | None:
    """Handle common series when SymPy cannot decide directly."""

    unsigned_expression = _unsigned_series_term(expression, variable)
    if not _series_divergence_test_passes(expression, variable):
        return "发散", "判定依据：级数收敛的必要条件（一般项不趋于 0）"

    if unsigned_expression != expression:
        power = _p_series_exponent(unsigned_expression, variable)
        if power is not None:
            result = "收敛" if power > 0 else "发散"
            return result, "判定依据：交错级数与 p 级数定理"
        asymptotic_power = _asymptotic_p_series_exponent(
            unsigned_expression, variable
        )
        if asymptotic_power is not None:
            return "收敛", "判定依据：交错级数审敛法与 p 级数比较"
    else:
        p_series = _p_series_convergence(expression, variable)
        if p_series is not None:
            return p_series, "判定依据：p 级数收敛定理"
        asymptotic_power = _asymptotic_p_series_exponent(expression, variable)
        if asymptotic_power is not None:
            result = "收敛" if asymptotic_power > 1 else "发散"
            return result, "判定依据：与 p 级数作渐近比较"

    ratio_result = _ratio_test_convergence(expression, variable)
    if ratio_result is not None:
        return ratio_result, "判定依据：比值审敛法"

    return None


def _unsigned_series_term(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> sympy.Expr:
    for factor in (
        (-1) ** variable,
        (-1) ** (variable + 1),
    ):
        if expression.has(factor):
            unsigned = simplify(expression / factor)
            if variable not in unsigned.free_symbols:
                continue
            return unsigned
    return expression


def _series_divergence_test_passes(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> bool:
    try:
        term_limit = Limit(expression, variable, sympy.oo).doit()
    except Exception:
        return True
    if term_limit.is_zero is True:
        return True
    if term_limit.is_infinite is True:
        return False
    if term_limit.is_real is True:
        return bool(sympy.simplify(term_limit).is_zero)
    return True


def _asymptotic_p_series_exponent(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> sympy.Expr | None:
    absolute_term = simplify(Abs(expression))
    for power in (
        sympy.Rational(1, 2),
        sympy.Integer(1),
        sympy.Rational(3, 2),
        sympy.Integer(2),
        sympy.Integer(3),
    ):
        try:
            comparison_limit = Limit(
                absolute_term * variable**power,
                variable,
                sympy.oo,
            ).doit()
        except Exception:
            continue
        if comparison_limit.is_infinite is True:
            continue
        comparison_limit = simplify(comparison_limit)
        if comparison_limit.is_real is True and comparison_limit.is_positive is True:
            return power
    return None


def _p_series_convergence(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> str | None:
    power = _p_series_exponent(expression, variable)
    if power is None:
        return None
    return "收敛" if power > 1 else "发散"


def _p_series_exponent(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> sympy.Expr | None:
    numerator, denominator = sympy.fraction(expression)
    if variable in numerator.free_symbols:
        return None

    coefficient, denominator_core = denominator.as_coeff_Mul()
    if coefficient == 0:
        return None

    exponent = sympy.Wild("exponent")
    match = denominator_core.match(variable**exponent)
    if match is None:
        return None

    power = simplify(match[exponent])
    if power.is_real is not True or variable in power.free_symbols:
        return None
    return power


def _ratio_test_convergence(
    expression: sympy.Expr,
    variable: sympy.Symbol,
) -> str | None:
    try:
        absolute_term = simplify(Abs(expression))
        ratio = simplify(
            absolute_term.subs(variable, variable + 1) / absolute_term
        )
        ratio_limit = Limit(ratio, variable, sympy.oo).doit()
    except Exception:
        return None

    if ratio_limit.is_real is not True:
        return None
    if ratio_limit < 1:
        return "收敛"
    if ratio_limit > 1:
        return "发散"
    return None


@_solver(method="幂级数收敛半径")
def _power_radius(view: _InputView) -> dict[str, Any]:
    coefficient = _parse_expression(view.text("coefficient"), "coefficient")
    variable = _parse_symbol(
        view.text("variable", required=False, default="n"),
        "variable",
    )
    ratio = Abs(coefficient.subs(variable, variable + 1) / coefficient)
    ratio_limit = Limit(ratio, variable, sympy.oo).doit()
    if ratio_limit == 0:
        radius = sympy.oo
    elif ratio_limit in {sympy.oo, -sympy.oo}:
        radius = 0
    else:
        radius = simplify(1 / ratio_limit)
    return {
        "result": radius,
        "comparison_value": radius,
        "notes": ["使用比值法: R = 1 / lim |a_(n+1)/a_n|"],
    }


_SOLVERS = {
    ("limits", "limit"): _limit,
    ("limits", "sequence_limit"): _sequence_limit,
    ("derivatives", "derivative"): _derivative,
    ("derivatives", "higher_derivative"): _higher_derivative,
    ("derivatives", "differential"): _differential,
    ("derivatives", "tangent"): _tangent,
    ("derivatives", "normal"): _normal,
    ("derivatives", "mean_value"): _mean_value,
    ("derivatives", "critical_points"): _critical_points,
    ("derivatives", "monotonicity"): _monotonicity,
    ("derivatives", "extrema"): _extrema,
    ("derivatives", "taylor"): _taylor,
    ("derivatives", "curvature"): _curvature,
    ("derivatives", "parametric_derivative"): _parametric_derivative,
    ("integrals", "indefinite"): _indefinite_integral,
    ("integrals", "definite"): _definite_integral,
    ("integrals", "improper"): _improper_integral,
    ("differential_equations", "dsolve"): _dsolve,
    ("vectors", "dot"): _dot,
    ("vectors", "cross"): _cross,
    ("vectors", "norm"): _norm,
    ("vectors", "angle"): _angle,
    ("vectors", "distance"): _distance,
    ("vectors", "projection"): _projection,
    ("multivariable_calculus", "partial"): _partial,
    ("multivariable_calculus", "mixed_partial"): _mixed_partial,
    ("multivariable_calculus", "gradient"): _gradient,
    ("multivariable_calculus", "hessian"): _hessian,
    ("multivariable_calculus", "directional_derivative"): _directional_derivative,
    ("multivariable_calculus", "implicit_derivative"): _implicit_derivative,
    (
        "multivariable_calculus",
        "system_implicit_derivative",
    ): _system_implicit_derivative,
    ("multivariable_calculus", "multivariable_extrema"): _multivariable_extrema,
    ("multivariable_calculus", "conditional_extrema"): _conditional_extrema,
    ("multiple_integrals", "double"): _double_integral,
    ("multiple_integrals", "double_polar"): _double_polar_integral,
    ("multiple_integrals", "triple"): _triple_integral,
    ("line_surface_integrals", "line_scalar"): _line_scalar,
    ("line_surface_integrals", "line_vector"): _line_vector,
    ("line_surface_integrals", "surface_scalar"): _surface_scalar,
    ("line_surface_integrals", "flux"): _flux,
    ("series", "sum"): _series_sum,
    ("series", "convergence"): _series_convergence,
    ("series", "power_radius"): _power_radius,
}
