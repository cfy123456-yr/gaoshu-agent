"""Shared success gate for deterministic math solutions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import sympy


SOLUTION_INTENTS = frozenset(
    {
        "arithmetic",
        "integrate",
        "limit",
        "plot",
        "solve",
        "verify",
    }
)

_INCOMPLETE_RESULT_MARKERS = (
    "Integral(",
    "Derivative(",
    "Limit(",
    "Sum(",
    "Product(",
    "nan",
    "zoo",
)


def verification_check(
    name: str,
    passed: Any,
    detail: str = "",
) -> dict[str, Any]:
    """Build one normalized verification check."""
    check: dict[str, Any] = {
        "name": str(name),
        "passed": bool(passed),
    }
    if detail:
        check["detail"] = str(detail)
    return check


def verification_result(
    kind: str,
    checks: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the shared verification payload."""
    normalized: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, Mapping):
            continue
        name = str(check.get("name") or "").strip()
        if not name:
            continue
        item: dict[str, Any] = {
            "name": name,
            "passed": check.get("passed") is True,
        }
        if check.get("detail"):
            item["detail"] = str(check["detail"])
        normalized.append(item)
    return {
        "passed": bool(normalized)
        and all(check["passed"] for check in normalized),
        "kind": str(kind),
        "checks": normalized,
    }


def failed_verification(kind: str, reason: str) -> dict[str, Any]:
    """Build a visible failed gate result."""
    return verification_result(
        kind,
        [verification_check("calculation_complete", False, reason)],
    )


def is_verified_solution(payload: Mapping[str, Any] | None) -> bool:
    """Return whether a response may drive answer and downstream content."""
    if not isinstance(payload, Mapping):
        return False
    if str(payload.get("status") or "").strip().lower() != "ok":
        return False
    intent = str(payload.get("intent") or "").strip().lower()
    if intent not in SOLUTION_INTENTS:
        return False
    if payload.get("verified") is not True:
        return False
    verification = payload.get("verification")
    if not isinstance(verification, Mapping):
        return False
    if verification.get("passed") is not True:
        return False
    checks = verification.get("checks")
    if not isinstance(checks, list) or not checks:
        return False
    if not all(
        isinstance(check, Mapping) and check.get("passed") is True
        for check in checks
    ):
        return False
    calculation = payload.get("calculation")
    if not isinstance(calculation, Mapping) or not calculation:
        return False

    try:
        recomputed = verify_calculation(
            intent,
            calculation,
            context=payload.get("verification_context"),
        )
    except Exception:
        return False
    if recomputed.get("passed") is not True:
        return False
    provided_kind = str(verification.get("kind") or "").strip()
    recomputed_kind = str(recomputed.get("kind") or "").strip()
    return bool(
        provided_kind
        and recomputed_kind
        and provided_kind == recomputed_kind
    )


def verify_calculation(
    intent: str,
    calculation: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently verify supported deterministic response calculations."""
    if not isinstance(calculation, Mapping) or not calculation:
        return failed_verification(intent or "calculation", "缺少计算明细")

    normalized_intent = str(intent or "").strip().lower()
    if normalized_intent == "solve":
        chapter = str(calculation.get("chapter") or "").strip()
        topic = str(calculation.get("topic") or "").strip()
        verification_context = _chapter_verification_context(
            calculation,
            context,
        )
        if chapter or topic:
            if verification_context is None:
                return failed_verification(
                    topic or "chapter",
                    "章节求解缺少原始 chapter、topic 或 inputs 条件",
                )
            from app.chapter_verification import verify_chapter_calculation

            kind, checks = verify_chapter_calculation(
                calculation,
                verification_context,
            )
            return verification_result(kind, checks)
        if verification_context is not None:
            return failed_verification(
                "chapter",
                "验证上下文与计算结果类型不一致",
            )
        return _verify_generic_solution(calculation)

    verifier = {
        "verify": _verify_derivative_calculation,
        "integrate": _verify_integral_calculation,
        "limit": _verify_limit_calculation,
        "arithmetic": _verify_arithmetic_calculation,
        "plot": _verify_plot_calculation,
    }.get(normalized_intent)
    if verifier is None:
        return failed_verification(
            normalized_intent or "calculation",
            "该响应不是可验证的求解结果",
        )
    return verifier(calculation)


def _verify_derivative_calculation(
    calculation: Mapping[str, Any],
) -> dict[str, Any]:
    derivative = str(calculation.get("derivative") or "").strip()
    expression = str(calculation.get("expression") or "").strip()
    variable = str(calculation.get("variable") or "x").strip()
    derivative_function = str(
        calculation.get("derivative_function") or derivative
    ).strip()
    checks = [
        verification_check(
            "derivative_available",
            bool(derivative and derivative_function),
        )
    ]

    try:
        expression_value = _parse(expression)
        variable_value = sympy.Symbol(variable)
        expected = sympy.diff(
            expression_value,
            variable_value,
            int(calculation.get("order") or 1),
        )
        calculated = _parse(derivative_function)
        checks.append(
            verification_check(
                "derivative_rule",
                _expressions_equal(expected, calculated),
                "对原函数重新求导并与解析结果比较",
            )
        )
        point = calculation.get("point")
        if point is not None:
            evaluated = sympy.simplify(
                calculated.subs(variable_value, _parse(str(point)))
            )
            checks.append(
                verification_check(
                    "point_substitution",
                    _expressions_equal(evaluated, _parse(derivative)),
                    "把点代入导函数并与最终值比较",
                )
            )
    except Exception as exc:
        checks.append(
            verification_check(
                "derivative_rule",
                False,
                f"验算失败：{exc}",
            )
        )
    return verification_result("derivative", checks)


def _verify_integral_calculation(
    calculation: Mapping[str, Any],
) -> dict[str, Any]:
    expression = str(calculation.get("expression") or "").strip()
    integral = str(calculation.get("integral") or "").strip()
    variable = str(calculation.get("variable") or "x").strip()
    lower = calculation.get("lower")
    upper = calculation.get("upper")
    checks = [
        verification_check("integral_available", bool(expression and integral))
    ]

    try:
        variable_value = sympy.Symbol(variable)
        expression_value = _parse(expression)
        integral_value = _parse(integral)
        if lower is None or upper is None:
            checks.append(
                verification_check(
                    "integral_derivative",
                    _expressions_equal(
                        sympy.diff(integral_value, variable_value),
                        expression_value,
                    ),
                    "对积分结果求导并与被积函数比较",
                )
            )
        else:
            expected = sympy.integrate(
                expression_value,
                (variable_value, _parse(str(lower)), _parse(str(upper))),
            )
            checks.append(
                verification_check(
                    "definite_evaluation",
                    _expressions_equal(expected, integral_value),
                    "重新计算定积分并与结果比较",
                )
            )
    except Exception as exc:
        checks.append(
            verification_check(
                "integral_derivative",
                False,
                f"验算失败：{exc}",
            )
        )
    return verification_result("integral", checks)


def _verify_limit_calculation(
    calculation: Mapping[str, Any],
) -> dict[str, Any]:
    expression = str(calculation.get("expression") or "").strip()
    limit_value = str(calculation.get("limit") or "").strip()
    variable = str(calculation.get("variable") or "x").strip()
    point = str(calculation.get("point") or "0").strip()
    raw_direction = calculation.get("direction")
    direction = str(raw_direction).strip() if raw_direction is not None else None
    exists = calculation.get("exists") is not False
    checks = [
        verification_check(
            "limit_available",
            bool(expression) and (bool(limit_value) or not exists),
        ),
        verification_check(
            "limit_direction",
            direction in {None, "+", "-"},
        )
    ]

    if not exists:
        try:
            variable_value = sympy.Symbol(variable)
            expression_value = _parse(expression)
            point_value = _parse(point)
            if direction in {"+", "-"}:
                recomputed = sympy.Limit(
                    expression_value,
                    variable_value,
                    point_value,
                    direction,
                ).doit()
                evidence_key = "right_limit" if direction == "+" else "left_limit"
                evidence = str(calculation.get(evidence_key) or "").strip()
                checks.extend(
                    [
                        verification_check(
                            "limit_unresolved",
                            _limit_is_unresolved(recomputed),
                            "单侧极限必须确实振荡或无法稳定确定",
                        ),
                        verification_check(
                            "limit_evidence",
                            bool(evidence)
                            and _limit_evidence_matches(recomputed, evidence),
                            "展示的单侧趋势必须与独立复算一致",
                        ),
                    ]
                )
            else:
                left = sympy.Limit(
                    expression_value,
                    variable_value,
                    point_value,
                    "-",
                ).doit()
                right = sympy.Limit(
                    expression_value,
                    variable_value,
                    point_value,
                    "+",
                ).doit()
                left_evidence = str(
                    calculation.get("left_limit") or ""
                ).strip()
                right_evidence = str(
                    calculation.get("right_limit") or ""
                ).strip()
                unresolved = (
                    _limit_is_unresolved(left)
                    or _limit_is_unresolved(right)
                )
                sides_disagree = (
                    not _limit_is_unresolved(left)
                    and not _limit_is_unresolved(right)
                    and not _expressions_equal(left, right)
                )
                checks.extend(
                    [
                        verification_check(
                            "limit_non_existence",
                            unresolved or sides_disagree,
                            "双侧极限不存在必须有振荡或左右趋势不一致的证据",
                        ),
                        verification_check(
                            "left_limit_evidence",
                            bool(left_evidence)
                            and _limit_evidence_matches(left, left_evidence),
                            "左极限展示值必须与独立复算一致",
                        ),
                        verification_check(
                            "right_limit_evidence",
                            bool(right_evidence)
                            and _limit_evidence_matches(right, right_evidence),
                            "右极限展示值必须与独立复算一致",
                        ),
                    ]
                )
        except Exception as exc:
            checks.append(
                verification_check(
                    "limit_non_existence",
                    False,
                    f"不存在性验算失败：{exc}",
                )
            )
    else:
        try:
            variable_value = sympy.Symbol(variable)
            recomputed = sympy.Limit(
                _parse(expression),
                variable_value,
                _parse(point),
                str(direction) if direction in {"+", "-"} else "+-",
            ).doit()
            checks.append(
                verification_check(
                    "limit_recomputed",
                    _expressions_equal(recomputed, _parse(limit_value)),
                    "重新计算极限并与解析结果比较",
                )
            )
        except Exception as exc:
            checks.append(
                verification_check(
                    "limit_recomputed",
                    False,
                    f"验算失败：{exc}",
                )
            )
    return verification_result("limit", checks)


def _verify_generic_solution(
    calculation: Mapping[str, Any],
) -> dict[str, Any]:
    from app.chapter_verification import verify_generic_solve_calculation

    if {"equation", "variable", "solutions"} <= set(calculation):
        kind = "equation"
    elif {"matrix", "result"} <= set(calculation):
        kind = "determinant"
    elif {"expression", "interval", "kind", "critical_points"} <= set(calculation):
        kind = "interval_extrema"
    else:
        kind = "generic_solve"
    return verification_result(
        kind,
        verify_generic_solve_calculation(calculation),
    )


def _chapter_verification_context(
    calculation: Mapping[str, Any],
    context: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    candidate = context
    if candidate is None:
        candidate = calculation.get("verification_context")
    if not isinstance(candidate, Mapping):
        return None
    chapter = str(candidate.get("chapter") or "").strip()
    topic = str(candidate.get("topic") or "").strip()
    inputs = candidate.get("inputs")
    if not chapter or not topic or not isinstance(inputs, Mapping):
        return None
    return {
        "chapter": chapter,
        "topic": topic,
        "inputs": dict(inputs),
    }


def _verify_arithmetic_calculation(
    calculation: Mapping[str, Any],
) -> dict[str, Any]:
    result = str(calculation.get("result") or "").strip()
    expression = str(calculation.get("expression") or "").strip()
    checks = [
        verification_check("result_available", bool(result)),
        verification_check(
            "expression_available",
            bool(expression),
            "算术结果必须保留可独立复算的原算式",
        ),
    ]
    if expression and result:
        try:
            checks.append(
                verification_check(
                    "arithmetic_recomputed",
                    _expressions_equal(_parse(expression), _parse(result)),
                    "重新计算算式并与结果比较",
                )
            )
        except Exception as exc:
            checks.append(
                verification_check(
                    "arithmetic_recomputed",
                    False,
                    f"验算失败：{exc}",
                )
            )
    return verification_result("arithmetic", checks)


def _limit_is_unresolved(value: Any) -> bool:
    if value in {sympy.nan, sympy.zoo}:
        return True
    return bool(
        getattr(value, "has", lambda *args: False)(
            sympy.Limit,
            sympy.AccumBounds,
        )
    )


def _limit_evidence_matches(recomputed: Any, evidence: str) -> bool:
    if not evidence:
        return False
    recomputed_text = str(recomputed).strip()
    if recomputed_text == evidence:
        return True
    try:
        return _expressions_equal(recomputed, _parse(evidence))
    except Exception:
        return False


def _verify_plot_calculation(
    calculation: Mapping[str, Any],
) -> dict[str, Any]:
    expression = str(calculation.get("expression") or "").strip()
    plot_url = str(calculation.get("plot_url") or "").strip()
    checks = [
        verification_check("expression_available", bool(expression)),
        verification_check("plot_available", bool(plot_url)),
    ]
    return verification_result("plot", checks)


def _expressions_equal(left: sympy.Expr, right: sympy.Expr) -> bool:
    """Compare exact values without treating indeterminate forms as equal."""
    invalid_values = (sympy.nan, sympy.zoo)
    if left in invalid_values or right in invalid_values:
        return False
    if left.is_infinite or right.is_infinite:
        return bool(left.is_infinite and right.is_infinite and left == right)
    try:
        difference = sympy.simplify(left - right)
    except Exception:
        return False
    if difference in invalid_values:
        return False
    return bool(difference == 0 or difference.is_zero is True)


def _parse(value: str) -> sympy.Expr:
    from app.main import parse_math_expression

    return parse_math_expression(value)
