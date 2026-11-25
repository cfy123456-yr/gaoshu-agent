"""Conversational text adapter for the public math demo."""

from __future__ import annotations

import ast
import json
import os
import re
import secrets
import unicodedata
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sympy import E, Matrix, diff, latex, limit, simplify, solve, symbols

from app.chapter_solvers import MissingInputError, SolveError, solve_chapter
from app.main import (
    IntegrateRequest,
    LimitRequest,
    VerifyRequest,
    calculate_integral,
    calculate_limit,
    parse_math_expression,
    verify_derivative,
)
from app.solution_gate import (
    SOLUTION_INTENTS,
    failed_verification,
    is_verified_solution,
    verify_calculation,
)
from deploy.demo_math_text import normalize_math_text
from deploy.demo_knowledge import search_knowledge
from deploy.demo_interval_solver import solve_interval_extrema
from deploy.demo_question_blocks import strip_question_number_prefix


class DemoChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=600)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    history: list[DemoChatHistoryMessage] = Field(default_factory=list, max_length=20)
    source: Literal["text", "ocr"] = "text"
    pending_question: str = Field(default="", max_length=600)
    mode: Literal["qa", "teach"] = "qa"
    teaching_action: Literal[
        "start",
        "answer",
        "hint",
        "explain",
        "skip",
        "restart",
    ] | None = None


_GENERAL_CHAT_API_KEY = os.getenv("GENERAL_CHAT_API_KEY", "").strip()
_VISION_API_KEY = os.getenv("VISION_API_KEY", "").strip()
GENERAL_CHAT_API_KEY = _GENERAL_CHAT_API_KEY or _VISION_API_KEY
GENERAL_CHAT_API_URL = (
    os.getenv("GENERAL_CHAT_API_URL")
    or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
).strip()
GENERAL_CHAT_MODEL = (
    os.getenv("GENERAL_CHAT_MODEL") or "qwen-plus"
).strip()
GENERAL_CHAT_TIMEOUT_SECONDS = 30.0
GENERAL_CHAT_MAX_TOKENS = 1400
CONFIRMED_SOLVE_MAX_TOKENS = 2400


def general_chat_configured() -> bool:
    """Return whether the general chat route has all required credentials."""
    return bool(GENERAL_CHAT_API_KEY and GENERAL_CHAT_API_URL and GENERAL_CHAT_MODEL)


def general_chat_provider() -> str:
    """Return a non-sensitive provider label for the configured endpoint."""
    host = (urlsplit(GENERAL_CHAT_API_URL).hostname or "").lower()
    if host == "dashscope.aliyuncs.com":
        return "dashscope"
    if host == "api.deepseek.com":
        return "deepseek"
    return "openai-compatible" if host else ""


def general_chat_key_source() -> str:
    """Describe whether general chat uses its own key or the vision key fallback."""
    if _GENERAL_CHAT_API_KEY:
        return "dedicated"
    if _VISION_API_KEY and GENERAL_CHAT_API_KEY:
        return "vision_fallback"
    return "missing"

GENERAL_CHAT_SYSTEM_PROMPT = """
你是“知微老师”，中文回答，核心专长是高等数学，也可以回答学习方法、
科学技术和生活常识等普通问题。回答要简洁、直接、诚实；不知道时明确说明，
不要编造事实或来源。涉及医疗、法律、金融等专业决定时，只提供一般信息，
并建议咨询专业人士。不要声称调用过数学工具；需要精确数学计算时，提醒用户
使用求导、积分、极限或全章节解题功能。
""".strip()

TEACHING_CHAT_SYSTEM_PROMPT = """
你是“知微老师”，中文回答，采用循序渐进的教学方式。先判断用户已经掌握到
哪一步，再给出一个最关键的思路提示和下一步可执行动作，必要时用一个问题检查
理解；除非用户明确要求完整解法或表示已经尝试仍不会，不要一次直接公布最终答案。
回答要诚实、具体，不能编造事实或来源。涉及医疗、法律、金融等专业决定时，只提供
一般信息，并建议咨询专业人士。不要声称调用过数学工具；需要精确数学计算时，提醒
用户使用求导、积分、极限或全章节解题功能。
""".strip()

CONFIRMED_SOLVE_SYSTEM_PROMPT = """
你是“知微老师”，负责解答用户已经确认过的题目。请直接依据用户给出的
“待解题目”完成读题、考点判断和分步讲解，最后给出答案。题目若包含选择题，
请判断正确选项并说明理由。不要再次要求用户确认题目，不要说需要用户重新上传
图片，也不要因为题目文本有轻微 OCR 噪声就拒绝作答；可说明不确定之处后继续。
仅使用清晰、可核验的步骤，无法唯一确定答案时要明确指出缺少的条件。
回答必须严格使用以下四个 Markdown 小标题，顺序不可改变，每部分都要有内容：
**题目理解**
**解题思路**
**详细计算步骤**
**最终答案**
简单题可以简洁，但不能只写答案；复杂题必须保留关键推导。不要声称调用过
计算器、数学工具或外部工具。
""".strip()

_CONFIRMED_SOLVE_HEADINGS = (
    "题目理解",
    "解题思路",
    "详细计算步骤",
    "最终答案",
)
_UNVERIFIED_TOOL_CLAIM_PATTERN = re.compile(
    r"(?:已|我)(?:经)?(?:调用|使用)(?:了)?.{0,12}"
    r"(?:计算器|数学工具|外部工具|工具完成计算)",
)

_MATH_HINT_PATTERN = re.compile(
    r"(?:求导|导数|微分|积分|极限|级数|收敛|发散|函数图像|函数图象|"
    r"方程|向量|矩阵|偏导|梯度|重积分|曲线积分|曲面积分|"
    r"极值|极大值|极小值|最大值|最小值|最值|"
    r"\blim\b)",
    re.IGNORECASE,
)
_MATH_CONCEPT_TERM_PATTERN = re.compile(
    r"(?:导数|微分|积分|极限|偏导|梯度|重积分|曲线积分|曲面积分|级数|"
    r"洛必达法则|中值定理|泰勒公式|极值|极大值|极小值|最大值|最小值|最值)"
)
_MATH_CONCEPT_REQUEST_PATTERN = re.compile(
    r"(?:什么是|什么叫|定义|概念|含义|几何意义|物理意义|性质|"
    r"怎么理解|如何理解|解释一下|讲解一下|说明一下|有什么区别|关系)"
)
_DIRECT_EXTREMA_REQUEST_PATTERN = re.compile(
    r"(?:求|计算|确定|找出|判断)\s*(?:一下)?\s*"
    r"(?:函数|曲线)?[^。！？?\n]{0,24}"
    r"(?:极值|极大值|极小值|最大值|最小值|最值)"
)
_SPOKEN_EXPRESSION_HINT_PATTERN = re.compile(
    r"(?:平方|立方|次方|根号|除以|乘以|分之)"
)


def _is_math_concept_question(value: str) -> bool:
    return bool(
        _MATH_CONCEPT_TERM_PATTERN.search(value)
        and _MATH_CONCEPT_REQUEST_PATTERN.search(value)
    )

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

_ARITHMETIC_EXPRESSION_PATTERN = re.compile(r"^[0-9+\-*/^().\s]+$")
_ARITHMETIC_OPERATOR_PATTERN = re.compile(r"[+\-*/^]")

_HELP_SUGGESTIONS = [
    "求导 x^2",
    "判断 2x 是不是 x^2 的导数",
    "积分 x^2",
    "积分 0 到 1 x^2",
    "lim x→0 sin(x)/x",
    "画函数 y=sin(x)，x 从 -3 到 3",
    "判断级数 1/n^2 收敛",
    "积分 0 到 1 0 到 1 x*y",
    "解微分方程 y'-y=0",
    "我以前做过哪些题",
]

_CJK_EXPRESSION_TAIL = re.compile(
    r"\s*(?:是否|的|求|等于|等于多少|多少|呢|吗|请|帮忙|计算|判断).*$"
)

_EXTENDED_CHAPTER_HINTS = {
    ("series", "convergence"): {
        "missing": "请写出级数的一般项，例如“判断级数 1/n^2 收敛”。",
        "suggestions": ["判断级数 1/n^2 收敛", "判断级数 2^n/n! 收敛"],
    },
    ("series", "sum"): {
        "missing": "请写出级数的一般项，例如“级数求和 1/n^2”。",
        "suggestions": ["级数求和 1/n^2"],
    },
    ("series", "power_radius"): {
        "missing": "请写出幂级数系数，例如“幂级数 a_n=1/n 的收敛半径”。",
        "suggestions": ["幂级数 a_n=1/n 的收敛半径"],
    },
    ("multiple_integrals", "double"): {
        "missing": "请写出二重积分和被积函数，例如“积分 0 到 1 0 到 1 x*y”。",
        "suggestions": ["积分 0 到 1 0 到 1 x*y"],
    },
    ("multiple_integrals", "double_polar"): {
        "missing": "请写出极坐标二重积分和内外积分限，例如“极坐标二重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi”。",
        "suggestions": [
            "极坐标二重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi",
        ],
    },
    ("multiple_integrals", "triple"): {
        "missing": "请写出三重积分、被积函数和三个积分变量，例如“三重积分 x+y+z 变量 x,y,z”。",
        "suggestions": ["三重积分 x+y+z 变量 x,y,z"],
    },
    ("multiple_integrals", "triple_cylindrical"): {
        "missing": "请写出柱面坐标三重积分，例如“柱面坐标三重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi z 0 到 1”。",
        "suggestions": [
            "柱面坐标三重积分 x^2+y^2 r 0 到 1 theta 0 到 2*pi z 0 到 1",
        ],
    },
    ("multiple_integrals", "triple_spherical"): {
        "missing": "请写出球面坐标三重积分，例如“球面坐标三重积分 1 rho 0 到 1 phi 0 到 pi theta 0 到 2*pi”。",
        "suggestions": [
            "球面坐标三重积分 1 rho 0 到 1 phi 0 到 pi theta 0 到 2*pi",
        ],
    },
    ("differential_equations", "dsolve"): {
        "missing": "请写出微分方程，例如“解微分方程 y'-y=0”。",
        "suggestions": ["解微分方程 y'-y=0"],
    },
    ("multivariable_calculus", "partial"): {
        "missing": "请写出函数和求偏导的变量，例如“求偏导 x^2*y 对 x”。",
        "suggestions": ["求偏导 x^2*y 对 x", "梯度 x^2+y^2 变量 x,y"],
    },
    ("multivariable_calculus", "gradient"): {
        "missing": "请写出函数和变量，例如“梯度 x^2+y^2 变量 x,y”。",
        "suggestions": ["梯度 x^2+y^2 变量 x,y"],
    },
    ("multivariable_calculus", "implicit_derivative"): {
        "missing": "请写出隐函数方程，例如“隐函数 x^2+y^2=1 求 dy/dx”。",
        "suggestions": ["隐函数 x^2+y^2=1 求 dy/dx"],
    },
    ("multivariable_calculus", "system_implicit_derivative"): {
        "missing": "请写出方程组和因变量，例如“方程组 u+v=x; u-v=y，因变量 u,v，自变量 x，求 ∂u/∂x”。",
        "suggestions": [
            "方程组 u+v=x; u-v=y，因变量 u,v，自变量 x，求 ∂u/∂x",
        ],
    },
    ("multivariable_calculus", "conditional_extrema"): {
        "missing": "请写出目标函数、约束和变量，例如“条件极值 x*y 约束 x+y=1 变量 x,y”。",
        "suggestions": ["条件极值 x*y 约束 x+y=1 变量 x,y"],
    },
    ("derivatives", "parametric_derivative"): {
        "missing": "请写出参数方程，例如“参数方程 x=t^2, y=t^3 求 dy/dx”。",
        "suggestions": ["参数方程 x=t^2, y=t^3 求 dy/dx"],
    },
    ("derivatives", "parametric_tangent_normal"): {
        "missing": (
            "请写出参数方程、参数点和切线/法线要求，例如"
            "“x=sin(t), y=cos(2*t) 在 t=pi/4 处的切线方程和法线方程”。"
        ),
        "suggestions": [
            "x=sin(t), y=cos(2*t) 在 t=pi/4 处的切线方程和法线方程",
            "参数方程 x=t^2, y=t^3 在 t=1 处的切线和法线",
        ],
    },
    ("vectors", "dot"): {
        "missing": "请写出两个向量，例如“向量 (1,2,3) 点乘 (4,5,6)”。",
        "suggestions": ["向量 (1,2,3) 点乘 (4,5,6)"],
    },
}


def _strip_expression_tail(value: str) -> str:
    cleaned = _CJK_EXPRESSION_TAIL.sub("", str(value)).strip()
    return cleaned.rstrip("，,。;；:：")


def _looks_like_differential_equation(value: str) -> bool:
    if "隐函数" in value or "方程组" in value:
        return False
    if "微分方程" in value:
        return True
    if (
        re.search(
            r"(?<![A-Za-z])y\s*的\s*"
            r"(?:(?:[一二三四五六七八九十\d]+)\s*阶\s*)?导数",
            value,
        )
        and re.search(r"=|等于", value)
    ):
        return True
    if re.search(
        r"(?:\bd\s*(?:\^\s*\(?\d+\s*\)?)?\s*y\s*/\s*d\s*[A-Za-z]|"
        r"\bd\s*/\s*d\s*[A-Za-z]\s*y|"
        r"\by\s*(?:['′″]+|\^\s*\{?\s*\\prime))",
        value,
    ):
        return True
    return (
        "通解" in value
        and "=" in value
        and re.search(r"\by\b", value) is not None
    )


def _infer_ode_variable(value: str) -> str:
    patterns = (
        r"\bd\s*(?:\^\s*\(?\d+\s*\)?)?\s*y\s*/\s*d\s*([A-Za-z])",
        r"\bd\s*/\s*d\s*([A-Za-z])\s*y",
        r"\by\s*(?:['′″]+|\^\{?\s*\\prime)\s*"
        r"\(\s*([A-Za-z])\s*\)",
        r"\by\s*\(\s*([A-Za-z])\s*\)",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return "x"


def _normalize_differential_equation(value: str) -> str:
    """Clean OCR question wording around a differential equation."""
    equation = unicodedata.normalize("NFKC", str(value).strip())
    equation = re.sub(
        r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]",
        "",
        equation,
    )
    equation = re.sub(
        r"^\s*(?:(?:第\s*)?[一二三四五六七八九十百\d]+\s*[、.．:：]\s*)?"
        r"(?:选择题|填空题|判断题|计算题|解答题|证明题|综合题|应用题)"
        r"\s*(?:[（(][^()（）]{0,40}[)）])?\s*",
        "",
        equation,
        count=1,
    )
    equation = re.sub(
        r"^\s*(?:第\s*)?\d+\s*[题、.．)）:：]\s*",
        "",
        equation,
        count=1,
    )
    equation = re.sub(
        r"^.*?(?:微分方程|常微分方程|方程)\s*[:：,，]?\s*",
        "",
        equation,
        count=1,
    )
    equation = re.sub(
        r"^\s*(?:(?:请|麻烦)\s*)?(?:(?:帮我)\s*)?"
        r"(?:求解|求|解|计算)\s*[:：]?\s*",
        "",
        equation,
        count=1,
    )
    equation = re.split(
        r"\s*(?:求|计算)?\s*(?:(?:这个|该|此|其)\s*)?"
        r"(?:方程\s*)?(?:的\s*)?(?:通解|特解)"
        r"\s*(?:为|是)?.*$",
        equation,
        maxsplit=1,
    )[0]
    equation = equation.replace("′", "'").replace("’", "'")
    equation = re.sub(
        r"(?<![A-Za-z])y\s*的\s*(?:二阶|二次)\s*导数",
        "y''",
        equation,
    )
    equation = re.sub(
        r"(?<![A-Za-z])y\s*的\s*(?:(?:一阶|一次)\s*)?导数",
        "y'",
        equation,
    )
    equation = equation.replace("等于", "=")
    equation = re.sub(r"\s*减去\s*", "-", equation)
    equation = re.sub(r"\s*加上\s*", "+", equation)
    equation = re.sub(r"\s*乘以\s*", "*", equation)
    equation = re.sub(r"\s*减\s*", "-", equation)
    equation = re.sub(r"\s*加\s*", "+", equation)
    equation = re.sub(r"\s*乘\s*", "*", equation)
    equation = re.sub(r"[_＿]{2,}", "", equation)
    return equation.strip().rstrip("，,。;；:：_＿")


def _split_variables(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，、\s]+", value) if part.strip()]


def _split_constraints(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;；\n]+", value) if part.strip()]


def _extract_integral_triple(message: str) -> tuple[str, str, str, str] | None:
    match = re.search(
        r"(-?[\w./^()*+\- ]+?)\s+d([A-Za-z])\s*d([A-Za-z])\s*d([A-Za-z])",
        message,
    )
    if match is None:
        return None
    return (
        _strip_expression_tail(match.group(1)),
        match.group(2),
        match.group(3),
        match.group(4),
    )


def _extract_integral_double(message: str) -> tuple[str, str, str] | None:
    match = re.search(
        r"(-?[\w./^()*+\- ]+?)\s+d([A-Za-z])\s*d([A-Za-z])",
        message,
    )
    if match is None:
        return None
    return (
        _strip_expression_tail(match.group(1)),
        match.group(2),
        match.group(3),
    )


def _extract_nested_bounds(
    value: str,
    count: int,
) -> tuple[list[str], str] | None:
    bounds: list[str] = []
    remaining = value.strip()
    for _ in range(count):
        match = re.match(
            r"^([^\s到]+)\s+到\s+([^\s到]+)\s+(.+)$",
            remaining,
        )
        if match is None:
            return None
        bounds.extend([match.group(1), match.group(2)])
        remaining = match.group(3).strip()
    if not remaining:
        return None
    return bounds, _strip_expression_tail(remaining)


def _extract_bounds_and_expression(
    value: str,
) -> tuple[str, str, str, str, str] | None:
    parsed = _extract_nested_bounds(value, 2)
    if parsed is None:
        return None
    bounds, expression = parsed
    return bounds[0], bounds[1], bounds[2], bounds[3], expression


def _extract_parameter_bounds(message: str) -> tuple[str, str] | None:
    match = re.search(r"([\w^()*+\-/]+)\s+到\s+([\w^()*+\-/]+)", message)
    if match is None:
        return None
    return (
        _strip_expression_tail(match.group(1)),
        _strip_expression_tail(match.group(2)),
    )


def _infer_variables(expression: str, count: int) -> list[str]:
    variables: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", expression):
        lowered = token.lower()
        if lowered in _NON_VARIABLE_NAMES or lowered == "e":
            continue
        if token not in variables:
            variables.append(token)
    for fallback in ("x", "y", "z"):
        if len(variables) >= count:
            break
        if fallback not in variables:
            variables.append(fallback)
    return variables[:count]


def _infer_expression_variables(expression: str) -> list[str]:
    variables: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", expression):
        lowered = token.lower()
        if lowered in _NON_VARIABLE_NAMES or lowered == "e":
            continue
        if token not in variables:
            variables.append(token)
    return variables or ["x", "y"]


def _extract_curve_components(message: str) -> dict[str, str]:
    return {
        name: value.strip()
        for name, value in re.findall(
            r"([xyz])\s*=\s*([\w./^()*+\-]+)",
            message,
        )
    }


def _extract_vector_field(message: str) -> list[str] | None:
    match = re.search(
        r"(?:向量场|力场|F)\s*[（(]([^）)]+)[）)]",
        message,
    )
    if match is None:
        return None
    return _split_variables(match.group(1))


def _extract_explicit_curve(
    message: str,
) -> tuple[str, str, str] | None:
    curve_match = re.search(
        r"(?:曲线\s*)?y\s*=\s*(?P<curve>.+?)"
        r"(?=\s*[,，;；]?\s*x\s*(?:从|:)|$)",
        message,
        flags=re.IGNORECASE,
    )
    bounds_match = re.search(
        r"\bx\s*(?:从|:)?\s*(?P<lower>[^\s,，]+)\s*到\s*(?P<upper>[^\s,，]+)",
        message,
        flags=re.IGNORECASE,
    )
    if curve_match is None or bounds_match is None:
        return None
    return (
        _strip_expression_tail(curve_match.group("curve")),
        _strip_expression_tail(bounds_match.group("lower")),
        _strip_expression_tail(bounds_match.group("upper")),
    )


def _extract_explicit_surface(
    message: str,
) -> tuple[str, str, str, str, str] | None:
    surface_match = re.search(
        r"(?:曲面\s*)?z\s*=\s*(?P<surface>.+?)"
        r"(?=\s*[,，;；]?\s*x\s*(?:从|:)|$)",
        message,
        flags=re.IGNORECASE,
    )
    x_match = re.search(
        r"\bx\s*(?:从|:)?\s*(?P<lower>[^\s,，]+)\s*到\s*(?P<upper>[^\s,，]+)",
        message,
        flags=re.IGNORECASE,
    )
    y_match = re.search(
        r"\by\s*(?:从|:)?\s*(?P<lower>[^\s,，]+)\s*到\s*(?P<upper>[^\s,，]+)",
        message,
        flags=re.IGNORECASE,
    )
    if surface_match is None or x_match is None or y_match is None:
        return None
    return (
        _strip_expression_tail(surface_match.group("surface")),
        _strip_expression_tail(x_match.group("lower")),
        _strip_expression_tail(x_match.group("upper")),
        _strip_expression_tail(y_match.group("lower")),
        _strip_expression_tail(y_match.group("upper")),
    )


def _extract_vector_operands(message: str) -> tuple[list[str], list[str]] | None:
    vectors = re.findall(r"[（(]([^（）()]+)[）)]", message)
    if len(vectors) < 2:
        return None
    left = _split_variables(vectors[0])
    right = _split_variables(vectors[1])
    if not left or not right:
        return None
    return left, right


def _extract_parametric_tangent_normal(
    message: str,
) -> tuple[str, str, str, str | None] | None:
    """Extract x(t), y(t) and the requested parameter point."""
    compact = str(message).strip()
    if "切线" not in compact or "法线" not in compact:
        return None

    x_match = re.search(r"(?<![A-Za-z])x\s*=\s*", compact)
    if x_match is None:
        return None
    y_match = re.search(
        r"[,，;；]\s*y\s*=\s*",
        compact[x_match.end() :],
    )
    if y_match is None:
        return None
    y_start = x_match.end() + y_match.end()
    x_expression = compact[x_match.end() : x_match.end() + y_match.start()]
    tail = compact[y_start:]
    point_marker = re.search(r"\s*[}\]]?\s*(?:在|当)", tail)
    point_match = None
    if point_marker is not None:
        y_expression = tail[: point_marker.start()]
        point_tail = tail[point_marker.start() :]
        point_match = re.search(
            r"(?:(?:在|当|其中|参数)\s*){1,4}"
            r"(?P<parameter>[A-Za-z][A-Za-z0-9_]*)\s*=\s*"
            r"(?P<point>.+?)"
            r"(?=\s*(?:处|时|的切线|求|$|[，,;；。]))",
            point_tail,
        )
        if point_match is None:
            return None
    else:
        y_expression = _strip_expression_tail(tail)

    if point_match is not None:
        parameter = point_match.group("parameter")
        point = _strip_expression_tail(
            point_match.group("point")
        ).strip(" {}[]")
    else:
        parameter_match = re.search(
            r"参数\s*([A-Za-z][A-Za-z0-9_]*)",
            compact,
        )
        x_variables = _infer_expression_variables(x_expression)
        parameter = (
            parameter_match.group(1)
            if parameter_match is not None
            else (x_variables[0] if x_variables else "t")
        )
        point = None

    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(parameter)}(?![A-Za-z0-9_])", x_expression) is None:
        return None
    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(parameter)}(?![A-Za-z0-9_])", y_expression) is None:
        return None

    x_expression = _strip_expression_tail(x_expression).strip(" {}[]")
    y_expression = _strip_expression_tail(y_expression).strip(" {}[]")
    if not x_expression or not y_expression:
        return None
    return x_expression, y_expression, parameter, point


def _extract_explicit_tangent_at_x(
    message: str,
) -> tuple[str, str] | None:
    """Extract y=f(x) and x=a from a natural tangent-line request."""
    compact = str(message).strip()
    if "切线" not in compact:
        return None

    match = re.search(
        r"(?:求|作|写出|计算)?\s*(?:曲线\s*)?"
        r"(?:y\s*=\s*)?(?P<expression>[^，,;；。\n]+?)"
        r"\s*(?:在|当)\s*(?:点\s*)?x\s*=\s*"
        r"(?P<point>[^\s,，;；。]+?)"
        r"\s*(?:处|时)?(?:的\s*)?切线",
        compact,
    )
    if match is None:
        return None

    expression = _strip_expression_tail(match.group("expression"))
    point = _strip_expression_tail(match.group("point")).strip(" {}[]")
    if not expression or not point:
        return None
    return expression, point


def _parse_partial_point(
    value: str,
    variables: list[str],
) -> dict[str, str] | None:
    text = str(value).strip()
    named_values = re.findall(
        r"(?<![A-Za-z])([A-Za-z][A-Za-z0-9_]*)\s*=\s*"
        r"([^,，;；\s]+)",
        text,
    )
    if named_values:
        return {name: item for name, item in named_values}

    coordinates = [
        part.strip()
        for part in re.split(r"[,，;；]+", text)
        if part.strip()
    ]
    if not coordinates or len(coordinates) > len(variables):
        return None
    return dict(zip(variables, coordinates, strict=False))


def _extract_pointwise_partial_request(
    message: str,
) -> tuple[str, str, dict[str, str]] | None:
    match = re.search(
        r"(?:求|计算)?\s*(?:函数\s*)?(?:z\s*=\s*)?"
        r"(?P<expression>.+?)\s*(?:在|当)\s*(?:点\s*)?"
        r"[（(](?P<point>[^（）()]+)[）)]\s*(?:处|时)\s*"
        r"(?:对|关于|变量)\s*(?P<variable>[A-Za-z])\s*"
        r"(?:的)?\s*(?:一阶)?\s*偏导数?(?:值)?",
        message,
    )
    if match is None:
        return None

    expression = _strip_expression_tail(match.group("expression"))
    expression = re.sub(
        r"^(?:z|f)\s*=\s*",
        "",
        expression,
    ).strip()
    if not expression:
        return None

    variables = _infer_expression_variables(expression)
    variable = match.group("variable")
    if variable not in variables:
        variables.insert(0, variable)
    point = _parse_partial_point(match.group("point"), variables)
    if point is None:
        return None
    return expression, variable, point


def _resolve_extended_chapter(message: str) -> tuple[str, str, dict[str, Any]] | None:
    compact = message.strip()

    parametric_tangent_normal = _extract_parametric_tangent_normal(compact)
    if parametric_tangent_normal is not None:
        x_expression, y_expression, parameter, point = (
            parametric_tangent_normal
        )
        inputs = {
            "x_expression": x_expression,
            "y_expression": y_expression,
            "parameter": parameter,
        }
        if point is not None:
            inputs["parameter_value"] = point
        return (
            "derivatives",
            "parametric_tangent_normal",
            inputs,
        )

    if "参数方程" in compact and "切线" in compact and "法线" in compact:
        x_match = re.search(
            r"x\s*=\s*(.+?)(?=\s*[,，;；]\s*y\s*=|y\s*=)",
            compact,
        )
        y_match = re.search(
            r"y\s*=\s*(.+?)(?=\s*(?:的切线|的?法线|求|$))",
            compact,
        )
        if x_match and y_match:
            parameter_match = re.search(r"参数\s*([A-Za-z])", compact)
            return (
                "derivatives",
                "parametric_tangent_normal",
                {
                    "x_expression": _strip_expression_tail(x_match.group(1)),
                    "y_expression": _strip_expression_tail(y_match.group(1)),
                    "parameter": (
                        parameter_match.group(1) if parameter_match else "t"
                    ),
                },
            )

    if "参数方程" in compact:
        x_match = re.search(
            r"x\s*=\s*(.+?)(?=\s*[,，;；]\s*y\s*=|y\s*=)",
            compact,
        )
        y_match = re.search(
            r"y\s*=\s*(.+?)(?=\s*(?:求|计算|,|，|;|；|$))",
            compact,
        )
        if x_match and y_match:
            parameter_match = re.search(r"参数\s*([A-Za-z])", compact)
            return (
                "derivatives",
                "parametric_derivative",
                {
                    "x_expression": _strip_expression_tail(x_match.group(1)),
                    "y_expression": _strip_expression_tail(y_match.group(1)),
                    "parameter": (
                        parameter_match.group(1) if parameter_match else "t"
                    ),
                },
            )

    if "切线" in compact and "法线" in compact:
        # A partial tangent-only answer would violate the completion gate.
        return None

    tangent_match = re.search(
        r"(?:求|作|写出)?\s*切线\s*(?:y\s*=\s*)?"
        r"(?P<expression>.+?)\s*(?:在|当)\s*"
        r"x\s*=\s*(?P<point>[^\s,，]+)\s*(?:处)?",
        compact,
    )
    if tangent_match:
        expression = _strip_expression_tail(
            tangent_match.group("expression")
        )
        return (
            "derivatives",
            "tangent",
            {
                "expression": expression,
                "variable": "x",
                "point": tangent_match.group("point"),
            },
        )

    explicit_tangent = _extract_explicit_tangent_at_x(compact)
    if explicit_tangent is not None:
        expression, point = explicit_tangent
        return (
            "derivatives",
            "tangent",
            {
                "expression": expression,
                "variable": "x",
                "point": point,
            },
        )

    if "单调" in compact and "区间" in compact:
        monotonic_match = re.search(
            r"单调(?:递增|递减)?区间\s*(?:为|是)?\s*(?P<expression>.+)",
            compact,
        )
        if monotonic_match:
            expression = _strip_expression_tail(
                monotonic_match.group("expression")
            )
            variables = _infer_expression_variables(expression)
            return (
                "derivatives",
                "monotonicity",
                {
                    "expression": expression,
                    "variable": variables[0] if variables else "x",
                },
            )

    if "驻点" in compact:
        critical_match = re.search(
            r"驻点\s*(?:为|是)?\s*(?P<expression>.+)",
            compact,
        )
        if critical_match:
            expression = _strip_expression_tail(
                critical_match.group("expression")
            )
            variables = _infer_expression_variables(expression)
            return (
                "derivatives",
                "critical_points",
                {
                    "expression": expression,
                    "variable": variables[0] if variables else "x",
                },
            )

    if "极值" in compact and "条件极值" not in compact:
        extrema_match = re.search(
            r"极值\s*(?:为|是)?\s*(?P<expression>.+)",
            compact,
        )
        if extrema_match:
            expression = _strip_expression_tail(
                extrema_match.group("expression")
            )
            variables = _infer_expression_variables(expression)
            return (
                "derivatives",
                "extrema",
                {
                    "expression": expression,
                    "variable": variables[0] if variables else "x",
                },
            )

    if "条件极值" in compact or "拉格朗日" in compact:
        variables_match = re.search(
            r"变量\s*([A-Za-z](?:\s*[,，、]\s*[A-Za-z])*)",
            compact,
        )
        variables = (
            _split_variables(variables_match.group(1)) if variables_match else []
        )
        constraint_match = re.search(
            r"约束(?:条件)?\s*(?:为|是)?\s*[：:]?\s*(.+?)"
            r"(?=\s*(?:变量|自变量|求|计算|$))",
            compact,
        )
        expression_text = ""
        constraint_text = ""
        if constraint_match:
            constraint_text = _strip_expression_tail(constraint_match.group(1))
            expression_match = re.search(
                r"(?:条件极值|拉格朗日(?:乘数法)?)\s*(.+)",
                compact[: constraint_match.start()],
            )
            if expression_match:
                expression_text = _strip_expression_tail(expression_match.group(1))
        else:
            under_match = re.search(r"在\s*(.+?)\s*下", compact)
            if under_match:
                constraint_text = _strip_expression_tail(under_match.group(1))
                expression_match = re.search(
                    r"(?:条件极值|拉格朗日(?:乘数法)?)\s*(.+)",
                    compact[: under_match.start()],
                )
                if expression_match:
                    expression_text = _strip_expression_tail(
                        expression_match.group(1)
                    )
        if expression_text and constraint_text:
            constraints = _split_constraints(constraint_text)
            if len(variables) < 2:
                variables = _infer_variables(
                    expression_text,
                    max(2, len(constraints) + 1),
                )
            inputs = {
                "expression": expression_text,
                "variables": variables,
            }
            if len(constraints) == 1:
                inputs["constraint"] = constraints[0]
            else:
                inputs["constraints"] = constraints
            return (
                "multivariable_calculus",
                "conditional_extrema",
                inputs,
            )

    if _looks_like_differential_equation(compact):
        equation = _normalize_differential_equation(compact)
        return (
            "differential_equations",
            "dsolve",
            {
                "equation": equation,
                "variable": _infer_ode_variable(compact),
                "function": "y",
            },
        )

    if "方程组" in compact and (
        "求导" in compact or "偏导" in compact or "∂" in compact
    ):
        equation_match = re.search(
            r"方程组\s*(?:确定(?:的)?函数)?\s*[：:]?\s*(.+?)"
            r"(?=(?:因变量|自变量|确定|求|计算|$))",
            compact,
        )
        dependents_match = re.search(
            r"(?:因变量|确定)\s*([A-Za-z](?:\s*[,，]\s*[A-Za-z])*)",
            compact,
        )
        variable_match = re.search(r"自变量\s*([A-Za-z])", compact)
        target_match = re.search(
            r"(?:求|计算)\s*(?:∂|d)\s*([A-Za-z])\s*/"
            r"\s*(?:∂|d)\s*([A-Za-z])",
            compact,
        )
        if equation_match and dependents_match:
            equation_text = equation_match.group(1).strip().rstrip("，,；; ")
            equations = [
                part.strip().rstrip("，,。;；")
                for part in re.split(r"[;；]", equation_text)
                if part.strip()
            ]
            if len(equations) == 1:
                equations = [
                    part.strip().rstrip("，,。;；")
                    for part in re.split(
                        r"[,，](?=\s*[A-Za-z][A-Za-z0-9_]*\s*=)",
                        equation_text,
                    )
                    if part.strip()
                ]
            dependents = _split_variables(dependents_match.group(1))
            if equations and dependents:
                return (
                    "multivariable_calculus",
                    "system_implicit_derivative",
                    {
                        "equations": equations,
                        "dependents": dependents,
                        "variable": (
                            target_match.group(2)
                            if target_match
                            else (
                                variable_match.group(1)
                                if variable_match
                                else "x"
                            )
                        ),
                        "dependent": (
                            target_match.group(1)
                            if target_match
                            else dependents[0]
                        ),
                    },
                )

    if "隐函数" in compact:
        match = re.search(r"隐函数\s*(.+)", compact)
        if match:
            equation = re.split(r"\s*(?:求|计算|的)\s*dy\s*/\s*dx", match.group(1))[0]
            equation = equation.strip().rstrip("，,。;；")
            return (
                "multivariable_calculus",
                "implicit_derivative",
                {"equation": equation, "variable": "x", "dependent": "y"},
            )

    if "梯度" in compact:
        match = re.search(
            r"梯度\s*(.+?)\s*(?:变量|对)\s*([A-Za-z](?:\s*[,，]\s*[A-Za-z])*)",
            compact,
        )
        if match:
            return (
                "multivariable_calculus",
                "gradient",
                {
                    "expression": _strip_expression_tail(match.group(1)),
                    "variables": _split_variables(match.group(2)),
                },
            )
        fallback = re.search(r"梯度\s*(.+)$", compact)
        if fallback:
            expression = _strip_expression_tail(fallback.group(1)).strip()
            if expression:
                return (
                    "multivariable_calculus",
                    "gradient",
                    {
                        "expression": expression,
                        "variables": _infer_expression_variables(expression),
                    },
                )

    if "混合偏导" in compact:
        match = re.search(r"混合偏导\s*(.+?)\s*(?:变量|对)\s*(.+)", compact)
        if match:
            return (
                "multivariable_calculus",
                "mixed_partial",
                {
                    "expression": _strip_expression_tail(match.group(1)),
                    "variables": _split_variables(match.group(2)),
                },
            )

    pointwise_partial = _extract_pointwise_partial_request(compact)
    if pointwise_partial is not None:
        expression, variable, point = pointwise_partial
        return (
            "multivariable_calculus",
            "partial",
            {
                "expression": expression,
                "variables": [variable],
                "point": point,
            },
        )

    if "偏导" in compact or "∂" in compact:
        match = re.search(
            r"偏导\s*(.+?)\s*(?:对|关于|变量)\s*([A-Za-z])",
            compact,
        )
        if match:
            return (
                "multivariable_calculus",
                "partial",
                {
                    "expression": _strip_expression_tail(match.group(1)),
                    "variables": [match.group(2)],
                },
            )

    if "投影" in compact:
        vectors = _extract_vector_operands(compact)
        if vectors:
            return (
                "vectors",
                "projection",
                {"left": vectors[0], "right": vectors[1]},
            )
    if "点乘" in compact or "点积" in compact or "数量积" in compact:
        vectors = _extract_vector_operands(compact)
        if vectors:
            return "vectors", "dot", {"left": vectors[0], "right": vectors[1]}
    if "叉乘" in compact or "向量积" in compact:
        vectors = _extract_vector_operands(compact)
        if vectors:
            return "vectors", "cross", {"left": vectors[0], "right": vectors[1]}
    if "模长" in compact or "向量模" in compact:
        match = re.search(r"[（(]([^（）()]+)[）)]", compact)
        if match:
            return "vectors", "norm", {"vector": _split_variables(match.group(1))}
    if "夹角" in compact:
        vectors = _extract_vector_operands(compact)
        if vectors:
            return "vectors", "angle", {"left": vectors[0], "right": vectors[1]}
    if "距离" in compact:
        vectors = _extract_vector_operands(compact)
        if vectors:
            return "vectors", "distance", {"left": vectors[0], "right": vectors[1]}

    area_match = re.search(
        r"(?:求|计算)?\s*(?:由\s*)?曲线\s*y\s*=\s*"
        r"(?P<upper_expression>.+?)\s*与\s*(?:x\s*轴|y\s*=\s*0)"
        r"\s*(?:在|从)?\s*(?:x\s*)?(?:从\s*)?"
        r"(?P<lower>[^\s,，]+)\s*(?:到|至)\s*"
        r"(?P<upper>[^\s,，]+)\s*(?:之间)?\s*"
        r"(?:围成的?)?面积",
        compact,
        flags=re.IGNORECASE,
    )
    if area_match:
        return (
            "integrals",
            "area_between",
            {
                "upper_expression": _strip_expression_tail(
                    area_match.group("upper_expression")
                ),
                "lower_expression": "0",
                "variable": "x",
                "lower": area_match.group("lower"),
                "upper": area_match.group("upper"),
            },
        )

    volume_match = re.search(
        r"(?:求|计算)?\s*(?:曲线\s*)?y\s*=\s*"
        r"(?P<expression>.+?)\s*(?:绕|围绕)\s*x\s*轴"
        r".*?(?:体积)"
        r".*?(?:x\s*)?(?:从\s*)?(?P<lower>[^\s,，]+)"
        r"\s*(?:到|至)\s*(?P<upper>[^\s,，]+)",
        compact,
        flags=re.IGNORECASE,
    )
    if volume_match:
        return (
            "integrals",
            "volume_revolution",
            {
                "expression": _strip_expression_tail(
                    volume_match.group("expression")
                ),
                "variable": "x",
                "lower": volume_match.group("lower"),
                "upper": volume_match.group("upper"),
            },
        )

    arc_length_match = re.search(
        r"(?:求|计算)?\s*(?:曲线\s*)?y\s*=\s*"
        r"(?P<expression>.+?)\s*(?:从\s*)?"
        r"x\s*=\s*(?P<lower>[^\s,，]+)\s*(?:到|至)\s*"
        r"x\s*=\s*(?P<upper>[^\s,，]+)\s*(?:的)?弧长",
        compact,
        flags=re.IGNORECASE,
    )
    if arc_length_match:
        return (
            "integrals",
            "arc_length",
            {
                "expression": _strip_expression_tail(
                    arc_length_match.group("expression")
                ),
                "variable": "x",
                "lower": arc_length_match.group("lower"),
                "upper": arc_length_match.group("upper"),
            },
        )

    polar_match = re.search(
        r"极坐标(?:二重积分)?\s*(?P<expression>.+?)"
        r"\s*(?:r|半径)\s*(?:从|:)?\s*(?P<lower_r>[^\s,，]+)"
        r"\s*到\s*(?P<upper_r>[^\s,，]+)"
        r"\s*(?:theta|θ|角度)\s*(?:从|:)?\s*(?P<lower_theta>[^\s,，]+)"
        r"\s*到\s*(?P<upper_theta>[^\s,，]+)",
        compact,
        flags=re.IGNORECASE,
    )
    if polar_match:
        return (
            "multiple_integrals",
            "double_polar",
            {
                "expression": _strip_expression_tail(
                    polar_match.group("expression")
                ),
                "lower_r": _strip_expression_tail(polar_match.group("lower_r")),
                "upper_r": _strip_expression_tail(polar_match.group("upper_r")),
                "lower_theta": _strip_expression_tail(
                    polar_match.group("lower_theta")
                ),
                "upper_theta": _strip_expression_tail(
                    polar_match.group("upper_theta")
                ),
            },
        )

    cylindrical_match = re.search(
        r"(?:柱面坐标(?:三重积分)?|三重积分\s*柱面坐标)\s*"
        r"(?P<expression>.+?)"
        r"\s*(?:r|半径)\s*(?:从|:)?\s*(?P<lower_r>[^\s,，]+)"
        r"\s*到\s*(?P<upper_r>[^\s,，]+)"
        r"\s*(?:theta|θ|角度)\s*(?:从|:)?\s*(?P<lower_theta>[^\s,，]+)"
        r"\s*到\s*(?P<upper_theta>[^\s,，]+)"
        r"\s*(?:z|高度)\s*(?:从|:)?\s*(?P<lower_z>[^\s,，]+)"
        r"\s*到\s*(?P<upper_z>[^\s,，]+)",
        compact,
        flags=re.IGNORECASE,
    )
    if cylindrical_match:
        return (
            "multiple_integrals",
            "triple_cylindrical",
            {
                "expression": _strip_expression_tail(
                    cylindrical_match.group("expression")
                ),
                "lower_r": _strip_expression_tail(
                    cylindrical_match.group("lower_r")
                ),
                "upper_r": _strip_expression_tail(
                    cylindrical_match.group("upper_r")
                ),
                "lower_theta": _strip_expression_tail(
                    cylindrical_match.group("lower_theta")
                ),
                "upper_theta": _strip_expression_tail(
                    cylindrical_match.group("upper_theta")
                ),
                "lower_z": _strip_expression_tail(
                    cylindrical_match.group("lower_z")
                ),
                "upper_z": _strip_expression_tail(
                    cylindrical_match.group("upper_z")
                ),
            },
        )

    spherical_match = re.search(
        r"(?:球面坐标(?:三重积分)?|三重积分\s*球面坐标)\s*"
        r"(?P<expression>.+?)"
        r"\s*(?:rho|ρ|半径)\s*(?:从|:)?\s*(?P<lower_rho>[^\s,，]+)"
        r"\s*到\s*(?P<upper_rho>[^\s,，]+)"
        r"\s*(?:phi|φ|极角)\s*(?:从|:)?\s*(?P<lower_phi>[^\s,，]+)"
        r"\s*到\s*(?P<upper_phi>[^\s,，]+)"
        r"\s*(?:theta|θ|方位角|角度)\s*(?:从|:)?\s*(?P<lower_theta>[^\s,，]+)"
        r"\s*到\s*(?P<upper_theta>[^\s,，]+)",
        compact,
        flags=re.IGNORECASE,
    )
    if spherical_match:
        return (
            "multiple_integrals",
            "triple_spherical",
            {
                "expression": _strip_expression_tail(
                    spherical_match.group("expression")
                ),
                "lower_rho": _strip_expression_tail(
                    spherical_match.group("lower_rho")
                ),
                "upper_rho": _strip_expression_tail(
                    spherical_match.group("upper_rho")
                ),
                "lower_phi": _strip_expression_tail(
                    spherical_match.group("lower_phi")
                ),
                "upper_phi": _strip_expression_tail(
                    spherical_match.group("upper_phi")
                ),
                "lower_theta": _strip_expression_tail(
                    spherical_match.group("lower_theta")
                ),
                "upper_theta": _strip_expression_tail(
                    spherical_match.group("upper_theta")
                ),
            },
        )

    triple = _extract_integral_triple(compact)
    if triple is not None and ("三重" in compact or re.search(r"∫\s*∫\s*∫", compact)):
        expression, x_var, y_var, z_var = triple
        return (
            "multiple_integrals",
            "triple",
            {
                "expression": expression,
                "variables": [x_var, y_var, z_var],
                "lower_x": "0",
                "upper_x": "1",
                "lower_y": "0",
                "upper_y": "1",
                "lower_z": "0",
                "upper_z": "1",
            },
        )

    if "三重" in compact and ("积分" in compact or "∫" in compact):
        match = re.search(r"(?:三重)?\s*(?:积分|∫)\s*(.+)", compact)
        if match:
            tail = match.group(1).strip()
            explicit = re.search(r"\s*变量\s*(.+)$", tail)
            variables = (
                [_strip_expression_tail(value) for value in _split_variables(explicit.group(1))]
                if explicit
                else []
            )
            expression_text = tail[: explicit.start()].strip() if explicit else tail
            parsed_bounds = _extract_nested_bounds(expression_text, 3)
            if parsed_bounds is not None:
                bounds, expression_text = parsed_bounds
            else:
                bounds = ["0", "1", "0", "1", "0", "1"]
            if not variables:
                variables = _infer_variables(expression_text, 3)
            return (
                "multiple_integrals",
                "triple",
                {
                    "expression": _strip_expression_tail(expression_text),
                    "variables": variables,
                    "lower_x": bounds[0],
                    "upper_x": bounds[1],
                    "lower_y": bounds[2],
                    "upper_y": bounds[3],
                    "lower_z": bounds[4],
                    "upper_z": bounds[5],
                },
            )

    double = _extract_integral_double(compact)
    if double is not None and ("二重" in compact or re.search(r"∫\s*∫", compact)):
        expression, x_var, y_var = double
        return (
            "multiple_integrals",
            "double",
            {
                "expression": expression,
                "variables": [x_var, y_var],
                "lower_x": "0",
                "upper_x": "1",
                "lower_y": "0",
                "upper_y": "1",
            },
        )

    if "积分" in compact or "∫" in compact:
        match = re.search(r"(?:积分|∫)\s*(.+)", compact)
        if match:
            tail = match.group(1).strip()
            bounds = _extract_bounds_and_expression(tail)
            if bounds is not None:
                expression = bounds[4]
                return (
                    "multiple_integrals",
                    "double",
                    {
                        "expression": expression,
                        "variables": _infer_variables(expression, 2),
                        "lower_x": bounds[0],
                        "upper_x": bounds[1],
                        "lower_y": bounds[2],
                        "upper_y": bounds[3],
                    },
                )

    if (
        "第一类曲线积分" in compact
        or ("对弧长" in compact and "曲线积分" in compact)
    ):
        curve = _extract_explicit_curve(compact)
        expression_match = re.search(
            r"(?:第一类|对弧长)?曲线积分\s*(.+?)"
            r"\s*(?:沿|在)?\s*曲线\s*y\s*=",
            compact,
        )
        if curve and expression_match:
            curve_expression, lower, upper = curve
            return (
                "line_surface_integrals",
                "line_scalar_explicit",
                {
                    "expression": _strip_expression_tail(
                        expression_match.group(1)
                    ),
                    "variables": ["x", "y"],
                    "y_expression": curve_expression,
                    "lower": lower,
                    "upper": upper,
                },
            )

    if (
        "第二类曲线积分" in compact
        or ("对坐标" in compact and "曲线积分" in compact)
    ):
        vector_field = _extract_vector_field(compact)
        curve = _extract_explicit_curve(compact)
        if vector_field and curve:
            curve_expression, lower, upper = curve
            return (
                "line_surface_integrals",
                "line_vector_explicit",
                {
                    "vector_field": vector_field,
                    "variables": ["x", "y"],
                    "y_expression": curve_expression,
                    "lower": lower,
                    "upper": upper,
                },
            )

    if "第一类曲面积分" in compact or "对面积" in compact:
        surface = _extract_explicit_surface(compact)
        expression_match = re.search(
            r"(?:第一类|对面积)?曲面积分\s*(.+?)"
            r"\s*(?:在)?\s*曲面\s*z\s*=",
            compact,
        )
        if surface and expression_match:
            (
                surface_expression,
                x_lower,
                x_upper,
                y_lower,
                y_upper,
            ) = surface
            return (
                "line_surface_integrals",
                "surface_scalar_explicit",
                {
                    "expression": _strip_expression_tail(
                        expression_match.group(1)
                    ),
                    "variables": ["x", "y"],
                    "z_expression": surface_expression,
                    "x_lower": x_lower,
                    "x_upper": x_upper,
                    "y_lower": y_lower,
                    "y_upper": y_upper,
                },
            )

    if "第二类曲面积分" in compact or "通量" in compact:
        vector_field = _extract_vector_field(compact)
        surface = _extract_explicit_surface(compact)
        if vector_field and surface:
            (
                surface_expression,
                x_lower,
                x_upper,
                y_lower,
                y_upper,
            ) = surface
            orientation = (
                "down"
                if "向下" in compact or "down" in compact.lower()
                else "up"
            )
            return (
                "line_surface_integrals",
                "flux_explicit",
                {
                    "vector_field": vector_field,
                    "variables": ["x", "y"],
                    "z_expression": surface_expression,
                    "x_lower": x_lower,
                    "x_upper": x_upper,
                    "y_lower": y_lower,
                    "y_upper": y_upper,
                    "orientation": orientation,
                },
            )

    if "曲线积分" in compact:
        vector_field = _extract_vector_field(compact)
        components = _extract_curve_components(compact)
        bounds = _extract_parameter_bounds(compact)
        if components and bounds:
            inputs = {
                "components": components,
                "lower": bounds[0],
                "upper": bounds[1],
            }
            if vector_field is not None:
                inputs["vector_field"] = vector_field
                return "line_surface_integrals", "line_vector", inputs
            match = re.search(r"(?:对弧长|第一类)\s*([\w./^()*+\-]+)", compact)
            if match:
                inputs["expression"] = match.group(1)
                return "line_surface_integrals", "line_scalar", inputs

    if "第一类曲面积分" in compact or "曲面积分" in compact:
        if "第一类" in compact or "面积" in compact:
            match = re.search(r"(?:对面积|第一类)\s*([\w./^()*+\-]+)", compact)
            if match:
                return (
                    "line_surface_integrals",
                    "surface_scalar",
                    {"expression": match.group(1)},
                )

    if "收敛半径" in compact:
        match = re.search(
            r"(?:a_?n\s*=|系数\s*)([A-Za-z0-9^()*+\-/., ]+?)\s*的\s*收敛半径",
            compact,
        )
        if match:
            return (
                "series",
                "power_radius",
                {"coefficient": match.group(1).strip(), "variable": "n"},
            )

    has_convergence_request = re.search(r"收敛|发散|敛散", compact) is not None
    if (
        "级数" in compact
        or "∑" in compact
        or (
            ("一般项" in compact or "通项" in compact)
            and has_convergence_request
        )
    ):
        if "求和" in compact or "和函数" in compact:
            match = re.search(r"(?:级数求和|级数和|求和)\s*(.+)", compact)
            if match:
                return (
                    "series",
                    "sum",
                    {"expression": _strip_expression_tail(match.group(1)), "variable": "n"},
                )
        if has_convergence_request:
            match = re.search(
                r"(?:判断)?\s*级数\s*(.+?)\s*"
                r"(?:是否|收敛|发散|的敛散性|敛散性)",
                compact,
            )
            if match is None:
                match = re.search(
                    r"(?:一般项|通项)\s*(?:为|是|[:：])?\s*(.+?)\s*"
                    r"(?:是否|收敛|发散|的敛散性|敛散性)",
                    compact,
                )
            if match:
                return (
                    "series",
                    "convergence",
                    {"expression": _strip_expression_tail(match.group(1)), "variable": "n"},
                )

    return None


def build_chat_response(
    message: str,
    history: list[DemoChatHistoryMessage] | None = None,
    mode: Literal["qa", "teach"] = "qa",
) -> dict[str, Any]:
    response = _build_mode_aware_chat_response(message, history, mode)
    response["mode"] = mode
    return response


def build_ocr_confirmation_reply(question: str) -> str:
    """Build one OCR confirmation prompt with consistent terminal punctuation."""
    cleaned = re.sub(r"[\s。；;，,、.!！?？]+$", "", str(question).strip())
    return (
        f"题目已识别，请核对：{cleaned}。"
        "确认无误回复“确认”，我将开始计算。"
    )


def _build_mode_aware_chat_response(
    message: str,
    history: list[DemoChatHistoryMessage] | None,
    mode: Literal["qa", "teach"],
) -> dict[str, Any]:
    normalized = _normalize_text(message)
    ocr_question = _extract_ocr_question(normalized)
    if ocr_question:
        question_candidate = strip_question_number_prefix(ocr_question)
        try:
            solved = _math_response(question_candidate)
        except Exception:
            solved = None
        if solved is not None and solved.get("intent") in {"solve", "calculation"}:
            return solved
        response = _needs_input(
            build_ocr_confirmation_reply(ocr_question)
        )
        response["intent"] = "ocr_confirm"
        response["formula_text"] = ocr_question
        return response

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

    if _is_confirmation(normalized):
        pending_ocr_question = _pending_ocr_question(history)
        if pending_ocr_question:
            response = _solve_confirmed_question(pending_ocr_question, history)
            response["history_used"] = pending_ocr_question
            return response
        return _needs_input("请先上传或输入需要解答的题目。")

    if _is_rejection(normalized):
        return _needs_input(
            "题目识别不正确，请重新上传清晰、完整的题目图片。"
        )

    if _is_math_concept_question(normalized):
        knowledge_response = _build_knowledge_response(normalized)
        if knowledge_response is not None:
            return knowledge_response
        general_response = _build_general_chat_response(
            normalized,
            history,
            _general_system_prompt_for_mode(mode),
        )
        if general_response is not None:
            return general_response
        return _concept_help_response()

    math_response = _math_response(normalized)
    if math_response.get("intent") == "unknown":
        normalized_response = _build_normalized_expression_response(
            str(message),
            normalized,
        )
        if normalized_response is not None:
            return normalized_response
    if (
        math_response.get("intent") == "unknown"
        and _DIRECT_EXTREMA_REQUEST_PATTERN.search(normalized)
    ):
        return _missing_extrema_condition_response()
    if (
        math_response.get("intent") == "unknown"
        and not _MATH_HINT_PATTERN.search(normalized)
    ):
        general_response = _build_general_chat_response(
            normalized,
            history,
            _general_system_prompt_for_mode(mode),
        )
        if general_response is not None:
            return general_response
    return math_response


def _missing_extrema_condition_response() -> dict[str, Any]:
    response = _needs_input(
        "这个极值/最值请求还缺少可验证的计算条件。请补充具体函数表达式；"
        "如果题目要求最大值或最小值，还请给出定义域或闭区间。"
        "缺少这些条件时，我不会生成最终答案、教学步骤或知识点推荐。"
    )
    response["intent"] = "solve"
    return response


def _general_system_prompt_for_mode(mode: Literal["qa", "teach"]) -> str:
    if mode == "teach":
        return TEACHING_CHAT_SYSTEM_PROMPT
    return GENERAL_CHAT_SYSTEM_PROMPT


def _math_response(normalized: str) -> dict[str, Any]:
    if not normalized:
        return _needs_input("请先输入一道高等数学题目。")

    if _is_greeting(normalized):
        return _help_response()

    arithmetic = _build_arithmetic_response(normalized)
    if arithmetic is not None:
        return arithmetic

    interval_extrema = solve_interval_extrema(normalized)
    if interval_extrema is not None:
        return interval_extrema

    algebra_response = _build_algebra_response(normalized)
    if algebra_response is not None:
        return algebra_response

    extended = _resolve_extended_chapter(normalized)
    if extended is not None:
        return _build_extended_chapter_response(*extended)

    intent = _detect_intent(normalized)
    if intent == "verify":
        return _build_derivative_response(normalized)
    if intent == "integrate":
        return _build_integral_response(normalized)
    if intent == "limit":
        return _build_limit_response(normalized)
    if intent == "plot":
        return _build_plot_response(normalized)
    fallback = _needs_input(
        "我还没识别出具体要计算的内容。请把题目、条件和要求写清楚；"
        "图片题可以先识别，再回复“确认”继续。"
    )
    fallback["intent"] = "unknown"
    return fallback


def _build_knowledge_response(query: str) -> dict[str, Any] | None:
    try:
        results = search_knowledge(query, limit=3)
    except Exception:
        return None
    if not results:
        return None

    top = results[0]
    reply = f"{top.title}：{top.excerpt}"
    if len(results) > 1:
        related = "、".join(result.title for result in results[1:])
        reply += f"\n\n还可以继续看：{related}。"
    return {
        "status": "ok",
        "intent": "knowledge",
        "reply": reply,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "sources": [
            {
                "title": result.title,
                "source": result.source,
                "chapter": result.chapter,
            }
            for result in results
        ],
        "suggestions": [
            "积分的基本性质是什么",
            "定积分和不定积分有什么区别",
        ],
    }


def _concept_help_response() -> dict[str, Any]:
    return {
        "status": "needs_input",
        "intent": "knowledge",
        "reply": (
            "这是概念问题，不是待计算的表达式。请把具体概念或定理写完整，"
            "例如“定积分的定义”“微积分基本定理”或“洛必达法则的适用条件”。"
        ),
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": [
            "定积分的定义",
            "导数的几何意义",
            "级数收敛的定义",
        ],
    }


def _build_normalized_expression_response(
    original: str,
    normalized: str,
) -> dict[str, Any] | None:
    if not _SPOKEN_EXPRESSION_HINT_PATTERN.search(original):
        return None
    expression_text = normalized.strip()
    if not expression_text or expression_text == original.strip():
        return None
    if not _is_parsable_expression(expression_text):
        return None

    expression = parse_math_expression(expression_text)
    rendered = str(expression)
    return _result_response(
        intent="normalize",
        reply=(
            f"已识别为 {rendered}。如果要继续计算，请补充“求导”、"
            "“积分”或“极限”等要求。"
        ),
        formula_latex=latex(expression),
        formula_text=rendered,
        calculation={
            "expression": rendered,
            "normalized": rendered,
        },
        suggestions=[
            f"求 {rendered} 的导数",
            f"求 {rendered} 的积分",
        ],
    )


def _build_arithmetic_response(message: str) -> dict[str, Any] | None:
    expression_text = message.strip()
    expression_text = re.sub(
        r"^\s*(?:请)?(?:计算|求值|算出)\s*[:：]?\s*",
        "",
        expression_text,
    )
    expression_text = re.sub(
        r"\s*=\s*[?？]?\s*$",
        "",
        expression_text,
    )
    expression_text = expression_text.strip(
        "=,，;；:：。！!?？"
    ).strip()
    if not expression_text:
        return None
    if not _ARITHMETIC_EXPRESSION_PATTERN.fullmatch(expression_text):
        return None
    if not re.search(r"\d", expression_text):
        return None
    if not _ARITHMETIC_OPERATOR_PATTERN.search(expression_text):
        return None

    try:
        expression = parse_math_expression(expression_text)
        result = simplify(expression)
    except ZeroDivisionError:
        return _arithmetic_error_response("除数不能为 0，请换一个非零除数再计算。")
    except Exception:
        return _arithmetic_error_response(
            "这个算式无法解析，请检查括号、运算符和数字是否完整。"
        )

    if getattr(result, "is_infinite", False):
        return _arithmetic_error_response("除数不能为 0，请换一个非零除数再计算。")

    if (
        not result.is_number
        or result.free_symbols
        or result.is_finite is not True
    ):
        return _arithmetic_error_response(
            "这个算式没有有限的实数结果，请检查除数或幂运算。"
        )

    if result.is_Integer:
        result_text = str(result)
    elif result.is_Rational:
        result_text = str(result)
    else:
        number = complex(result.evalf())
        if abs(number.imag) > 1e-12:
            return _arithmetic_error_response(
                "这个算式没有得到实数结果，请检查输入。"
            )
        result_text = format(number.real, ".15g")

    return _result_response(
        intent="arithmetic",
        reply=f"结果是 {result_text}。",
        formula_latex=f"{_to_latex(expression_text)}={_to_latex(result_text)}",
        formula_text=f"{expression_text} = {result_text}",
        calculation={
            "operation": "arithmetic",
            "expression": expression_text,
            "result": result_text,
        },
        suggestions=_HELP_SUGGESTIONS,
    )


def _arithmetic_error_response(reply: str) -> dict[str, Any]:
    return {
        "status": "error",
        "intent": "arithmetic",
        "reply": reply,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _build_interval_extrema_response(message: str) -> dict[str, Any] | None:
    match = re.search(
        r"函数\s*f\s*\(\s*x\s*\)\s*=\s*(?P<expression>.+?)\s*"
        r"在\s*(?:区间\s*)?(?P<left>[\(\[])\s*(?P<lower>.+?)\s*,"
        r"\s*(?P<upper>.+?)\s*(?P<right>[\)\]])\s*上(?:的)?"
        r"(?P<kind>最大值|最小值)",
        message,
    )
    if match is None:
        return None

    expression_text = match.group("expression").strip()
    expression_text = re.sub(
        r"\bln\s*([A-Za-z])",
        r"ln(\1)",
        expression_text,
        flags=re.IGNORECASE,
    )
    try:
        expression = parse_math_expression(expression_text)
        lower = _parse_interval_bound(match.group("lower"))
        upper = _parse_interval_bound(match.group("upper"))
    except Exception:
        return None

    variable = symbols("x", real=True)
    derivative = simplify(diff(expression, variable))
    critical_points = [
        point
        for point in solve(derivative, variable)
        if point.is_real is not False
    ]

    candidates: list[tuple[str, Any]] = []
    lower_value = complex(lower.evalf()) if lower.is_number else None
    upper_value = complex(upper.evalf()) if upper.is_number else None

    for point in critical_points:
        point_value = complex(point.evalf())
        if lower_value is not None and point_value.real < lower_value.real:
            continue
        if upper_value is not None and point_value.real > upper_value.real:
            continue
        candidates.append(
            (
                f"驻点 x={point}",
                simplify(expression.subs(variable, point)),
            )
        )

    try:
        if match.group("left") == "[":
            candidates.append(
                (
                    f"左端点 x={lower}",
                    simplify(expression.subs(variable, lower)),
                )
            )
        else:
            candidates.append(
                (
                    f"左端点 x={lower} 的极限",
                    limit(expression, variable, lower, dir="+"),
                )
            )
        if match.group("right") == "]":
            candidates.append(
                (
                    f"右端点 x={upper}",
                    simplify(expression.subs(variable, upper)),
                )
            )
        else:
            candidates.append(
                (
                    f"右端点 x={upper} 的极限",
                    limit(expression, variable, upper, dir="-"),
                )
            )
    except Exception:
        return None

    real_candidates = [
        (label, value)
        for label, value in candidates
        if value.is_real is not False
    ]
    if not real_candidates:
        return None

    kind = match.group("kind")
    if kind == "最大值":
        selected_label, selected_value = max(
            real_candidates,
            key=lambda item: float(item[1].evalf()),
        )
    else:
        selected_label, selected_value = min(
            real_candidates,
            key=lambda item: float(item[1].evalf()),
        )
    selected_value = simplify(selected_value)
    detail = "；".join(
        f"{label}: f(x)={simplify(value)}"
        for label, value in real_candidates
    )
    interval_text = (
        f"{match.group('left')}{lower}, {upper}{match.group('right')}"
    )
    return _result_response(
        intent="solve",
        reply=(
            f"函数在区间 {interval_text} 上的{kind}是 {selected_value}。"
            f"求导得 f'(x)={derivative}，比较驻点和端点后，"
            f"{selected_label} 取到{kind}。"
        ),
        formula_latex=(
            rf"\max_{{x\in{interval_text}}}"
            rf"\left({latex(expression)}\right)={latex(selected_value)}"
            if kind == "最大值"
            else rf"\min_{{x\in{interval_text}}}"
            rf"\left({latex(expression)}\right)={latex(selected_value)}"
        ),
        formula_text=f"{kind} = {selected_value}",
        calculation={
            "expression": str(expression),
            "variable": "x",
            "interval": interval_text,
            "kind": kind,
            "derivative": str(derivative),
            "critical_points": [str(point) for point in critical_points],
            "candidates": detail,
            "result": str(selected_value),
        },
        suggestions=_HELP_SUGGESTIONS,
    )


def _solve_confirmed_question(
    question: str,
    history: list[DemoChatHistoryMessage] | None = None,
) -> dict[str, Any]:
    """Solve a confirmed OCR question without exposing general-chat failures."""
    cleaned = re.split(
        r"(?:\u786e\u8ba4\u65e0\u8bef|\u8bf7\u6838\u5bf9|"
        r"\u56de\u590d[\u201c\"']?\u786e\u8ba4[\u201d\"']?)",
        str(question),
        maxsplit=1,
    )[0].strip()
    cleaned = strip_question_number_prefix(cleaned)
    if not cleaned:
        return _needs_input(
            "\u8bf7\u5148\u4e0a\u4f20\u6216\u8f93\u5165\u9700\u8981\u89e3\u7b54\u7684\u9898\u76ee\u3002"
        )

    generic_interval_response = solve_interval_extrema(cleaned)
    if generic_interval_response is not None:
        return generic_interval_response

    normalized = _normalize_text(cleaned)
    for candidate in (cleaned, normalized):
        try:
            result = (
                _build_interval_extrema_response(candidate)
                or _build_confirmed_interval_extrema_response(candidate)
            )
        except Exception:
            result = None
        if result is not None:
            return result

    try:
        math_response = _math_response(normalized)
    except Exception:
        math_response = _needs_input("")
        math_response["intent"] = "unknown"

    if math_response.get("intent") != "unknown":
        return math_response

    general_response = _build_general_chat_response(
        f"\u5f85\u89e3\u9898\u76ee\uff1a{cleaned}",
        None,
        CONFIRMED_SOLVE_SYSTEM_PROMPT,
    )
    if general_response is not None and general_response.get("status") != "error":
        return general_response

    fallback = _needs_input("")
    fallback["status"] = "error"
    fallback["intent"] = "solve"
    fallback["reply"] = (
        "已经读取到题目，但题型识别或确定性求解阶段没有完成，"
        "因此不会继续生成教学步骤或知识点建议。"
        "请保留参数方程、参数点以及切线/法线、积分、极限等具体要求，"
        "修改题干后重新发送；如果原题含多个小问，请先发送当前要计算的那一问。"
    )
    return fallback


def _build_confirmed_interval_extrema_response(
    question: str,
) -> dict[str, Any] | None:
    """Retry OCR interval-extrema questions through a canonical form."""
    text = normalize_math_text(str(question))
    text = unicodedata.normalize("NFKC", text).replace("\n", " ").strip()
    if not text:
        return None

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

    if "\u6700\u5927\u503c" in text:
        kind = "\u6700\u5927\u503c"
    elif "\u6700\u5c0f\u503c" in text:
        kind = "\u6700\u5c0f\u503c"
    else:
        return None

    interval_match = re.search(
        r"(?:\u533a\u95f4|\u5728)\s*"
        r"(?P<left>[\(\[])\s*(?P<lower>[^,\)\]]+?)\s*,\s*"
        r"(?P<upper>[^\)\]]+?)\s*(?P<right>[\)\]])",
        text,
    )
    if interval_match is None:
        return None

    function_match = re.search(
        r"(?:[fgh]\s*\(\s*[A-Za-z]\s*\)|y)\s*=",
        text,
    )
    if function_match is None:
        return None

    equals_index = text.find("=", function_match.start(), interval_match.start())
    if equals_index < 0:
        return None

    expression_text = text[equals_index + 1 : interval_match.start()]
    expression_text = re.split(
        r"(?:\u5219|\u5f53|\u5728|\u533a\u95f4|[,;\uFF0C\uFF1B\u3002])",
        expression_text,
        maxsplit=1,
    )[0].strip()
    if not expression_text:
        return None

    canonical_question = (
        f"f(x)={expression_text}\u5728\u533a\u95f4"
        f"{interval_match.group('left')}{interval_match.group('lower')},"
        f"{interval_match.group('upper')}{interval_match.group('right')}"
        f"\u4e0a\u7684{kind}"
    )
    return _build_interval_extrema_response(canonical_question)


def _parse_interval_bound(value: str):
    cleaned = _clean_expression(value.strip())
    if cleaned.lower() in {"e", "exp(1)"}:
        return E
    return parse_math_expression(cleaned)


def _build_general_chat_response(
    message: str,
    history: list[DemoChatHistoryMessage] | None,
    system_prompt: str = GENERAL_CHAT_SYSTEM_PROMPT,
) -> dict[str, Any] | None:
    if not GENERAL_CHAT_API_KEY or not GENERAL_CHAT_API_URL:
        return None

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    for item in (history or [])[-6:]:
        role = item.get("role") if isinstance(item, dict) else item.role
        text = item.get("text") if isinstance(item, dict) else item.text
        if role in {"user", "assistant"} and text.strip():
            messages.append({"role": role, "content": text.strip()})
    messages.append({"role": "user", "content": message})

    solve_mode = system_prompt == CONFIRMED_SOLVE_SYSTEM_PROMPT
    payload = json.dumps(
        {
            "model": GENERAL_CHAT_MODEL,
            "messages": messages,
            "temperature": 0.15 if solve_mode else 0.3,
            "max_tokens": (
                CONFIRMED_SOLVE_MAX_TOKENS
                if solve_mode
                else GENERAL_CHAT_MAX_TOKENS
            ),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        GENERAL_CHAT_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {GENERAL_CHAT_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=GENERAL_CHAT_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
        choice = data["choices"][0]
        reply = choice["message"]["content"].strip()
        finish_reason = str(choice.get("finish_reason") or "").lower()
    except HTTPError as exc:
        print(
            f"general_chat_request_failed: HTTPError: {exc.code}",
            flush=True,
        )
        return _general_chat_error(_general_chat_http_error_message(exc.code))
    except (URLError, TimeoutError, OSError) as exc:
        print(
            f"general_chat_request_failed: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return _general_chat_error()
    except Exception as exc:
        print(
            f"general_chat_request_failed: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return _general_chat_error()

    if not reply:
        return _general_chat_error()
    if finish_reason == "length":
        return _general_chat_error(
            "问答服务返回的解析被截断，为避免给出不完整结论，本次结果未采用。"
            "请把题目拆成较小的一问后重试；高数求导、积分和极限仍可直接输入计算。"
        )
    if finish_reason == "content_filter":
        return _general_chat_error(
            "问答服务未返回完整解析，请调整题目表述后重试。"
        )
    if solve_mode:
        invalid_reason = _confirmed_solve_reply_invalid_reason(reply)
        if invalid_reason:
            return _general_chat_error(
                f"问答服务返回的解题结果不完整（{invalid_reason}），"
                "为避免误导未采用该结果。请保留原题重新发送，或拆成单问后再试；"
                "高数求导、积分和极限可直接使用确定性计算。"
            )
    if solve_mode:
        return {
            "status": "unverified",
            "intent": "general",
            "reply": (
                "以下为未经独立验算的参考解析，不能替代确定性求解结果；"
                "教学步骤、知识点和错题本不会据此生成。\n\n"
                f"{reply}"
            ),
            "formula_latex": "",
            "formula_text": "",
            "calculation": None,
            "verified": False,
            "verification": failed_verification(
                "model_solution",
                "模型参考解析未经过独立符号计算与结果验算",
            ),
            "suggestions": _HELP_SUGGESTIONS,
        }

    return {
        "status": "ok",
        "intent": "general",
        "reply": reply,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _confirmed_solve_reply_invalid_reason(reply: str) -> str | None:
    """Return why a model-written confirmed solution is unsafe to display."""
    text = str(reply or "").strip()
    if len(text) < 40:
        return "内容过短"

    positions = [text.find(heading) for heading in _CONFIRMED_SOLVE_HEADINGS]
    if any(position < 0 for position in positions):
        return "缺少统一的四段结构"
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        return "四段结构顺序错误"

    for index, heading in enumerate(_CONFIRMED_SOLVE_HEADINGS):
        content_start = positions[index] + len(heading)
        content_end = (
            positions[index + 1]
            if index + 1 < len(positions)
            else len(text)
        )
        section = text[content_start:content_end]
        section = re.sub(r"[\s#*`：:>\-]+", "", section)
        if len(section) < 2:
            return f"{heading}部分为空"

    if _UNVERIFIED_TOOL_CLAIM_PATTERN.search(text):
        return "包含未经核验的工具调用声明"
    return None


def _general_chat_http_error_message(status_code: int) -> str:
    suffix = "高数计算仍可继续使用。"
    if status_code == 401:
        return f"普通问答服务鉴权失败，请联系管理员检查 API Key；{suffix}"
    if status_code == 403:
        return (
            "普通问答免费额度已用尽或服务已暂停，"
            f"请在百炼控制台检查额度与停止策略；{suffix}"
        )
    if status_code == 429:
        return f"普通问答请求过于频繁，请稍后重试；{suffix}"
    if status_code >= 500:
        return f"普通问答服务返回临时错误，请稍后重试；{suffix}"
    return f"普通问答服务暂时不可用，请稍后再试；{suffix}"


def _general_chat_error(reply: str = "") -> dict[str, Any]:
    return {
        "status": "error",
        "intent": "general",
        "reply": reply or "普通问答服务暂时不可用，请稍后再试；高数计算仍可继续使用。",
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _build_algebra_response(message: str) -> dict[str, Any] | None:
    determinant = _build_determinant_response(message)
    if determinant is not None:
        return determinant
    return _build_equation_response(message)


def _build_equation_response(message: str) -> dict[str, Any] | None:
    if "微分方程" in message:
        return None

    match = re.search(
        r"^(?:请|帮我)?\s*(?:求解|解|求)\s*(?:下列|这个|该)?\s*"
        r"(?:一元(?:一次|二次|三次)?|方程)\s*[:：]?\s*(?P<equation>.+)$",
        message,
    )
    if match is None:
        match = re.search(
            r"^(?:请|帮我)?\s*求\s*(?P<equation>[^,，。;；]+=[^,，。;；]+)"
            r"\s*的(?:解|根)$",
            message,
        )
    if match is None:
        return None

    equation_text = _strip_expression_tail(match.group("equation")).strip(
        " .。"
    )
    if equation_text.count("=") != 1:
        return None
    left_text, right_text = equation_text.split("=", 1)
    try:
        difference = simplify(
            parse_math_expression(left_text)
            - parse_math_expression(right_text)
        )
    except Exception as exc:
        return _calculation_error(exc)

    variables = sorted(difference.free_symbols, key=str)
    if not variables:
        return _needs_input("这个等式里没有待求解的未知数，请补充方程。")

    variable_match = re.search(
        r"(?:关于|对)\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:求解|求根|解方程)?",
        message,
    )
    if variable_match:
        variable_name = variable_match.group(1)
        variable = symbols(variable_name)
        if variable not in variables:
            return _needs_input(
                f"方程中没有未知数 {variable_name}，请核对题目。"
            )
    else:
        variable = variables[0]

    solutions = solve(difference, variable)
    solution_texts = [str(solution) for solution in solutions]
    result_text = str(solution_texts)
    return _result_response(
        intent="solve",
        reply=(
            f"方程的解是 {result_text}。"
            "代回原方程就能检验结果，你可以任选一个解试一下。"
        ),
        formula_latex=(
            f"{_to_latex(equation_text)}\\Rightarrow "
            f"{latex(variable)}={latex(solutions)}"
        ),
        formula_text=f"{equation_text} => {result_text}",
        calculation={
            "method": "方程求解",
            "equation": equation_text,
            "variable": str(variable),
            "solutions": solution_texts,
            "result": result_text,
        },
        suggestions=["解方程 x^2-1=0", "求矩阵 [[1,2],[3,4]] 的行列式"],
    )


def _build_determinant_response(message: str) -> dict[str, Any] | None:
    match = re.search(
        r"(?:矩阵|matrix)\s*(?P<matrix>\[\[.+\]\])\s*"
        r"(?:的)?\s*(?:行列式|determinant|det)",
        message,
        re.IGNORECASE,
    )
    if match is None:
        return None

    try:
        raw_matrix = ast.literal_eval(match.group("matrix"))
        matrix = Matrix(raw_matrix)
    except (SyntaxError, TypeError, ValueError) as exc:
        return _calculation_error(exc)

    if matrix.rows != matrix.cols:
        return _needs_input("只有方阵才有行列式，请检查矩阵的行数和列数。")

    determinant = simplify(matrix.det())
    return _result_response(
        intent="solve",
        reply=(
            f"矩阵的行列式是 {determinant}。"
            "行列式会用在可逆性和线性方程组判断中。"
        ),
        formula_latex=rf"\det\left({latex(matrix)}\right)={latex(determinant)}",
        formula_text=f"det({matrix}) = {determinant}",
        calculation={
            "method": "矩阵行列式",
            "matrix": str(matrix),
            "result": str(determinant),
        },
        suggestions=["求矩阵 [[1,2],[3,4]] 的行列式", "解方程 x^2-1=0"],
    )


def _build_extended_chapter_response(
    chapter: str,
    topic: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = solve_chapter(chapter, topic, inputs)
    except MissingInputError as exc:
        return _missing_chapter_input_response(exc, chapter, topic)
    except SolveError as exc:
        return _calculation_error(exc)

    method = result["method"]
    value = result["result"]
    notes = result.get("notes") or []
    latex_result = result.get("latex") or _to_latex(value)
    details = result.get("details")
    solution_sections = None
    if (
        chapter == "derivatives"
        and topic == "parametric_tangent_normal"
        and isinstance(details, dict)
    ):
        solution_sections = _format_parametric_tangent_normal_solution(
            details
        )
    if solution_sections is None:
        solution_sections = _format_generic_chapter_solution(
            method=method,
            inputs=inputs,
            value=value,
            latex_result=latex_result,
            notes=notes,
        )
    understanding, strategy, steps, conclusion = solution_sections
    reply = _format_math_solution_reply(
        understanding=understanding,
        strategy=strategy,
        steps=steps,
        conclusion=conclusion,
    )
    hint = _EXTENDED_CHAPTER_HINTS.get((chapter, topic), {})
    response = _result_response(
        intent="solve",
        reply=reply,
        formula_latex=latex_result,
        formula_text=f"{method}: {value}",
        calculation=result,
        suggestions=hint.get("suggestions", _HELP_SUGGESTIONS),
    )
    if is_verified_solution(response) and isinstance(details, dict):
        knowledge_points = details.get("knowledge_points")
        if isinstance(knowledge_points, list) and knowledge_points:
            response["knowledge_points"] = knowledge_points
    return response


def _format_generic_chapter_solution(
    *,
    method: str,
    inputs: dict[str, Any],
    value: str,
    latex_result: str,
    notes: list[Any],
) -> tuple[str, str, str, str]:
    condition_lines = _format_chapter_conditions(inputs)
    understanding = f"本题要求使用“{method}”完成计算。"
    if condition_lines:
        understanding += f"\n已确认的题目条件：\n{condition_lines}"

    strategy = (
        f"根据上述条件确定{method}的计算对象与适用范围，"
        "按对应定义或判定定理完成化简，"
        "最后将结果代回原条件进行独立复算。"
    )
    step_lines = [
        "1. 整理题目中的表达式、变量、区间或方程等已知条件。"
    ]
    step_lines.extend(
        f"{index}. {str(note).strip().rstrip('。；;')}。"
        for index, note in enumerate(notes, start=2)
        if str(note).strip()
    )
    result_latex = str(latex_result or "").strip() or _to_latex(value)
    step_lines.extend(
        (
            (
                f"{len(step_lines) + 1}. 应用{method}的定义、公式或判定条件"
                "完成计算与化简。"
            ),
            (
                f"{len(step_lines) + 2}. 将结果代回原条件独立复算，"
                f"得到 ${result_latex}$，验算通过。"
            ),
        )
    )
    steps = "\n".join(step_lines)
    conclusion = (
        f"计算结果为 ${result_latex}$。"
        "该结果已通过独立复算和结果一致性检查。"
    )
    return understanding, strategy, steps, conclusion


_CHAPTER_INPUT_LABELS = {
    "expression": "表达式",
    "x_expression": "x 的参数表达式",
    "y_expression": "y 的参数表达式",
    "upper_expression": "上边界函数",
    "lower_expression": "下边界函数",
    "equation": "方程",
    "equations": "方程组",
    "constraint": "约束条件",
    "constraints": "约束条件",
    "variable": "自变量",
    "variables": "变量",
    "parameter": "参数",
    "parameter_value": "参数取值",
    "function": "未知函数",
    "dependent": "因变量",
    "dependents": "因变量",
    "left": "第一个向量",
    "right": "第二个向量",
    "vector": "向量",
    "lower": "下限",
    "upper": "上限",
    "lower_x": "x 下限",
    "upper_x": "x 上限",
    "lower_y": "y 下限",
    "upper_y": "y 上限",
    "lower_z": "z 下限",
    "upper_z": "z 上限",
    "point": "取值点",
    "direction": "方向",
    "order": "阶数",
    "kind": "目标类型",
}


def _format_chapter_conditions(inputs: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in inputs.items():
        if value is None or value == "" or value == []:
            continue
        label = _CHAPTER_INPUT_LABELS.get(key, str(key))
        lines.append(f"- {label}：{_format_chapter_condition_value(key, value)}")
    return "\n".join(lines)


def _format_chapter_condition_value(key: str, value: Any) -> str:
    if isinstance(value, dict):
        assignments = ", ".join(
            f"{_to_latex(str(name))}={_to_latex(str(item))}"
            for name, item in value.items()
        )
        return f"$({assignments})$"
    if isinstance(value, (list, tuple)):
        parts = [_format_chapter_condition_value(key, item) for item in value]
        if key in {"left", "right", "vector"}:
            values = ", ".join(_to_latex(str(item)) for item in value)
            return f"$({values})$"
        separator = "、" if key in {"variables", "dependents", "equations"} else ", "
        return separator.join(parts)

    text = str(value).strip()
    if key in {
        "variable",
        "variables",
        "parameter",
        "function",
        "dependent",
        "dependents",
    }:
        return f"${_to_latex(text)}$"
    if key in {"order", "kind"}:
        return text
    return f"${_to_latex(text)}$"


def _format_parametric_tangent_normal_solution(
    details: dict[str, Any],
) -> tuple[str, str, str, str] | None:
    required_keys = (
        "x_expression",
        "y_expression",
        "parameter",
        "parameter_value",
        "point_x",
        "point_y",
        "dx_dt",
        "dy_dt",
        "dx_value",
        "dy_value",
        "tangent_kind",
        "tangent_slope",
        "normal_slope",
        "tangent_latex",
        "normal_latex",
    )
    values = {
        key: str(details.get(key) or "").strip()
        for key in required_keys
    }
    if any(not value for value in values.values()):
        return None

    parameter = values["parameter"]
    parameter_value = values["parameter_value"]
    x_latex = _to_latex(values["x_expression"])
    y_latex = _to_latex(values["y_expression"])
    parameter_latex = _to_latex(parameter_value)
    tangent_latex = values["tangent_latex"]
    normal_latex = values["normal_latex"]
    point_text = (
        f"$\\left({_to_latex(values['point_x'])},"
        f"{_to_latex(values['point_y'])}\\right)$"
    )

    understanding = (
        f"已知参数方程 $x={x_latex}$、$y={y_latex}$，"
        f"要求在 ${parameter}={parameter_latex}$ 处的切线方程和法线方程。"
    )
    strategy = (
        f"先分别求 $dx/d{parameter}$ 和 $dy/d{parameter}$，"
        "再把参数值代入得到切点和切向量；接着由切向量确定切线斜率，"
        "用法线斜率与切线斜率的负倒数关系写出两条直线，最后复核。"
    )

    step_lines = [
        (
            f"1. 对 $x={x_latex}$ 关于 ${parameter}$ 求导，"
            f"得到 $\\dfrac{{dx}}{{d{parameter}}}="
            f"{_to_latex(values['dx_dt'])}$。"
        ),
        (
            f"2. 对 $y={y_latex}$ 关于 ${parameter}$ 求导，"
            f"得到 $\\dfrac{{dy}}{{d{parameter}}}="
            f"{_to_latex(values['dy_dt'])}$。"
        ),
        (
            f"3. 代入 ${parameter}={parameter_latex}$，得到切点 "
            f"{point_text}，且 "
            f"$\\dfrac{{dx}}{{d{parameter}}}="
            f"{_to_latex(values['dx_value'])}$、"
            f"$\\dfrac{{dy}}{{d{parameter}}}="
            f"{_to_latex(values['dy_value'])}$。"
        ),
    ]

    tangent_kind = values["tangent_kind"]
    if tangent_kind == "slope":
        step_lines.append(
            f"4. 切线斜率 $k_T=\\dfrac{{dy/d{parameter}}}"
            f"{{dx/d{parameter}}}={_to_latex(values['tangent_slope'])}$；"
            f"法线斜率 $k_N=-\\dfrac{{1}}{{k_T}}="
            f"{_to_latex(values['normal_slope'])}$。"
        )
    elif tangent_kind == "vertical":
        step_lines.append(
            "4. 该点处 $dx/d"
            f"{parameter}=0$，所以切线竖直、普通斜率不存在；"
            "法线水平，法线斜率为 $0$。"
        )
    else:
        step_lines.append(
            "4. 该点处 $dy/d"
            f"{parameter}=0$，所以切线水平、斜率为 $0$；"
            "法线竖直，普通斜率不存在。"
        )

    step_lines.extend(
        (
            f"5. 切线经过切点 {point_text}，方程为 "
            f"$ {tangent_latex} $。",
            f"6. 法线经过同一坐标的切点，方程为 "
            f"$ {normal_latex} $。",
            (
                "7. 复核切点代入结果，并检查切线与法线的方向互相垂直；"
                "两项检查均与参数导数关系一致。"
            ),
        )
    )
    conclusion = (
        f"切点为 {point_text}；"
        f"切线方程为 $ {tangent_latex} $；"
        f"法线方程为 $ {normal_latex} $。"
    )
    return understanding, strategy, "\n".join(step_lines), conclusion


def _missing_chapter_input_response(
    exc: MissingInputError,
    chapter: str,
    topic: str,
) -> dict[str, Any]:
    field = str(getattr(exc, "field", "") or "").strip()
    hint = _EXTENDED_CHAPTER_HINTS.get((chapter, topic), {})
    if field == "parameter_value":
        reply = (
            "这道参数方程切线/法线题还缺少参数点。"
            "请补充参数值，例如 t=pi/4 或 t=1。"
        )
    elif field == "equation" and chapter == "differential_equations":
        reply = (
            "这道微分方程题还缺少方程表达式。"
            "请写出完整方程，例如 y'-y=0。"
        )
    else:
        reply = str(hint.get("missing") or "").strip()
        if not reply:
            reply = (
                "这道题还缺少可验证的必要条件。"
                f"请补充输入项：{field or '题目条件'}。"
            )
    reply += "缺少这些条件时，我不会生成最终答案、教学步骤或知识点推荐。"
    response = _needs_input(reply, intent="solve")
    response["missing_fields"] = [field] if field else []
    return response


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
        if (
            _detect_intent(normalized)
            not in {"verify", "integrate", "limit", "plot"}
            and _resolve_extended_chapter(normalized) is None
        ):
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
    normalized = normalize_math_text(str(value))
    return " ".join(normalized.translate(_TEXT_REPLACEMENTS).strip().split())


def _is_confirmation(value: str) -> bool:
    compact = re.sub(r"[\s,，。！!?？；;]", "", value)
    exact_confirmations = {
        "确认",
        "正确",
        "无误",
        "对的",
        "是的",
        "是这题",
        "就是这题",
        "就是这道",
        "就是这道题",
        "题目没问题",
        "识别没问题",
        "继续",
        "正确继续",
        "正确继续解题",
        "确认继续",
        "请继续",
    }
    if compact in exact_confirmations:
        return True
    if len(compact) <= 12 and any(
        marker in compact
        for marker in ("确认", "正确", "无误", "继续", "开始")
    ):
        return True
    return False


def _is_rejection(value: str) -> bool:
    compact = re.sub(r"[\s,，。！!?？]", "", value)
    return compact in {
        "不对",
        "不正确",
        "错误",
        "识别错误",
        "识别不正确",
        "题目不正确",
        "题目错误",
        "不是这题",
        "不是这道",
        "不是这道题",
        "重新识别",
        "重新上传",
        "重新上传图片",
        "我要重新上传",
        "重新发图片",
    }


def _pending_ocr_question(
    history: list[DemoChatHistoryMessage] | None,
) -> str:
    for item in reversed(history or []):
        role = item.get("role") if isinstance(item, dict) else item.role
        text = item.get("text") if isinstance(item, dict) else item.text
        if role != "user" or not isinstance(text, str):
            continue
        question = _extract_ocr_question(text)
        if question:
            return question
    return ""


def _extract_ocr_question(value: str) -> str:
    markers = (
        "请你确认题目识别是否正确",
        "请确认识别是否正确",
        "请确认图片识别结果是否正确",
        "请确认识别结果是否正确",
        "请确认识别的题目是否正确",
        "请确认你识别的题目是否正确",
        "我将为你求解并判断结果",
        "我将开始计算",
    )
    marker_indexes = [
        value.find(marker)
        for marker in markers
        if value.find(marker) > 0
    ]
    generic_marker = re.search(
        r"(?:请确认.{0,12}识别.{0,12}是否正确|"
        r"我将为你求解|确认无误回复)",
        value,
    )
    if generic_marker and generic_marker.start() > 0:
        marker_indexes.append(generic_marker.start())
    if marker_indexes:
        return value[: min(marker_indexes)].strip()
    return ""


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
        "你是谁",
        "你叫什么",
        "你是什么",
        "自我介绍",
        "介绍一下你",
        "介绍一下自己",
        "知微是谁",
    }


def _detect_intent(value: str) -> str:
    lowered = value.lower()
    if re.search(r"(?:极限|lim(?:it)?|limit)", lowered):
        return "limit"
    if (
        "积分" in value
        or "∫" in value
        or _parse_integral(value) is not None
    ):
        return "integrate"
    if (
        re.search(r"(?:求导|导数|导函数|微分|d\s*/\s*d)", lowered)
        or _parse_derivative(value) is not None
    ):
        return "verify"
    if _PLOT_KEYWORDS.search(value):
        return "plot"
    return "unknown"


_PLOT_KEYWORDS = re.compile(
    r"(?:画|绘制|画出|作出|作图|函数图像|函数图象|函数图形|图像|图象|plot)",
    re.IGNORECASE,
)

_HELP_REPLIES = (
    (
        "我在。把题目发来就行，文字或图片都可以；"
        "我先算结果，再和你一起看关键步骤。"
    ),
    (
        "可以，直接发题。求导、积分、极限、函数图像，"
        "以及后面的章节题都能一起处理。"
    ),
    (
        "发完整题目或题目图片都可以，不用提前改写格式。"
    ),
    (
        "把题意和已知条件带上就好；"
        "如果题目不完整，我会先告诉你还缺什么。"
    ),
)

_PLOT_RANGE_BRACKET = re.compile(
    r"\[\s*(?P<low>-?\d+(?:\.\d+)?)\s*,\s*(?P<high>-?\d+(?:\.\d+)?)\s*\]"
)

_PLOT_RANGE_SPAN = re.compile(
    r"(?P<low>-?\d+(?:\.\d+)?)\s*(?:到|至|~)\s*(?P<high>-?\d+(?:\.\d+)?)"
)


def _format_plot_number(value: float) -> str:
    return f"{value:g}"


def _is_parsable_expression(value: str) -> bool:
    try:
        parse_math_expression(value)
    except Exception:
        return False
    return True


def _parse_plot(message: str) -> tuple[str, str, float, float] | None:
    text = message
    x_min, x_max = -10.0, 10.0
    span = _PLOT_RANGE_BRACKET.search(text) or _PLOT_RANGE_SPAN.search(text)
    if span:
        x_min = float(span.group("low"))
        x_max = float(span.group("high"))
        text = f"{text[: span.start()]} {text[span.end() :]}"
        text = re.sub(
            r"\s*(?:从|在|上|范围是|范围|区间|其中|∈)\s*$",
            "",
            text,
        )
        text = re.sub(r"[,，]\s*[A-Za-z]\s*$", "", text)
    if x_min >= x_max:
        return None

    cleaned = re.sub(
        r"^(?:帮我|请|麻烦|来|给我)?\s*"
        r"(?:绘制|画出|作出|作图|作|画|plot)\s*",
        "",
        text.strip(),
        count=1,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:函数|曲线)\s*", "", cleaned)
    cleaned = re.sub(r"^[yY]\s*=\s*", "", cleaned)
    cleaned = re.sub(r"^f\s*\(\s*x\s*\)\s*=\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\s*(?:的)?\s*(?:函数)?\s*(?:图像|图象|图形|曲线|图)\s*$",
        "",
        cleaned,
    )
    cleaned = _clean_expression(cleaned.strip(" ,，。;；"))
    if not cleaned:
        return None
    if not _is_parsable_expression(cleaned):
        trimmed = re.sub(r"[,，]?\s*[A-Za-z]\s*$", "", cleaned).strip(" ,，。;；")
        if trimmed and _is_parsable_expression(trimmed):
            cleaned = trimmed

    variable = _infer_variable(message, cleaned)
    return cleaned, variable, x_min, x_max


def _build_plot_response(message: str) -> dict[str, Any]:
    parsed = _parse_plot(message)
    if parsed is None:
        return _needs_input(
            "请写出要画图的函数和自变量范围，例如"
            "“画函数 y=sin(x)，x 从 -3 到 3”。"
        )

    expression, variable, x_min, x_max = parsed
    if not _is_parsable_expression(expression):
        return _needs_input(
            "这个函数表达式暂时无法解析，请换一种写法，例如"
            "“画函数 y=sin(x)，x 从 -3 到 3”。"
        )

    plot_url = "/demo/api/plot.svg?" + urlencode(
        {
            "expression": expression,
            "variable": variable,
            "x_min": _format_plot_number(x_min),
            "x_max": _format_plot_number(x_max),
            "samples": 80,
            "width": 640,
            "height": 360,
        }
    )
    low = _format_plot_number(x_min)
    high = _format_plot_number(x_max)
    return _result_response(
        intent="plot",
        reply=(
            f"函数图像已经画好，自变量 {variable} 的范围是 {low} 到 {high}。"
            "你能指出它的单调区间吗？"
        ),
        formula_latex=rf"y={_to_latex(expression)}",
        formula_text=f"y = {expression}",
        calculation={
            "expression": expression,
            "variable": variable,
            "x_min": x_min,
            "x_max": x_max,
            "plot_url": plot_url,
        },
        suggestions=[
            "画函数 y=x^2，x 从 -3 到 3",
            "画函数 y=sin(x)，x 从 -6 到 6",
        ],
    )


def _format_math_solution_reply(
    *,
    understanding: str,
    strategy: str,
    steps: str,
    conclusion: str,
) -> str:
    return "\n\n".join(
        (
            f"**题目理解**\n{understanding}",
            f"**解题思路**\n{strategy}",
            f"**详细计算步骤**\n{steps}",
            f"**最终答案**\n{conclusion}",
        )
    )


def _build_derivative_response(message: str) -> dict[str, Any]:
    parsed = _parse_derivative(message)
    if parsed is None:
        return _needs_input(
            "请写出要求和导的函数，例如“求导 x^2”或"
            "“判断 2x 是不是 x^2 的导数”。"
        )

    expression, variable, candidate, order, point = parsed
    if order == 1 and point is None:
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
            rf"\frac{{d}}{{d{result['variable']}}}"
            rf"\left({expression_latex}\right)"
            rf"={result['derivative_latex']}"
        )
        formula_text = (
            f"d/d{result['variable']} ({result['expression']}) = "
            f"{result['derivative']}"
        )

        understanding = (
            f"求函数 $f({result['variable']})={expression_latex}$ "
            "的一阶导数。"
        )
        strategy = (
            "按照基本求导公式、乘积法则和链式法则逐项求导，"
            "再核对候选答案是否与求导结果恒等。"
        )
        steps = (
            f"对 $f({result['variable']})={expression_latex}$ 求导，"
            f"得到 ${result['derivative_latex']}$。"
        )
        if result["candidate"] is None:
            conclusion = (
                f"导数为 ${result['derivative_latex']}$。"
            )
        elif result["is_correct"]:
            steps += (
                f" 候选答案 ${_to_latex(result['candidate'])}$ "
                "与求导结果化简后恒等。"
            )
            conclusion = (
                f"这个答案是对的，导数是 ${result['derivative_latex']}$。"
            )
        else:
            steps += (
                f" 候选答案 ${_to_latex(result['candidate'])}$ "
                "与求导结果化简后不恒等。"
            )
            conclusion = (
                "这里还差一点，"
                f"正确导数是 ${result['derivative_latex']}$。"
            )
        reply = _format_math_solution_reply(
            understanding=understanding,
            strategy=strategy,
            steps=steps,
            conclusion=conclusion,
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

    try:
        expression_value = parse_math_expression(expression)
        variable_value = symbols(variable)
        derivative_value = simplify(
            diff(expression_value, variable_value, order)
        )
        answer = derivative_value
        if point is not None:
            answer = simplify(
                derivative_value.subs(
                    variable_value,
                    parse_math_expression(point),
                )
            )
        candidate_value = (
            parse_math_expression(candidate) if candidate else None
        )
        is_correct = (
            simplify(answer - candidate_value) == 0
            if candidate_value is not None
            else None
        )
    except Exception as exc:
        return _calculation_error(exc)

    expression_latex = latex(expression_value)
    if order == 1:
        derivative_operator = rf"\frac{{d}}{{d{variable}}}"
        derivative_text = "导数"
    else:
        derivative_operator = (
            rf"\frac{{d^{{{order}}}}}{{d{variable}^{{{order}}}}}"
        )
        derivative_text = f"{order} 阶导数"
    derivative_formula = (
        rf"{derivative_operator}\left({expression_latex}\right)"
    )
    if point is None:
        formula_latex = rf"{derivative_formula}={latex(answer)}"
        formula_text = (
            f"{derivative_text} of {expression} = {answer}"
        )
    else:
        formula_latex = (
            rf"\left.{derivative_formula}\right|_"
            rf"{{{variable}={_to_latex(point)}}}={latex(answer)}"
        )
        formula_text = (
            f"{derivative_text} of {expression} at {variable}={point} "
            f"= {answer}"
        )

    if point is not None:
        understanding = (
            f"求函数 ${expression_latex}$ 在 "
            f"${variable}={_to_latex(point)}$ 处的"
            f"{derivative_text}值。"
        )
    else:
        understanding = (
            f"求函数 ${expression_latex}$ 的{derivative_text}。"
        )
    strategy = (
        "先按基本求导公式、乘积法则或链式法则求导函数，"
        "再按题目要求代入指定点或做候选答案恒等检查。"
    )
    steps = (
        f"求导得到 ${derivative_formula}={latex(derivative_value)}$。"
    )
    if point is not None:
        steps += (
            f" 代入 ${variable}={_to_latex(point)}$，"
            f"得到 ${latex(answer)}$。"
        )
    if candidate is not None:
        if is_correct:
            steps += (
                f" 候选答案 ${_to_latex(candidate)}$ "
                "与计算结果化简后恒等。"
            )
            conclusion = (
                f"这个答案是对的，{derivative_text}结果是 ${latex(answer)}$。"
            )
        else:
            steps += (
                f" 候选答案 ${_to_latex(candidate)}$ "
                "与计算结果化简后不恒等。"
            )
            conclusion = (
                "这里还差一点，"
                f"正确{derivative_text}结果是 ${latex(answer)}$。"
            )
    else:
        conclusion = f"{derivative_text}结果是 ${latex(answer)}$。"
    reply = _format_math_solution_reply(
        understanding=understanding,
        strategy=strategy,
        steps=steps,
        conclusion=conclusion,
    )

    return _result_response(
        intent="verify",
        reply=reply,
        formula_latex=formula_latex,
        formula_text=formula_text,
        calculation={
            "expression": str(expression_value),
            "variable": variable,
            "derivative": str(answer),
            "derivative_latex": latex(answer),
            "derivative_function": str(derivative_value),
            "order": order,
            "point": point,
            "candidate": candidate,
            "is_correct": is_correct,
        },
        suggestions=[
            "求二阶导 x^3",
            "求 f(x)=x^2 在 x=2 的导数值",
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

    if lower is not None and upper is not None:
        understanding = (
            f"计算函数 ${expression_latex}$ 关于 "
            f"${result['variable']}$ 的定积分，"
            f"积分区间为 ${_to_latex(lower)}$ 到 "
            f"${_to_latex(upper)}$。"
        )
        strategy = (
            "先求出原函数，再代入上限和下限相减；"
            "必要时通过原函数求导检查积分结果。"
        )
        steps = (
            rf"$\int_{{{_to_latex(lower)}}}^{{{_to_latex(upper)}}}"
            rf"{expression_latex}\,d{result['variable']}"
            rf"={result['integral_latex']}$。"
        )
        conclusion_value = f"${result['integral_latex']}$"
    else:
        understanding = (
            f"计算函数 ${expression_latex}$ 关于 "
            f"${result['variable']}$ 的不定积分。"
        )
        strategy = (
            "先求出原函数，并通过原函数的导数是否等于被积函数"
            "来检查结果，最后补上任意常数 $C$。"
        )
        steps = (
            rf"$\int {expression_latex}\,d{result['variable']}"
            rf"={result['integral_latex']}+C$。"
        )
        conclusion_value = f"${result['integral_latex']}+C$"

    if result["candidate"] is None:
        conclusion = f"{result_label}结果是 {conclusion_value}。"
    elif result["is_correct"]:
        steps += (
            f" 候选答案 ${_to_latex(result['candidate'])}$ "
            "与计算结果化简后恒等。"
        )
        conclusion = (
            f"这个答案是对的，{result_label}结果是 {conclusion_value}。"
        )
    else:
        steps += (
            f" 候选答案 ${_to_latex(result['candidate'])}$ "
            "与计算结果化简后不恒等。"
        )
        conclusion = (
            f"这里还差一点，正确{result_label}结果是 {conclusion_value}。"
        )
    reply = _format_math_solution_reply(
        understanding=understanding,
        strategy=strategy,
        steps=steps,
        conclusion=conclusion,
    )

    return _result_response(
        intent="integrate",
        reply=reply,
        formula_latex=formula_latex,
        formula_text=formula_text,
        calculation={
            **result,
            "lower": lower,
            "upper": upper,
        },
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

    direction_text = {
        "+": "右极限",
        "-": "左极限",
        None: "双侧极限",
    }[result["direction"]]
    understanding = (
        f"求函数 ${_to_latex(result['expression'])}$ 在 "
        f"${result['variable']}\to {_to_latex(result['point'])}$ 时的"
        f"{direction_text}。"
    )
    if result["direction"] is None:
        strategy = (
            "分别计算左极限和右极限，再比较两侧趋势；"
            "只有两侧都收敛且结果一致时，双侧极限才存在。"
        )
    else:
        strategy = (
            "沿着题目指定的方向计算单侧极限，并检查结果是否收敛。"
        )

    if result["direction"] is None:
        steps = (
            f"左极限为 ${_to_latex(result['left_limit'])}$，"
            f"右极限为 ${_to_latex(result['right_limit'])}$。"
            f" {result['explanation']}"
        )
    else:
        steps = (
            f"{direction_text}计算得到 ${result['limit_latex']}$。"
            f" {result['explanation']}"
        )

    if result["exists"]:
        conclusion_value = f"${result['limit_latex']}$"
    else:
        conclusion_value = "不存在"

    if result["candidate"] is None:
        conclusion = f"该{direction_text}为 {conclusion_value}。"
    elif result["is_correct"]:
        conclusion = (
            f"这个答案是对的，该{direction_text}为 {conclusion_value}。"
        )
    else:
        conclusion = (
            f"这里还差一点，该{direction_text}应为 {conclusion_value}。"
        )
    if not result["exists"]:
        conclusion += f" {result['explanation']}"
    reply = _format_math_solution_reply(
        understanding=understanding,
        strategy=strategy,
        steps=steps,
        conclusion=conclusion,
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


_DERIVATIVE_ORDER_PATTERN = r"(?:\d+|[一二两三四五六七八九十]+)"
_CHINESE_NUMBER_VALUES = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _parse_derivative_order(message: str) -> int:
    order_match = re.search(
        rf"(?:第)?\s*(?P<order>{_DERIVATIVE_ORDER_PATTERN})"
        r"\s*阶\s*(?:导|导数)",
        message,
    )
    if order_match:
        order_text = order_match.group("order")
        if order_text.isdigit():
            return int(order_text)
        if order_text in _CHINESE_NUMBER_VALUES:
            return _CHINESE_NUMBER_VALUES[order_text]

    prime_match = re.search(r"f\s*(?P<primes>['′]+)", message)
    if prime_match:
        return len(prime_match.group("primes"))
    return 1


def _parse_derivative_point(message: str, variable: str) -> str | None:
    function_point = re.search(
        r"f\s*['′]+\s*\(\s*(?P<point>[^()]+?)\s*\)",
        message,
    )
    if function_point:
        point = _clean_math_fragment(function_point.group("point"))
        if point and point != variable:
            return point

    at_point = re.search(
        r"(?:在|当)\s*(?:[A-Za-z][A-Za-z0-9_]*\s*=\s*)?"
        r"(?P<point>[^,，;；\s]+)\s*(?:处|点)?\s*"
        r"(?:的)?(?:导数值|导数)",
        message,
    )
    if at_point:
        point = _clean_math_fragment(at_point.group("point"))
        if point and point != variable:
            return point
    return None


def _parse_derivative(
    message: str,
) -> tuple[str, str, str | None, int, str | None] | None:
    candidate: str | None = None
    expression: str | None = None
    variable_override: str | None = None
    order = _parse_derivative_order(message)

    relation = re.search(
        r"^\s*is\s+(?P<first>.+?)\s+(?:the\s+)?"
        r"(?:derivative|antiderivative)\s+of\s+"
        r"(?P<second>.+?)\s*[?？]?\s*$",
        message,
        re.IGNORECASE,
    )
    if relation is None:
        relation = re.search(
            r"^\s*(?P<first>.+?)\s+is\s+(?:the\s+)?"
            r"(?:derivative|antiderivative)\s+of\s+"
            r"(?P<second>.+?)\s*[?？]?\s*$",
            message,
            re.IGNORECASE,
        )
    if relation:
        candidate = _clean_math_fragment(relation.group("first"))
        expression = _clean_expression(relation.group("second"))
    else:
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
        function_match = re.search(
            r"(?:f|g|h)\s*\(\s*(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*\)"
            r"\s*=\s*(?P<expr>.+?)"
            r"(?=\s*(?:[,，;；]|(?:在|求|计算|的)|$))",
            message,
            re.IGNORECASE,
        )
        if function_match:
            expression = _clean_expression(function_match.group("expr"))
            variable_override = function_match.group("variable")
        else:
            differential_match = re.search(
                r"^(?:帮我|请|计算|求)?\s*d\s*/\s*d"
                r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
                r"(?P<expr>.+)$",
                message,
                re.IGNORECASE,
            )
            if differential_match:
                expression = _clean_expression(
                    differential_match.group("expr")
                )
                variable_override = differential_match.group("variable")
            else:
                advanced_patterns = (
                    (
                        rf"^(?:帮我|请|计算|求)?\s*(?:第)?"
                        rf"{_DERIVATIVE_ORDER_PATTERN}\s*阶\s*"
                        r"(?:导数|导)\s*(?:为|是|:)?\s*(?P<expr>.+)$",
                        None,
                    ),
                    (
                        rf"^(?:求|计算|帮我|请)?\s*(?P<expr>.+?)\s*"
                        rf"的(?:第)?{_DERIVATIVE_ORDER_PATTERN}\s*阶\s*"
                        r"(?:导数|导)(?:是多少)?$",
                        None,
                    ),
                    (
                        r"^(?:求|计算|帮我|请)?\s*(?P<expr>.+?)\s*在\s*"
                        r"(?:[A-Za-z][A-Za-z0-9_]*\s*=\s*)?"
                        r"[^,，;；\s]+\s*(?:处|点)?\s*的"
                        r"(?:导数值|导数)$",
                        None,
                    ),
                    (
                        r"^对\s*(?P<expr>.+?)\s*求(?:关于|对)\s*"
                        r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*的"
                        r"(?:导函数|导数)$",
                        "variable",
                    ),
                )
                for pattern, variable_group in advanced_patterns:
                    advanced_match = re.search(
                        pattern,
                        message,
                        re.IGNORECASE,
                    )
                    if advanced_match:
                        expression = _clean_expression(
                            advanced_match.group("expr")
                        )
                        if variable_group:
                            variable_override = advanced_match.group(
                                variable_group
                            )
                        break

    if expression is None:
        patterns = (
            r"^(?:帮我|请|来|计算|求)?\s*(?:求导|求导数|求导函数)\s*"
            r"(?:为|是|:)?\s*(.+)$",
            r"^(?:帮我|请|计算|求)?\s*(?:导数|微分)\s*(?:为|是|:)?\s*(.+)$",
            r"^(.+?)\s*的(?:导函数|导数)(?:是多少)?$",
            r"^(?:please\s+)?(?:(?:compute|calculate|find|evaluate|"
            r"determine|take|get|what\s+is)\s+)?"
            r"(?:the\s+)?(?:derivative|differentiate|differentiation)\s*"
            r"(?:of|for)?\s*(?:(?:the\s+)?function\s+)?(.+?)\s*$",
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

    variable = variable_override or _infer_variable(message, expression)
    point = _parse_derivative_point(message, variable)
    return expression, variable, candidate, order, point


def _parse_integral(
    message: str,
) -> tuple[str, str, str | None, str | None, str | None] | None:
    candidate: str | None = None
    expression: str | None = None
    lower: str | None = None
    upper: str | None = None

    relation = re.search(
        r"^\s*is\s+(?P<first>.+?)\s+(?:the\s+)?"
        r"(?:integral|antiderivative)\s+of\s+"
        r"(?P<second>.+?)\s*[?？]?\s*$",
        message,
        re.IGNORECASE,
    )
    if relation is None:
        relation = re.search(
            r"^\s*(?P<first>.+?)\s+is\s+(?:the\s+)?"
            r"(?:integral|antiderivative)\s+of\s+"
            r"(?P<second>.+?)\s*[?？]?\s*$",
            message,
            re.IGNORECASE,
        )
    if relation:
        candidate = _clean_math_fragment(relation.group("first"))
        expression = _clean_expression(relation.group("second"))
    else:
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
            r"^(?:please\s+)?(?:(?:compute|calculate|find|evaluate|"
            r"determine)\s+)?(?:the\s+)?(?:definite\s+)?"
            r"(?:integral|integrate)\s+from\s+(?P<lower>[^\s,]+)\s+"
            r"to\s+(?P<upper>[^\s,]+)\s+(?:of\s+)?(?P<expr>.+)$",
            r"^(?:please\s+)?(?:(?:compute|calculate|find|evaluate|"
            r"determine)\s+)?(?:the\s+)?(?:definite\s+)?"
            r"(?:integral|integrate|antiderivative)\s+(?:of\s+)?"
            r"(?P<expr>.+?)\s+from\s+(?P<lower>[^\s,]+)\s+"
            r"to\s+(?P<upper>[^\s,]+)\s*$",
            r"(?:积分|∫)\s*(?:从\s*)?(?P<lower>[^\s,]+)\s*"
            r"(?:到|至)\s*(?P<upper>[^\s,]+)\s*(?P<expr>.+)$",
            r"(?P<expr>.+?)\s*(?:从|在)\s*(?P<lower>[^\s,，]+?)\s*"
            r"到\s*(?P<upper>[^\s,，]+?)\s*(?:上\s*)?"
            r"的(?:定积分|积分)$",
            r"∫\s*_?\s*(?P<lower>[^\s^]+)\s*\^\s*"
            r"(?P<upper>[^\s]+)\s*(?P<expr>.+)$",
            r"^(?:计算|求|请)?\s*(?:当\s*)?"
            r"[A-Za-z]\s*从\s*(?P<lower>[^\s,，]+)\s*"
            r"到\s*(?P<upper>[^\s,，]+)\s*(?:时|的时候)\s*"
            r"(?P<expr>.+?)\s*的(?:定积分|积分)$",
        )
        for pattern in bound_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                candidate_expression = _clean_integrand(
                    match.group("expr")
                )
                if not candidate_expression:
                    continue
                lower = _clean_math_fragment(match.group("lower"))
                upper = _clean_math_fragment(match.group("upper"))
                expression = candidate_expression
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
                r"^(?:please\s+)?(?:(?:compute|calculate|find|evaluate|"
                r"determine|get)\s+)?(?:the\s+)?"
                r"(?:indefinite\s+)?(?:integral|integrate|antiderivative)"
                r"\s*(?:of|for)?\s*(?:(?:the\s+)?integrand\s+)?(.+)$",
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
    limit_direction_pattern = r"(?:趋近于?|趋于|接近|→|->)"
    limit_point_pattern = (
        r"[+-]?(?:(?:\d+(?:\.\d+)?|pi|e)"
        r"(?:\s*(?:\^?[+-]|正|负))?"
        r"|[正负]?无穷(?:大)?|oo|∞|[A-Za-z][A-Za-z0-9_]*)"
    )

    lim_match = re.search(
        r"(?:求|计算)?\s*(?:极限\s*)?lim(?:it)?\s*_?\s*\{?\s*"
        r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
        rf"{limit_direction_pattern}\s*"
        rf"(?P<point>{limit_point_pattern})\s*\}}?\s*"
        r"(?P<expr>.+?)\s*$",
        message,
        re.IGNORECASE,
    )
    if lim_match:
        variable = lim_match.group("variable")
        point = lim_match.group("point")
        expression = _clean_expression(lim_match.group("expr"))
    else:
        chinese_match = re.search(
            r"^\s*(?:求|计算|请)?\s*(?:当\s*)?"
            r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
            rf"{limit_direction_pattern}\s*(?P<point>.+?)\s*"
            r"(?:时|的时候)\s*(?P<expr>.+?)\s*"
            r"(?:的)?(?:左极限|右极限|极限)$",
            message,
            re.IGNORECASE,
        )
        front_expression_match = re.search(
            r"^\s*(?:求|计算|请)?\s*(?:当\s*)?"
            r"(?P<expr>.+?)\s*"
            r"(?:在|当)\s*(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
            rf"{limit_direction_pattern}\s*(?P<point>.+?)\s*"
            r"(?:时|的时候)\s*(?:的)?(?:左极限|右极限|极限)$",
            message,
            re.IGNORECASE,
        )
        if chinese_match:
            variable = chinese_match.group("variable")
            point = chinese_match.group("point")
            expression = _clean_expression(chinese_match.group("expr"))
        elif front_expression_match:
            variable = front_expression_match.group("variable")
            point = front_expression_match.group("point")
            expression = _clean_expression(
                front_expression_match.group("expr")
            )
        else:
            inline_match = re.search(
                r"(?:求|计算)?\s*(?:极限|lim(?:it)?)\s*"
                r"(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*"
                rf"{limit_direction_pattern}\s*"
                rf"(?P<point>{limit_point_pattern})\s*"
                r"(?:时|的时候)?\s*"
                r"(?P<expr>.+)$",
                message,
                re.IGNORECASE,
            )
            if inline_match:
                variable = inline_match.group("variable")
                point = inline_match.group("point")
                expression = _clean_expression(inline_match.group("expr"))
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
                    expression = _clean_expression(
                        trailing_match.group("expr")
                    )

    if expression is None or variable is None or point is None:
        return None

    direction = None
    if "右极限" in message:
        direction = "+"
    elif "左极限" in message:
        direction = "-"

    compact_point = re.sub(r"\s+", "", point)
    if direction is None:
        if compact_point.endswith("正"):
            direction = "+"
        elif compact_point.endswith("负"):
            direction = "-"
        elif compact_point.endswith("+") and compact_point not in {"+oo", "+∞"}:
            direction = "+"
        elif compact_point.endswith("-") and compact_point not in {"-oo", "-∞"}:
            direction = "-"

    if direction is not None:
        point = re.sub(
            r"(?:右极限|左极限|正|负|\^?[+-])\s*$",
            "",
            point,
        ).strip()

    point = point.replace("无穷大", "oo").replace("正无穷", "oo")
    point = point.replace("负无穷", "-oo").replace("无穷", "oo")
    point = point.replace("∞", "oo")
    if point in {"+∞", "+oo"}:
        point = "oo"
    elif point == "-oo":
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
    value = re.sub(
        r"^(?:the\s+)?(?:function|expression)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s*d[A-Za-z][A-Za-z0-9_]*\s*$", "", value)
    value = re.sub(
        r"\s+(?:with\s+respect\s+to|wrt)\s+[A-Za-z][A-Za-z0-9_]*\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
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
    english = re.search(
        r"\b(?:with\s+respect\s+to|wrt)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)",
        message,
        re.IGNORECASE,
    )
    if english:
        return english.group(1)

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
        "reply": secrets.choice(_HELP_REPLIES),
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _needs_input(
    reply: str,
    *,
    intent: str = "unknown",
) -> dict[str, Any]:
    return {
        "status": "needs_input",
        "intent": intent,
        "reply": reply,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _calculation_error(exc: Exception) -> dict[str, Any]:
    detail = getattr(exc, "detail", None) or str(exc) or "表达式无法解析"
    return {
        "status": "error",
        "intent": "calculation",
        "reply": (
            f"这次没算出来：{detail}。"
            "你可以把表达式写得更具体一些，我再试一次。"
        ),
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
    normalized_intent = str(intent or "").strip().lower()
    verification = None
    if normalized_intent in SOLUTION_INTENTS:
        verification = verify_calculation(normalized_intent, calculation)
        if verification.get("passed") is not True:
            failed_details = [
                str(check.get("detail") or check.get("name") or "")
                for check in verification.get("checks", [])
                if check.get("passed") is not True
            ]
            detail = "；".join(filter(None, failed_details))
            return {
                "status": "error",
                "intent": normalized_intent,
                "reply": (
                    "计算已经停止：结果没有通过独立验算"
                    + (f"（{detail}）" if detail else "")
                    + "。请核对题目条件和输入格式后重新提交。"
                ),
                "formula_latex": "",
                "formula_text": "",
                "calculation": None,
                "knowledge_points": [],
                "verified": False,
                "verification": verification,
                "suggestions": suggestions,
            }

    response = {
        "status": "ok",
        "intent": normalized_intent,
        "reply": reply,
        "formula_latex": formula_latex,
        "formula_text": formula_text,
        "calculation": calculation,
        "suggestions": suggestions,
    }
    if verification is not None:
        response["verified"] = True
        response["verification"] = verification
        if not is_verified_solution(response):
            return {
                "status": "error",
                "intent": normalized_intent,
                "reply": (
                    "计算已经停止：结果未通过统一成功门禁。"
                    "请核对题目条件和输入格式后重新提交。"
                ),
                "formula_latex": "",
                "formula_text": "",
                "calculation": None,
                "knowledge_points": [],
                "verified": False,
                "verification": verification,
                "suggestions": suggestions,
            }
    return response


def _build_interval_extrema_response(message: str) -> dict[str, Any] | None:
    """Solve single-variable extrema on an interval from OCR-style text."""
    message = unicodedata.normalize("NFKC", str(message))
    function_match = re.search(
        r"(?:f\s*\(\s*x\s*\)|y)\s*=\s*(?P<expression>.+?)"
        r"(?=(?:[,;\uFF0C\uFF1B\u3002]\s*)?"
        r"(?:\u5219|\u5728|\u5f53|\u533a\u95f4|$))",
        message,
    )
    interval_match = re.search(
        r"(?:(?:\u5728)?\s*\u533a\u95f4|\u5728)\s*"
        r"(?P<left>[\(\[])\s*(?P<lower>.+?)\s*,\s*"
        r"(?P<upper>.+?)\s*(?P<right>[\)\]])",
        message,
    )
    kind_match = re.search(
        r"(?P<kind>\u6700\u5927\u503c|\u6700\u5c0f\u503c)",
        message,
    )
    if (
        function_match is None
        or interval_match is None
        or kind_match is None
    ):
        return None

    expression_text = function_match.group("expression").strip()
    expression_text = re.sub(
        r"\b(?:in|1n)\s*([A-Za-z])",
        r"ln(\1)",
        expression_text,
        flags=re.IGNORECASE,
    )
    expression_text = re.sub(
        r"\bln\s*([A-Za-z])",
        r"ln(\1)",
        expression_text,
        flags=re.IGNORECASE,
    )
    try:
        expression = parse_math_expression(expression_text)
        lower = _parse_interval_bound(interval_match.group("lower"))
        upper = _parse_interval_bound(interval_match.group("upper"))
    except Exception:
        return None

    variable = symbols("x", real=True)
    derivative = simplify(diff(expression, variable))
    critical_points = [
        point
        for point in solve(derivative, variable)
        if point.is_real is not False
    ]

    candidates: list[tuple[str, Any]] = []
    lower_value = complex(lower.evalf()) if lower.is_number else None
    upper_value = complex(upper.evalf()) if upper.is_number else None

    for point in critical_points:
        point_value = complex(point.evalf())
        if lower_value is not None and point_value.real < lower_value.real:
            continue
        if upper_value is not None and point_value.real > upper_value.real:
            continue
        candidates.append(
            (
                f"\u9a7b\u70b9 x={point}",
                simplify(expression.subs(variable, point)),
            )
        )

    try:
        if interval_match.group("left") == "[":
            candidates.append(
                (
                    f"\u5de6\u7aef\u70b9 x={lower}",
                    simplify(expression.subs(variable, lower)),
                )
            )
        else:
            candidates.append(
                (
                    f"\u5de6\u7aef\u70b9 x={lower} \u7684\u6781\u9650",
                    limit(expression, variable, lower, dir="+"),
                )
            )
        if interval_match.group("right") == "]":
            candidates.append(
                (
                    f"\u53f3\u7aef\u70b9 x={upper}",
                    simplify(expression.subs(variable, upper)),
                )
            )
        else:
            candidates.append(
                (
                    f"\u53f3\u7aef\u70b9 x={upper} \u7684\u6781\u9650",
                    limit(expression, variable, upper, dir="-"),
                )
            )
    except Exception:
        return None

    real_candidates = [
        (label, value)
        for label, value in candidates
        if value.is_real is not False
    ]
    if not real_candidates:
        return None

    kind = kind_match.group("kind")
    if kind == "\u6700\u5927\u503c":
        selected_label, selected_value = max(
            real_candidates,
            key=lambda item: float(item[1].evalf()),
        )
    else:
        selected_label, selected_value = min(
            real_candidates,
            key=lambda item: float(item[1].evalf()),
        )
    selected_value = simplify(selected_value)
    detail = "\uff1b".join(
        f"{label}: f(x)={simplify(value)}"
        for label, value in real_candidates
    )
    interval_text = (
        f"{interval_match.group('left')}{lower}, "
        f"{upper}{interval_match.group('right')}"
    )
    return _result_response(
        intent="solve",
        reply=(
            f"\u51fd\u6570\u5728\u533a\u95f4 {interval_text} "
            f"\u4e0a\u7684{kind}\u662f {selected_value}\u3002"
            f"\u6c42\u5bfc\u5f97 f'(x)={derivative}\uff0c"
            "\u6bd4\u8f83\u9a7b\u70b9\u548c\u7aef\u70b9\u540e\uff0c"
            f"{selected_label} \u53d6\u5230{kind}\u3002"
        ),
        formula_latex=(
            rf"\max_{{x\in{interval_text}}}"
            rf"\left({latex(expression)}\right)={latex(selected_value)}"
            if kind == "\u6700\u5927\u503c"
            else rf"\min_{{x\in{interval_text}}}"
            rf"\left({latex(expression)}\right)={latex(selected_value)}"
        ),
        formula_text=f"{kind} = {selected_value}",
        calculation={
            "expression": str(expression),
            "variable": "x",
            "interval": interval_text,
            "kind": kind,
            "derivative": str(derivative),
            "critical_points": [str(point) for point in critical_points],
            "candidates": detail,
            "result": str(selected_value),
        },
        suggestions=_HELP_SUGGESTIONS,
    )
