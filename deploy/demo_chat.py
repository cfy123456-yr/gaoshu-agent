"""Conversational text adapter for the public math demo."""

from __future__ import annotations

import json
import os
import re
import secrets
import unicodedata
from typing import Any, Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sympy import E, diff, latex, limit, simplify, solve, symbols

from app.chapter_solvers import SolveError, solve_chapter
from app.main import (
    IntegrateRequest,
    LimitRequest,
    VerifyRequest,
    calculate_integral,
    calculate_limit,
    parse_math_expression,
    verify_derivative,
)
from deploy.demo_math_text import normalize_math_text
from deploy.demo_interval_solver import solve_interval_extrema


class DemoChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=600)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    history: list[DemoChatHistoryMessage] = Field(default_factory=list, max_length=20)
    source: Literal["text", "ocr"] = "text"
    pending_question: str = Field(default="", max_length=600)


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

GENERAL_CHAT_SYSTEM_PROMPT = """
你是“知微老师”，中文回答，核心专长是高等数学，也可以回答学习方法、
科学技术和生活常识等普通问题。回答要简洁、直接、诚实；不知道时明确说明，
不要编造事实或来源。涉及医疗、法律、金融等专业决定时，只提供一般信息，
并建议咨询专业人士。不要声称调用过数学工具；需要精确数学计算时，提醒用户
使用求导、积分、极限或全章节解题功能。
""".strip()

CONFIRMED_SOLVE_SYSTEM_PROMPT = """
你是“知微老师”，负责解答用户已经确认过的题目。请直接依据用户给出的
“待解题目”完成读题、考点判断和分步讲解，最后给出答案。题目若包含选择题，
请判断正确选项并说明理由。不要再次要求用户确认题目，不要说需要用户重新上传
图片，也不要因为题目文本有轻微 OCR 噪声就拒绝作答；可说明不确定之处后继续。
仅使用清晰、可核验的步骤，无法唯一确定答案时要明确指出缺少的条件。
""".strip()

_MATH_HINT_PATTERN = re.compile(
    r"(?:求导|导数|微分|积分|极限|级数|收敛|发散|函数图像|函数图象|"
    r"方程|向量|矩阵|偏导|梯度|重积分|曲线积分|曲面积分|\blim\b)",
    re.IGNORECASE,
)
_MATH_CONCEPT_TERM_PATTERN = re.compile(
    r"(?:导数|微分|积分|极限|偏导|梯度|重积分|曲线积分|曲面积分|级数|"
    r"洛必达法则|中值定理|泰勒公式)"
)
_MATH_CONCEPT_REQUEST_PATTERN = re.compile(
    r"(?:什么是|什么叫|定义|概念|含义|几何意义|物理意义|性质|"
    r"怎么理解|如何理解|解释一下|讲解一下|说明一下|有什么区别|关系)"
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
    ("vectors", "dot"): {
        "missing": "请写出两个向量，例如“向量 (1,2,3) 点乘 (4,5,6)”。",
        "suggestions": ["向量 (1,2,3) 点乘 (4,5,6)"],
    },
}


def _strip_expression_tail(value: str) -> str:
    cleaned = _CJK_EXPRESSION_TAIL.sub("", str(value)).strip()
    return cleaned.rstrip("，,。;；:：")


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


def _resolve_extended_chapter(message: str) -> tuple[str, str, dict[str, Any]] | None:
    compact = message.strip()

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

    if (
        "微分方程" in compact
        or ("=" in compact and re.search(r"\bdy\s*/\s*dx\b", compact))
        or re.search(r"\by\s*['′]\s*", compact)
    ):
        equation = re.sub(
            r"^(?:请|帮我)?\s*(?:求解|解)?\s*微分方程\s*",
            "",
            compact,
        )
        equation = re.sub(r"^(?:请|帮我)?\s*(?:求解|解)\s*", "", equation)
        equation = equation.replace("′", "'").replace("dy/dx", "y'")
        return (
            "differential_equations",
            "dsolve",
            {"equation": equation, "variable": "x", "function": "y"},
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
    if "点乘" in compact or "数量积" in compact:
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

    if "级数" in compact or "∑" in compact:
        if "求和" in compact or "和函数" in compact:
            match = re.search(r"(?:级数求和|级数和|求和)\s*(.+)", compact)
            if match:
                return (
                    "series",
                    "sum",
                    {"expression": _strip_expression_tail(match.group(1)), "variable": "n"},
                )
        if re.search(r"收敛|发散|敛散", compact):
            match = re.search(r"(?:判断)?\s*级数\s*(.+?)\s*(?:是否|收敛|发散|的敛散性|敛散性)", compact)
            if match is None:
                match = re.search(r"一般项\s*(.+)", compact)
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
) -> dict[str, Any]:
    normalized = _normalize_text(message)
    ocr_question = _extract_ocr_question(normalized)
    if ocr_question:
        response = _needs_input(
            f"题目已识别，请核对：{ocr_question}。"
            "确认无误回复“确认”，我将开始计算。"
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
        general_response = _build_general_chat_response(normalized, history)
        if general_response is not None:
            return general_response

    math_response = _math_response(normalized)
    if (
        math_response.get("intent") == "unknown"
        and not _MATH_HINT_PATTERN.search(normalized)
    ):
        general_response = _build_general_chat_response(normalized, history)
        if general_response is not None:
            return general_response
    return math_response


def _solve_confirmed_question(
    question: str,
    history: list[DemoChatHistoryMessage] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_text(question)
    try:
        interval_extrema = _build_interval_extrema_response(
            question
        ) or _build_interval_extrema_response(normalized)
    except Exception:
        interval_extrema = None
    if interval_extrema is not None:
        return interval_extrema

    try:
        math_response = _math_response(normalized)
    except Exception:
        math_response = _needs_input("")
        math_response["intent"] = "unknown"
    if math_response.get("intent") == "unknown":
        general_response = _build_general_chat_response(
            f"待解题目：{question}",
            None,
            CONFIRMED_SOLVE_SYSTEM_PROMPT,
        )
        if general_response is not None:
            return general_response
    return math_response


def _math_response(normalized: str) -> dict[str, Any]:
    if not normalized:
        return _needs_input("请先输入一道高等数学题目。")

    if _is_greeting(normalized):
        return _help_response()

    arithmetic = _build_arithmetic_response(normalized)
    if arithmetic is not None:
        return arithmetic

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
        "\u5df2\u7ecf\u8bfb\u53d6\u5230\u4f60\u786e\u8ba4\u7684\u9898\u76ee\uff0c"
        "\u4f46\u81ea\u52a8\u6c42\u89e3\u6682\u65f6\u6ca1\u6709\u5b8c\u6210\u3002"
        "\u8bf7\u4fdd\u7559\u9898\u5e72\u4e2d\u7684\u51fd\u6570\u3001\u533a\u95f4\u548c"
        "\u6700\u503c\u8981\u6c42\uff0c\u76f4\u63a5\u91cd\u65b0\u53d1\u9001\u4e00\u6b21\uff1b"
        "\u5982\u679c\u539f\u9898\u542b\u591a\u4e2a\u5c0f\u95ee\uff0c"
        "\u8bf7\u5148\u53d1\u9001\u5f53\u524d\u8981\u8ba1\u7b97\u7684\u90a3\u4e00\u95ee\u3002"
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

    payload = json.dumps(
        {
            "model": GENERAL_CHAT_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 800,
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
        reply = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(
            f"general_chat_request_failed: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return _general_chat_error()

    if not reply:
        return _general_chat_error()
    return {
        "status": "ok",
        "intent": "general",
        "reply": reply,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _general_chat_error() -> dict[str, Any]:
    return {
        "status": "error",
        "intent": "general",
        "reply": "普通问答服务暂时不可用，请稍后再试；高数计算仍可继续使用。",
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": _HELP_SUGGESTIONS,
    }


def _build_extended_chapter_response(
    chapter: str,
    topic: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = solve_chapter(chapter, topic, inputs)
    except SolveError as exc:
        return _calculation_error(exc)

    method = result["method"]
    value = result["result"]
    notes = result.get("notes") or []
    note_text = f" {notes[0]}。" if notes else ""
    reply = (
        f"结果是 {value}。这里用的是 {method}。{note_text}"
        "你可以先试着说说这个方法最关键的使用条件。"
    )
    hint = _EXTENDED_CHAPTER_HINTS.get((chapter, topic), {})
    return _result_response(
        intent="solve",
        reply=reply,
        formula_latex=result["latex"],
        formula_text=f"{method}: {value}",
        calculation=result,
        suggestions=hint.get("suggestions", _HELP_SUGGESTIONS),
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
    if re.search(r"(?:极限|\blim\b|limit)", lowered):
        return "limit"
    if "积分" in value or "∫" in value:
        return "integrate"
    if re.search(r"(?:求导|导数|导函数|微分|d\s*/\s*d)", lowered):
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
            f"答案是 {result['derivative']}。"
            "这一步主要看求导法则，你能认出用的是哪一条吗？"
        )
    elif result["is_correct"]:
        reply = (
            f"这个答案是对的，导数是 {result['derivative']}。"
            "再试着说说最关键的一步。"
        )
    else:
        reply = (
            f"这里还差一点，正确导数是 {result['derivative']}。"
            "先检查系数和符号，再回头看是否漏用了链式法则。"
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
            f"{result_label}结果是 {result['integral']}{suffix}。"
            "这题的关键在积分方法，你能看出该用哪一种吗？"
        )
    elif result["is_correct"]:
        reply = (
            f"这个答案是对的，{result_label}结果是 {result['integral']}。"
            "试着说说最关键的一步。"
        )
    else:
        reply = (
            f"这里还差一点，正确{result_label}结果是 {result['integral']}。"
            "先检查常数或上下限，再回头看基本积分公式。"
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
            f"极限是 {result['limit']}。"
            "这里最容易忽略趋近方向，你能判断是否需要区分左右极限吗？"
        )
    elif result["is_correct"]:
        reply = (
            f"这个答案是对的，极限是 {result['limit']}。"
            "再说明一下这个结论成立的依据。"
        )
    else:
        reply = (
            f"这里还差一点，正确极限是 {result['limit']}。"
            "先检查趋近方向，再确认等价无穷小或洛必达法则是否满足条件。"
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
        "reply": secrets.choice(_HELP_REPLIES),
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
    return {
        "status": "ok",
        "intent": intent,
        "reply": reply,
        "formula_latex": formula_latex,
        "formula_text": formula_text,
        "calculation": calculation,
        "suggestions": suggestions,
    }


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
