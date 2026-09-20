"""Conversational text adapter for the public math demo."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sympy import latex

from app.main import (
    IntegrateRequest,
    LimitRequest,
    VerifyRequest,
    calculate_integral,
    calculate_limit,
    parse_math_expression,
    verify_derivative,
)


class DemoChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=600)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    history: list[DemoChatHistoryMessage] = Field(default_factory=list, max_length=20)


_TEXT_REPLACEMENTS = str.maketrans(
    {
        "（": "(",
        "）": ")",
        "，": ",",
        "：": ":",
        "；": ";",
        "－": "-",
        "−": "-",
        "–": "-",
        "—": "-",
        "×": "*",
        "÷": "/",
        "∞": "oo",
        "π": "pi",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
)

_FUNCTION_NAMES = {
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "asin",
    "acos",
    "atan",
    "acot",
    "asec",
    "acsc",
    "sinh",
    "cosh",
    "tanh",
    "asinh",
    "acosh",
    "atanh",
    "exp",
    "log",
    "ln",
    "sqrt",
    "abs",
}
_NON_VARIABLE_NAMES = _FUNCTION_NAMES | {"pi", "oo"}

_HELP_SUGGESTIONS = [
    "求导 x^2",
    "判断 2x 是不是 x^2 的导数",
    "积分 x^2",
    "积分 0 到 1 x^2",
    "lim x→0 sin(x)/x",
    "我以前做过哪些题",
]


def build_chat_response(
    message: str,
    history: list[DemoChatHistoryMessage] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_text(message)
    recent_questions = _recent_math_questions(history)
    if _is_history_query(normalized):
        return _history_response(recent_questions)

    if _is_history_followup(normalized):
        if not recent_questions:
            return _needs_input(
                "我这边还没有找到上一道题，请把题目重新发给我。"
            )
        previous_question = recent_questions[-1]
        response = _math_response(previous_question)
        response["reply"] = (
            f"我找到了上一题“{previous_question}”，下面重新给你核对。\n"
            f"{response['reply']}"
        )
        response["history_used"] = previous_question
        return response

    return _math_response(normalized)


def _math_response(normalized: str) -> dict[str, Any]:
    if not normalized:
        return _needs_input("请先输入一道高等数学题目。")

    if _is_greeting(normalized):
        return _help_response()

    intent = _detect_intent(normalized)
    if intent == "verify":
        return _build_derivative_response(normalized)
    if intent == "integrate":
        return _build_integral_response(normalized)
    if intent == "limit":
        return _build_limit_response(normalized)
    return _needs_input(
        "这个独立演示页目前可以连续处理求导、积分和极限。"
        "你可以直接输入“求导 x^2”或“积分 0 到 1 x^2”。"
    )


def _recent_math_questions(
    history: list[DemoChatHistoryMessage] | None,
) -> list[str]:
    questions: list[str] = []
    for item in history or []:
        role = item.get("role") if isinstance(item, dict) else item.role
        text = item.get("text") if isinstance(item, dict) else item.text
        if role != "user":
            continue
        normalized = _normalize_text(text)
        if _detect_intent(normalized) not in {"verify", "integrate", "limit"}:
            continue
        questions.append(normalized)

    unique_questions: list[str] = []
    for question in reversed(questions):
        if question not in unique_questions:
            unique_questions.append(question)
    unique_questions.reverse()
    return unique_questions[-8:]


def _is_history_query(value: str) -> bool:
    return bool(
        re.search(
            r"(?:历史题目|以前的题目|之前的题目|最近(?:做|问)过的?题|"
            r"(?:做过|问过)(?:哪些|什么)题|我(?:以前|之前)问过什么)",
            value,
            re.IGNORECASE,
        )
    )


def _is_history_followup(value: str) -> bool:
    compact = re.sub(r"[\s,，。！!?？]", "", value)
    return bool(
        re.fullmatch(
            r"(?:请)?(?:再|重新)?(?:算|做|讲|看)?(?:一遍|一下)?"
            r"(?:上一题|刚才(?:那|的)?题|上道题|前一道题|上一个问题)(?:吧|呢)?",
            compact,
        )
        or re.fullmatch(r"(?:继续|接着讲|然后呢)", compact)
    )


def _history_response(questions: list[str]) -> dict[str, Any]:
    if not questions:
        return {
            "status": "ok",
            "intent": "history",
            "reply": (
                "我这边还没有找到历史题目。"
                "先发一道求导、积分或极限题，我就能记住。"
            ),
            "formula_latex": "",
            "formula_text": "",
            "calculation": None,
            "history_questions": [],
            "suggestions": _HELP_SUGGESTIONS,
        }

    recent = questions[-5:]
    numbered = "\n".join(
        f"{index}. {question}" for index, question in enumerate(recent, start=1)
    )
    return {
        "status": "ok",
        "intent": "history",
        "reply": (
            f"我最近记得这些题目：\n{numbered}\n"
            "你可以重新发其中一道，或者说“再算一遍上一题”。"
        ),
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "history_questions": recent,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _normalize_text(value: str) -> str:
    return " ".join(str(value).translate(_TEXT_REPLACEMENTS).strip().split())


def _is_greeting(value: str) -> bool:
    compact = re.sub(r"[\s,，。！!?？]", "", value).lower()
    return compact in {
        "你好",
        "您好",
        "hi",
        "hello",
        "在吗",
        "帮助",
        "help",
        "你会什么",
        "你能做什么",
    }


def _detect_intent(value: str) -> str:
    lowered = value.lower()
    if re.search(r"(?:极限|\blim\b|limit)", lowered):
        return "limit"
    if "积分" in value or "∫" in value:
        return "integrate"
    if re.search(r"(?:求导|导数|导函数|微分|d\s*/\s*d)", lowered):
        return "verify"
    return "unknown"


def _build_derivative_response(message: str) -> dict[str, Any]:
    parsed = _parse_derivative(message)
    if parsed is None:
        return _needs_input(
            "请写出要求和导的函数，例如“求导 x^2”或"
            "“判断 2x 是不是 x^2 的导数”。"
        )

    expression, variable, candidate = parsed
    try:
        result = verify_derivative(
            VerifyRequest(
                expression=expression,
                variable=variable,
                candidate=candidate,
            ),
            _=None,
        ).model_dump(mode="json")
    except (HTTPException, ValidationError, ValueError) as exc:
        return _calculation_error(exc)

    expression_latex = _to_latex(result["expression"])
    formula_latex = (
        rf"\frac{{d}}{{d{result['variable']}}}\left({expression_latex}\right)"
        rf"={result['derivative_latex']}"
    )
    formula_text = (
        f"d/d{result['variable']} ({result['expression']}) = {result['derivative']}"
    )

    if result["candidate"] is None:
        reply = (
            f"我先给你确定性结果：导数是 {result['derivative']}。"
            "你能说一下这里用到了哪条求导法则吗？"
        )
    elif result["is_correct"]:
        reply = (
            "核对完成：候选答案正确。"
            f"导数是 {result['derivative']}。你能写出关键的一步吗？"
        )
    else:
        reply = (
            "核对完成：候选答案不正确。"
            f"正确导数是 {result['derivative']}，请重点检查系数、符号或链式法则。"
        )

    return _result_response(
        intent="verify",
        reply=reply,
        formula_latex=formula_latex,
        formula_text=formula_text,
        calculation=result,
        suggestions=[
            "求导 sin(x)",
            "判断 cos(x) 是不是 sin(x) 的导数",
        ],
    )


def _build_integral_response(message: str) -> dict[str, Any]:
    parsed = _parse_integral(message)
    if parsed is None:
        return _needs_input(
            "请写出要计算的积分，例如“积分 x^2”、"
            "“积分 0 到 1 x^2”或“∫ x^2 dx”。"
        )

    expression, variable, lower, upper, candidate = parsed
    try:
        result = calculate_integral(
            IntegrateRequest(
                expression=expression,
                variable=variable,
                lower=lower,
                upper=upper,
                candidate=candidate,
            ),
            _=None,
        ).model_dump(mode="json")
    except (HTTPException, ValidationError, ValueError) as exc:
        return _calculation_error(exc)

    expression_latex = _to_latex(result["expression"])
    if lower is not None and upper is not None:
        formula_latex = (
            rf"\int_{{{_to_latex(lower)}}}^{{{_to_latex(upper)}}}"
            rf"{expression_latex}\,d{result['variable']}={result['integral_latex']}"
        )
        formula_text = (
            f"integral of {result['expression']} from {lower} to {upper} "
            f"= {result['integral']}"
        )
        result_label = "定积分"
    else:
        formula_latex = (
            rf"\int {expression_latex}\,d{result['variable']}"
            rf"={result['integral_latex']}+C"
        )
        formula_text = (
            f"integral of {result['expression']} d{result['variable']} "
            f"= {result['integral']} + C"
        )
        result_label = "不定积分"

    if result["candidate"] is None:
        suffix = "，不要忘记任意常数 C" if result_label == "不定积分" else ""
        reply = (
            f"我先给出{result_label}结果：{result['integral']}{suffix}。"
            "你能说出本题最适合使用的积分方法吗？"
        )
    elif result["is_correct"]:
        reply = (
            f"核对完成：候选答案正确。{result_label}结果是 {result['integral']}。"
            "你能写出最关键的一步吗？"
        )
    else:
        reply = (
            f"核对完成：候选答案不正确。{result_label}结果是 {result['integral']}，"
            "请检查常数、上下限代入或基本积分公式。"
        )

    return _result_response(
        intent="integrate",
        reply=reply,
        formula_latex=formula_latex,
        formula_text=formula_text,
        calculation=result,
        suggestions=[
            "积分 x^2",
            "积分 0 到 1 x^2",
        ],
    )


def _build_limit_response(message: str) -> dict[str, Any]:
    parsed = _parse_limit(message)
    if parsed is None:
        return _needs_input(
            "请写出极限题，例如“lim x→0 sin(x)/x”或"
            "“求 x趋近于0时 1/x 的右极限”。"
        )

    expression, variable, point, direction, candidate = parsed
    try:
        result = calculate_limit(
            LimitRequest(
                expression=expression,
                variable=variable,
                point=point,
                direction=direction,
                candidate=candidate,
            ),
            _=None,
        ).model_dump(mode="json")
    except (HTTPException, ValidationError, ValueError) as exc:
        return _calculation_error(exc)

    direction_latex = ""
    if result["direction"] == "+":
        direction_latex = "^+"
    elif result["direction"] == "-":
        direction_latex = "^-"

    formula_latex = (
        rf"\lim_{{{result['variable']}\to {_to_latex(result['point'])}"
        rf"{direction_latex}}}\left({_to_latex(result['expression'])}\right)"
        rf"={result['limit_latex']}"
    )
    formula_text = (
        f"limit {result['expression']} as {result['variable']} -> "
        f"{result['point']} = {result['limit']}"
    )

    if result["candidate"] is None:
        reply = (
            f"我先给出极限结果：{result['limit']}。"
            "你能判断这里是否需要区分左极限和右极限吗？"
        )
    elif result["is_correct"]:
        reply = (
            f"核对完成：候选答案正确。极限是 {result['limit']}。"
            "你能说明为什么可以使用这个结论吗？"
        )
    else:
        reply = (
            f"核对完成：候选答案不正确。正确极限是 {result['limit']}，"
            "请检查趋近方向、等价无穷小或洛必达法则的使用条件。"
        )

    return _result_response(
        intent="limit",
        reply=reply,
        formula_latex=formula_latex,
        formula_text=formula_text,
        calculation=result,
        suggestions=[
            "lim x→0 sin(x)/x",
            "求 x趋近于0时 1/x 的右极限",
        ],
    )


def _parse_derivative(message: str) -> tuple[str, str, str | None] | None:
    candidate: str | None = None
    expression: str | None = None

    relation = re.search(
        r"(?P<first>.+?)\s*(?:是不是|是否为|是|等于)\s*"
        r"(?P<second>.+?)\s*的(?:导函数|导数)(?:吗)?$",
        message,
        re.IGNORECASE,
    )
    if relation:
        candidate = _clean_math_fragment(relation.group("first"))
        expression = _clean_expression(relation.group("second"))
    else:
        relation = re.search(
            r"(?P<expr>.+?)\s*的(?:导函数|导数)\s*"
            r"(?:是不是|是否为|是|等于)\s*(?P<candidate>.+?)(?:吗)?$",
            message,
            re.IGNORECASE,
        )
        if relation:
            expression = _clean_expression(relation.group("expr"))
            candidate = _clean_math_fragment(relation.group("candidate"))

    if expression is None:
        candidate = _extract_trailing_candidate(message) or candidate
        patterns = (
            r"^(?:帮我|请|来|计算|求)?\s*(?:求导|求导数|求导函数)\s*"
            r"(?:为|是|:)?\s*(.+)$",
            r"^(?:帮我|请|计算|求)?\s*(?:导数|微分)\s*(?:为|是|:)?\s*(.+)$",
            r"^(.+?)\s*的(?:导函数|导数)(?:是多少)?$",
            r"^d\s*/\s*d([A-Za-z][A-Za-z0-9_]*)\s*(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                expression = (
                    match.group(2)
                    if pattern == patterns[-1] and match.lastindex == 2
                    else match.group(1)
                )
                expression = _clean_expression(expression)
                break

    if expression is None:
        return None

    variable = _infer_variable(message, expression)
    return expression, variable, candidate


def _parse_integral(
    message: str,
) -> tuple[str, str, str | None, str | None, str | None] | None:
    candidate: str | None = None
    expression: str | None = None
    lower: str | None = None
    upper: str | None = None

    relation = re.search(
        r"(?P<first>.+?)\s*(?:是不是|是否为|是|等于)\s*"
        r"(?P<second>.+?)\s*的(?:不定积分|定积分|积分)(?:吗)?$",
        message,
        re.IGNORECASE,
    )
    if relation:
        candidate = _clean_math_fragment(relation.group("first"))
        expression = _clean_expression(relation.group("second"))
    else:
        relation = re.search(
            r"(?P<expr>.+?)\s*的(?:不定积分|定积分|积分)\s*"
            r"(?:是不是|是否为|是|等于)\s*(?P<candidate>.+?)(?:吗)?$",
            message,
            re.IGNORECASE,
        )
        if relation:
            expression = _clean_expression(relation.group("expr"))
            candidate = _clean_math_fragment(relation.group("candidate"))

    if expression is None:
        candidate = _extract_trailing_candidate(message) or candidate
        bound_patterns = (
            r"(?:积分|∫)\s*(?:从\s*)?(?P<lower>[^\s,]+)\s*"
            r"(?:到|至)\s*(?P<upper>[^\s,]+)\s*(?P<expr>.+)$",
            r"(?P<expr>.+?)\s*(?:从|在)\s*(?P<lower>[^\s,]+)\s*"
            r"到\s*(?P<upper>[^\s,]+)\s*的(?:定积分|积分)$",
            r"^∫\s*_?\s*(?P<lower>[^\s^]+)\s*\^\s*"
            r"(?P<upper>[^\s]+)\s*(?P<expr>.+)$",
        )
        for pattern in bound_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                lower = _clean_math_fragment(match.group("lower"))
                upper = _clean_math_fragment(match.group("upper"))
                expression = _clean_integrand(match.group("expr"))
                break

    if expression is None:
        integral_match = re.search(
            r"∫\s*(?P<expr>.+?)\s*d(?P<variable>[A-Za-z][A-Za-z0-9_]*)",
            message,
            re.IGNORECASE,
        )
        if integral_match:
            expression = _clean_integrand(integral_match.group("expr"))
        else:
            patterns = (
                r"^(?:帮我|请|计算|求)?\s*(?:求积分|积分)\s*"
                r"(?:为|是|:)?\s*(.+)$",
                r"^(.+?)\s*的(?:不定积分|积分)$",
            )
            for pattern in patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    expression = _clean_expression(match.group(1))
                    break

    if expression is None:
        return None

    expression = _clean_integrand(expression)
    variable = _infer_variable(message, expression)
    return expression, variable, lower, upper, candidate


def _parse_limit(
    message: str,
) -> tuple[str, str, str, str | None, str | None] | None:
    candidate = _extract_trailing_candidate(message)
    relation = re.search(
        r"(?P<first>.+?)\s*(?:是不是|是否为|是|等于)\s*"
        r"(?P<second>.+?)\s*的极限(?:吗)?$",
        message,
        re.IGNORECASE,
    )
    if relation:
        candidate = _clean_math_fragment(relation.group("first"))

    expression: str | None = None
    variable: str | None = None
    point: str | None = None

    lim_match = re.search(
        r"\blim(?:it)?\b\s*_?\s*\{?\s*"
        r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
        r"(?:→|->|趋于|趋近于)\s*(?P<point>[^}\s,]+)\s*\}?\s*"
        r"(?P<expr>.+)$",
        message,
        re.IGNORECASE,
    )
    if lim_match:
        variable = lim_match.group("variable")
        point = lim_match.group("point")
        expression = _clean_expression(lim_match.group("expr"))
    else:
        chinese_match = re.search(
            r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
            r"(?:趋于|趋近于|接近|→|->)\s*(?P<point>.+?)\s*"
            r"(?:时|的时候)\s*(?P<expr>.+?)\s*"
            r"(?:的)?(?:左极限|右极限|极限)$",
            message,
            re.IGNORECASE,
        )
        if chinese_match:
            variable = chinese_match.group("variable")
            point = chinese_match.group("point")
            expression = _clean_expression(chinese_match.group("expr"))
        else:
            trailing_match = re.search(
                r"(?:求|计算)?\s*极限\s*(?P<expr>.+?)\s*,?\s*"
                r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
                r"(?:趋于|趋近于|接近|→|->)\s*(?P<point>.+)$",
                message,
                re.IGNORECASE,
            )
            if trailing_match:
                variable = trailing_match.group("variable")
                point = trailing_match.group("point")
                expression = _clean_expression(trailing_match.group("expr"))

    if expression is None or variable is None or point is None:
        return None

    direction = None
    if re.search(r"(?:右极限|\+)\s*$", point) or "右极限" in message:
        direction = "+"
    elif re.search(r"(?:左极限|-)\s*$", point) or "左极限" in message:
        direction = "-"

    point = re.sub(r"(?:右极限|左极限|\+|-)\s*$", "", point).strip()
    point = point.replace("无穷大", "oo")
    if point in {"+∞", "+oo"}:
        point = "oo"
    elif point in {"-∞", "-oo"}:
        point = "-oo"

    expression = _clean_expression(expression)
    return expression, variable, point, direction, candidate


def _clean_expression(value: str) -> str:
    value = _clean_math_fragment(value)
    value = re.sub(
        r"^(?:帮我|请|计算|求|判断|检查|核对|看看)\s*",
        "",
        value,
    )
    value = re.sub(
        r"^(?:求导|求导数|求导函数|导数|微分|求积分|积分|极限)\s*"
        r"(?:为|是|:)?\s*",
        "",
        value,
    )
    value = re.sub(r"^[A-Za-z]\s*\([^)]*\)\s*=\s*", "", value)
    value = re.sub(r"^[A-Za-z]\s*=\s*", "", value)
    value = re.sub(r"\s*d[A-Za-z][A-Za-z0-9_]*\s*$", "", value)
    value = re.sub(
        r"\s*的?(?:导函数|导数|不定积分|定积分|积分|极限)\s*$",
        "",
        value,
    )
    return value.strip()


def _clean_integrand(value: str) -> str:
    value = _clean_expression(value)
    value = re.sub(r"\s*d[A-Za-z][A-Za-z0-9_]*\s*$", "", value)
    return value.strip()


def _clean_math_fragment(value: str) -> str:
    value = value.strip().strip("`'\"“”").strip()
    value = re.sub(
        r"^(?:帮我|请|计算|求|判断|检查|核对|看看|是|为|等于)\s*",
        "",
        value,
    )
    value = re.sub(
        r"\s*(?:吗|呢|对吗|对不对|是否正确|请判断)\s*[?？]?\s*$",
        "",
        value,
    )
    return value.strip(" ?？。;；")


def _extract_trailing_candidate(value: str) -> str | None:
    match = re.search(
        r"(?:候选答案|答案|结果)\s*(?:是|为|:)?\s*(.+)$",
        value,
        re.IGNORECASE,
    )
    if not match:
        return None
    candidate = _clean_math_fragment(match.group(1))
    return candidate or None


def _infer_variable(message: str, expression: str) -> str:
    explicit = re.search(
        r"(?:自变量|变量)\s*(?:为|是|:)?\s*([A-Za-z][A-Za-z0-9_]*)",
        message,
        re.IGNORECASE,
    )
    if explicit:
        return explicit.group(1)

    derivative = re.search(
        r"d\s*/\s*d\s*([A-Za-z][A-Za-z0-9_]*)",
        message,
        re.IGNORECASE,
    )
    if derivative:
        return derivative.group(1)

    integral = re.search(
        r"d\s*([A-Za-z][A-Za-z0-9_]*)\b",
        expression,
        re.IGNORECASE,
    )
    if integral:
        return integral.group(1)

    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", expression):
        if token not in _NON_VARIABLE_NAMES and token != "e":
            return token
    return "x"


def _to_latex(value: str) -> str:
    try:
        return latex(parse_math_expression(value))
    except Exception:
        return value.replace("**", "^")


def _help_response() -> dict[str, Any]:
    return {
        "status": "ok",
        "intent": "help",
        "reply": (
            "你好，我是知微老师。你可以像聊天一样直接输入题目，"
            "我会调用确定性数学工具计算求导、积分和极限，再给你检查问题。"
        ),
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _needs_input(reply: str) -> dict[str, Any]:
    return {
        "status": "needs_input",
        "intent": "unknown",
        "reply": reply,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _calculation_error(exc: Exception) -> dict[str, Any]:
    detail = getattr(exc, "detail", None) or "表达式无法解析"
    return {
        "status": "error",
        "intent": "calculation",
        "reply": f"这次计算没有完成：{detail}。请换一种写法后重试。",
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _result_response(
    *,
    intent: str,
    reply: str,
    formula_latex: str,
    formula_text: str,
    calculation: dict[str, Any],
    suggestions: list[str],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "intent": intent,
        "reply": reply,
        "formula_latex": formula_latex,
        "formula_text": formula_text,
        "calculation": calculation,
        "suggestions": suggestions,
    }
