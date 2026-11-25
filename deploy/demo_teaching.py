"""Server-side teaching sessions for the public math demo."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
import math
import re
import threading
import time
import unicodedata
from typing import Any, Literal

from sympy import integrate, latex, simplify

from app.main import parse_math_expression
from app.solution_gate import is_verified_solution


TeachingAction = Literal[
    "start",
    "answer",
    "hint",
    "explain",
    "skip",
    "restart",
]

_SESSION_TTL_SECONDS = 30 * 60
_MAX_SESSIONS = 500
_NONEXISTENT_ANSWERS = {
    "不存在",
    "无极限",
    "极限不存在",
    "dne",
    "doesnotexist",
}
_ANSWER_PREFIX_PATTERN = re.compile(
    r"^(?:我的答案(?:是)?|答案是|结果是|导数是|积分是|极限是|"
    r"原函数是|选)[:：]?\s*",
    re.IGNORECASE,
)
_INTEGRATION_CONSTANT_PATTERN = re.compile(
    r"(?:\+|\-)\s*(?:c|c1|任意常数|常数)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TeachingStep:
    title: str
    prompt: str
    hint: str
    explanation: str
    expected: tuple[str, ...]
    match_kind: Literal["math", "method", "point", "equation"] = "math"


@dataclass(frozen=True)
class TeachingSnapshot:
    question: str
    solution: dict[str, Any]
    steps: tuple[TeachingStep, ...]
    current_index: int
    attempts: int
    phase: Literal["awaiting_answer", "complete"]
    hint_visible: bool
    explanation_visible: bool
    updated_at: float


@dataclass(frozen=True)
class TeachingTurn:
    snapshot: TeachingSnapshot
    event: Literal[
        "started",
        "correct",
        "wrong",
        "hint",
        "explain",
        "skipped",
        "restarted",
        "complete",
    ]
    feedback: str = ""
    review_title: str = ""
    review_explanation: str = ""


class TeachingSessionStore:
    """Thread-safe, bounded teaching state for one WSGI worker."""

    def __init__(self, ttl_seconds: float, max_sessions: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._lock = threading.RLock()
        self._sessions: dict[str, TeachingSnapshot] = {}

    def start(
        self,
        session_id: str,
        question: str,
        solution: dict[str, Any],
    ) -> TeachingTurn | None:
        steps = build_teaching_steps(question, solution)
        if not steps:
            return None
        snapshot = TeachingSnapshot(
            question=str(question).strip(),
            solution=copy.deepcopy(solution),
            steps=tuple(steps),
            current_index=0,
            attempts=0,
            phase="awaiting_answer",
            hint_visible=False,
            explanation_visible=False,
            updated_at=time.time(),
        )
        with self._lock:
            self._set_locked(session_id, snapshot)
        return TeachingTurn(snapshot=snapshot, event="started")

    def get(self, session_id: str) -> TeachingSnapshot | None:
        with self._lock:
            self._prune_locked()
            return self._sessions.get(session_id)

    def get_active(self, session_id: str) -> TeachingSnapshot | None:
        snapshot = self.get(session_id)
        if snapshot is None or snapshot.phase == "complete":
            return None
        return snapshot

    def apply(
        self,
        session_id: str,
        action: TeachingAction,
        answer: str = "",
    ) -> TeachingTurn | None:
        with self._lock:
            self._prune_locked()
            snapshot = self._sessions.get(session_id)
            if snapshot is None:
                return None
            turn = _apply_locked(snapshot, action, answer)
            self._set_locked(session_id, turn.snapshot)
            return turn

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _set_locked(
        self,
        session_id: str,
        snapshot: TeachingSnapshot,
    ) -> None:
        self._sessions.pop(session_id, None)
        self._sessions[session_id] = replace(snapshot, updated_at=time.time())
        while len(self._sessions) > self._max_sessions:
            oldest_session_id = min(
                self._sessions,
                key=lambda key: self._sessions[key].updated_at,
            )
            self._sessions.pop(oldest_session_id, None)

    def _prune_locked(self) -> None:
        now = time.time()
        for session_id, snapshot in list(self._sessions.items()):
            if now - snapshot.updated_at > self._ttl_seconds:
                self._sessions.pop(session_id, None)


def _apply_locked(
    snapshot: TeachingSnapshot,
    action: TeachingAction,
    answer: str,
) -> TeachingTurn:
    if action == "restart":
        restarted = replace(
            snapshot,
            current_index=0,
            attempts=0,
            phase="awaiting_answer",
            hint_visible=False,
            explanation_visible=False,
        )
        return TeachingTurn(
            snapshot=restarted,
            event="restarted",
            feedback="已从第 1 步重新开始。",
        )

    if snapshot.phase == "complete":
        return TeachingTurn(
            snapshot=snapshot,
            event="complete",
            feedback="这道题已经完成，可以重新开始再练一次。",
        )

    step = snapshot.steps[snapshot.current_index]
    if action == "hint":
        hinted = replace(snapshot, hint_visible=True)
        return TeachingTurn(
            snapshot=hinted,
            event="hint",
            feedback="先参考提示，自己写出这一步的关键结果。",
        )

    if action == "explain":
        explained = replace(snapshot, explanation_visible=True)
        return TeachingTurn(
            snapshot=explained,
            event="explain",
            feedback="这是当前步骤的解析；看懂后仍需提交答案或选择跳过。",
        )

    if action == "skip":
        return _advance(snapshot, "skipped", "已跳过本步，继续下一题组。")

    if action != "answer":
        raise ValueError("unsupported teaching action")

    if answer_matches(answer, step):
        return _advance(
            snapshot,
            "correct",
            "回答正确。",
            review_title=step.title,
            review_explanation=step.explanation,
        )

    wrong = replace(
        snapshot,
        attempts=snapshot.attempts + 1,
        hint_visible=True,
    )
    return TeachingTurn(
        snapshot=wrong,
        event="wrong",
        feedback="还差一点，先根据提示重新思考；这一步的答案先不公布。",
    )


def _advance(
    snapshot: TeachingSnapshot,
    event: Literal["correct", "skipped"],
    feedback: str,
    *,
    review_title: str = "",
    review_explanation: str = "",
) -> TeachingTurn:
    next_index = snapshot.current_index + 1
    if next_index >= len(snapshot.steps):
        complete = replace(
            snapshot,
            current_index=len(snapshot.steps),
            attempts=0,
            phase="complete",
            hint_visible=False,
            explanation_visible=False,
        )
        return TeachingTurn(
            snapshot=complete,
            event="complete",
            feedback=f"{feedback} 本题已完成。",
            review_title=review_title,
            review_explanation=review_explanation,
        )
    advanced = replace(
        snapshot,
        current_index=next_index,
        attempts=0,
        hint_visible=False,
        explanation_visible=False,
    )
    return TeachingTurn(
        snapshot=advanced,
        event=event,
        feedback=f"{feedback} 进入第 {next_index + 1} 步。",
        review_title=review_title,
        review_explanation=review_explanation,
    )


def build_teaching_steps(
    question: str,
    solution: dict[str, Any],
) -> list[TeachingStep]:
    if not is_verified_solution(solution):
        return []
    calculation = solution.get("calculation")
    if not isinstance(calculation, dict):
        return []
    intent = str(solution.get("intent") or "")
    if intent == "verify":
        return _derivative_steps(calculation)
    if intent == "integrate":
        return _integral_steps(calculation)
    if intent == "limit":
        return _limit_steps(calculation)
    if intent == "solve":
        return _chapter_steps(calculation)
    if intent == "arithmetic" and calculation.get("result"):
        return [
            TeachingStep(
                title="完成计算",
                prompt=f"请计算：{question}",
                hint="先确定运算顺序，再逐项化简。",
                explanation=f"按运算顺序计算，结果是 {_math_text(calculation['result'])}。",
                expected=(str(calculation["result"]),),
            )
        ]
    return []


def _derivative_steps(calculation: dict[str, Any]) -> list[TeachingStep]:
    expression = str(calculation.get("expression") or "")
    variable = str(calculation.get("variable") or "x")
    derivative = str(calculation.get("derivative") or "")
    derivative_function = str(
        calculation.get("derivative_function") or derivative
    )
    point = calculation.get("point")
    order = int(calculation.get("order") or 1)
    if not derivative:
        return []

    derivative_label = "一阶导数" if order == 1 else f"{order} 阶导数"
    if point is None:
        return [
            TeachingStep(
                title=f"求出{derivative_label}",
                prompt=(
                    f"先不看答案。请对 {_math_text(expression)} 求"
                    f"{derivative_label}，写出导函数。"
                ),
                hint=(
                    "先判断各项要用的求导法则；复合结构从外层向内层逐层求导，"
                    "乘法结构注意乘积法则。"
                ),
                explanation=(
                    f"逐项求导并化简后，得到 "
                    f"{_math_text(derivative_function)}。"
                ),
                expected=(derivative_function, derivative),
            )
        ]

    return [
        TeachingStep(
            title=f"先求{derivative_label}",
            prompt=(
                f"请先求 {_math_text(expression)} 的{derivative_label}，"
                "暂时不要代入定点。"
            ),
            hint="先完成符号求导，再处理题目给出的定点。",
            explanation=(
                f"先求导得到 {_math_text(derivative_function)}；"
                "下一步再代入定点。"
            ),
            expected=(derivative_function,),
        ),
        TeachingStep(
            title="代入定点",
            prompt=(
                f"把 {variable}={_math_text(point)} 代入刚才的导函数，"
                "写出最终数值。"
            ),
            hint="只做代入与算术化简，注意负号和括号。",
            explanation=(
                f"代入 {variable}={_math_text(point)} 后，"
                f"结果为 {_math_text(derivative)}。"
            ),
            expected=(derivative,),
        ),
    ]


def _integral_steps(calculation: dict[str, Any]) -> list[TeachingStep]:
    expression = str(calculation.get("expression") or "")
    variable = str(calculation.get("variable") or "x")
    integral = str(calculation.get("integral") or "")
    if not integral:
        return []

    bounds = _integral_bounds(calculation)
    if bounds is None:
        return [
            TeachingStep(
                title="求不定积分",
                prompt=(
                    f"请计算 {_math_text(expression)} 关于 {variable} 的不定积分，"
                    "写出一个原函数。"
                ),
                hint=(
                    "先看被积函数适合直接套基本积分公式，还是需要换元、"
                    "分部积分等变形。"
                ),
                explanation=(
                    f"求出原函数并整理后得到 {_math_text(integral)}；"
                    "不定积分还需补上任意常数 C。"
                ),
                expected=(integral,),
            )
        ]

    lower, upper = bounds
    try:
        antiderivative = str(
            integrate(parse_math_expression(expression), parse_math_expression(variable))
        )
    except Exception:
        antiderivative = ""

    steps: list[TeachingStep] = []
    if antiderivative:
        steps.append(
            TeachingStep(
                title="先求原函数",
                prompt=(
                    f"先求 {_math_text(expression)} 的一个原函数，"
                    "暂不代入积分上下限。"
                ),
                hint="先完成不定积分，再准备代入上下限。",
                explanation=(
                    f"可先取原函数 {_math_text(antiderivative)}；"
                    "下一步再代入上下限相减。"
                ),
                expected=(antiderivative,),
            )
        )
    steps.append(
        TeachingStep(
            title="代入上下限",
            prompt=(
                f"原函数在上限 {_math_text(upper)} 与下限 "
                f"{_math_text(lower)} 处相减，写出定积分的值。"
            ),
            hint="按“上限代入值减去下限代入值”计算，并检查符号。",
            explanation=f"代入上下限相减后，定积分为 {_math_text(integral)}。",
            expected=(integral,),
        )
    )
    return steps


def _limit_steps(calculation: dict[str, Any]) -> list[TeachingStep]:
    expression = str(calculation.get("expression") or "")
    variable = str(calculation.get("variable") or "x")
    point = str(calculation.get("point") or "0")
    direction = calculation.get("direction")
    limit_value = str(calculation.get("limit") or "不存在")
    exists = bool(calculation.get("exists", True))
    explanation = str(calculation.get("explanation") or "")
    if not expression:
        return []

    if direction is None:
        left = _limit_answer(calculation.get("left_limit"))
        right = _limit_answer(calculation.get("right_limit"))
        final = limit_value if exists else "不存在"
        steps = [
            TeachingStep(
                title="先求左极限",
                prompt=(
                    f"先沿 {variable}→{_math_text(point)}⁻ 求左极限，"
                    "写出你得到的结果。"
                ),
                hint="从小于趋近点的一侧观察函数值，必要时先化简函数。",
                explanation=(
                    f"左极限为 {_math_text(left)}。"
                    if left != "不存在"
                    else "左极限无法稳定确定。"
                ),
                expected=(left,),
            ),
            TeachingStep(
                title="再求右极限",
                prompt=(
                    f"再沿 {variable}→{_math_text(point)}⁺ 求右极限，"
                    "写出你得到的结果。"
                ),
                hint="从大于趋近点的一侧观察函数值，并保留函数式的定义域限制。",
                explanation=(
                    f"右极限为 {_math_text(right)}。"
                    if right != "不存在"
                    else "右极限无法稳定确定。"
                ),
                expected=(right,),
            ),
        ]
        final_hint = "比较左右极限是否都存在并且相等。"
        final_explanation = (
            f"左右极限同为 {_math_text(final)}，所以该极限存在。"
            if exists
            else explanation or "左右极限不一致，所以双侧极限不存在。"
        )
        steps.append(
            TeachingStep(
                title="判断双侧极限",
                prompt="比较左右极限，写出双侧极限的结果；如果不存在，请写“不存在”。",
                hint=final_hint,
                explanation=final_explanation,
                expected=(final,),
            )
        )
        return steps

    direction_text = "右极限" if direction == "+" else "左极限"
    final = limit_value if exists else "不存在"
    return [
        TeachingStep(
            title=f"求{direction_text}",
            prompt=(
                f"请沿指定方向求 {_math_text(expression)} 在 "
                f"{variable}→{_math_text(point)} 时的{direction_text}。"
            ),
            hint="先判断趋近方向，再化简函数并计算对应的单侧极限。",
            explanation=(
                f"{direction_text}为 {_math_text(final)}。"
                if final != "不存在"
                else explanation or f"{direction_text}不存在。"
            ),
            expected=(final,),
        )
    ]


def _chapter_steps(calculation: dict[str, Any]) -> list[TeachingStep]:
    topic = str(calculation.get("topic") or "")
    if topic == "parametric_tangent_normal":
        details = calculation.get("details")
        if not isinstance(details, dict):
            return []
        return _parametric_tangent_normal_steps(details)

    method = str(calculation.get("method") or "标准方法")
    result = str(calculation.get("result") or "")
    if not result:
        return []
    return [
        TeachingStep(
            title="先判断题型",
            prompt=(
                "先看题目条件和所求目标。这道题应采用什么方法？"
                "写出方法名称即可。"
            ),
            hint="从所求对象、已知条件和本章定理的名称中找到对应方法。",
            explanation=f"本题对应的方法是“{method}”。",
            expected=_method_aliases(method),
            match_kind="method",
        ),
        TeachingStep(
            title="完成标准计算",
            prompt=f"按“{method}”的标准步骤完成计算，写出最终结果。",
            hint="先把条件整理成标准形式，再代入公式或判定定理并化简。",
            explanation=f"完成化简后，得到 {_math_text(result)}。",
            expected=(result,),
        ),
    ]


def _parametric_tangent_normal_steps(
    details: dict[str, Any],
) -> list[TeachingStep]:
    required_keys = (
        "x_expression",
        "y_expression",
        "parameter",
        "parameter_value",
        "point_x",
        "point_y",
        "dx_dt",
        "dy_dt",
        "tangent_kind",
        "tangent_slope",
        "normal_slope",
        "tangent_result",
        "normal_result",
    )
    values = {
        key: str(details.get(key) or "").strip()
        for key in required_keys
    }
    if any(not value for value in values.values()):
        return []

    x_expression = values["x_expression"]
    y_expression = values["y_expression"]
    parameter = values["parameter"]
    parameter_value = values["parameter_value"]
    point_x = values["point_x"]
    point_y = values["point_y"]
    dx_dt = values["dx_dt"]
    dy_dt = values["dy_dt"]
    tangent_kind = values["tangent_kind"]
    tangent_slope = values["tangent_slope"]
    normal_slope = values["normal_slope"]
    tangent_result = values["tangent_result"]
    normal_result = values["normal_result"]

    if tangent_kind == "vertical":
        tangent_prompt = (
            f"在 {parameter}={parameter_value} 处，切线的方向是竖直还是水平？"
            "请说明切线斜率是否存在。"
        )
        tangent_expected = ("不存在", "竖直")
        tangent_hint = "先看 dx/dt 在该点的取值；若 dx/dt=0，切线竖直。"
        tangent_explanation = "dx/dt 在该点为 0，因此切线竖直，普通斜率不存在。"
        normal_slope_prompt = "竖直切线的法线是水平的，请写出法线斜率。"
        normal_slope_expected = ("0",)
    elif tangent_kind == "horizontal":
        tangent_prompt = (
            f"在 {parameter}={parameter_value} 处，切线的方向是竖直还是水平？"
            "请写出切线斜率。"
        )
        tangent_expected = ("0", "水平")
        tangent_hint = "先看 dy/dt 在该点的取值；若 dy/dt=0，切线水平。"
        tangent_explanation = "dy/dt 在该点为 0，因此切线水平，切线斜率为 0。"
        normal_slope_prompt = "水平切线的法线是竖直的，请写出法线斜率。"
        normal_slope_expected = ("不存在", "竖直")
    else:
        tangent_prompt = (
            f"用 dy/dx = (dy/dt)/(dx/dt) 求 {parameter}={parameter_value} "
            "处的切线斜率。"
        )
        tangent_expected = (tangent_slope,)
        tangent_hint = (
            "先把参数值代入 dx/dt 和 dy/dt，再用 dy/dt 除以 dx/dt。"
        )
        tangent_explanation = f"代入后得到切线斜率 {_math_text(tangent_slope)}。"
        normal_slope_prompt = (
            "切线斜率与法线斜率互为负倒数，请写出法线斜率。"
        )
        normal_slope_expected = (normal_slope,)

    if tangent_kind != "vertical" and normal_slope != "不存在":
        normal_slope_explanation = (
            f"法线斜率为切线斜率的负倒数，即 {_math_text(normal_slope)}。"
        )
    else:
        normal_slope_explanation = (
            "切线竖直时法线水平，因此法线斜率为 0。"
            if tangent_kind == "vertical"
            else "切线水平时法线竖直，因此法线斜率不存在。"
        )

    return [
        TeachingStep(
            title="先求 dx/dt",
            prompt=(
                f"对 x({parameter})={_math_text(x_expression)} 关于 "
                f"{parameter} 求导，写出 dx/d{parameter}。"
            ),
            hint="把参数方程中的 x 表达式单独求导，注意复合函数链式法则。",
            explanation=f"对 x 求参数导数，得到 {_math_text(dx_dt)}。",
            expected=(dx_dt,),
        ),
        TeachingStep(
            title="再求 dy/dt",
            prompt=(
                f"对 y({parameter})={_math_text(y_expression)} 关于 "
                f"{parameter} 求导，写出 dy/d{parameter}。"
            ),
            hint="把参数方程中的 y 表达式单独求导，留意内层系数的乘积。",
            explanation=f"对 y 求参数导数，得到 {_math_text(dy_dt)}。",
            expected=(dy_dt,),
        ),
        TeachingStep(
            title="求切点坐标",
            prompt=(
                f"把 {parameter}={parameter_value} 分别代入 x({parameter}) "
                "和 y({parameter})，写出切点坐标，可用 (x,y) 表示。"
            ),
            hint="横坐标代 x 的参数方程，纵坐标代 y 的参数方程，再分别化简。",
            explanation=(
                f"代入参数值后，切点为 ({_math_text(point_x)}, "
                f"{_math_text(point_y)})。"
            ),
            expected=(point_x, point_y),
            match_kind="point",
        ),
        TeachingStep(
            title="判断并求切线斜率",
            prompt=tangent_prompt,
            hint=tangent_hint,
            explanation=tangent_explanation,
            expected=tangent_expected,
        ),
        TeachingStep(
            title="求法线斜率",
            prompt=normal_slope_prompt,
            hint="法线斜率与切线斜率相乘等于 -1；水平与竖直切线要分别处理。",
            explanation=normal_slope_explanation,
            expected=normal_slope_expected,
        ),
        TeachingStep(
            title="写切线方程",
            prompt=(
                "用切点和切线斜率写出切线方程，保留 y=... 的形式。"
            ),
            hint="使用点斜式 y-y0=k(x-x0)，再展开并合并常数项。",
            explanation=f"整理后得到切线方程 {_math_text(tangent_result)}。",
            expected=(tangent_result,),
            match_kind="equation",
        ),
        TeachingStep(
            title="写法线方程",
            prompt=(
                "用同一切点和法线斜率写出法线方程，保留 y=... 的形式。"
            ),
            hint="仍使用点斜式，但斜率换成法线斜率；最后核对它经过切点。",
            explanation=f"整理后得到法线方程 {_math_text(normal_result)}。",
            expected=(normal_result,),
            match_kind="equation",
        ),
    ]


def answer_matches(answer: str, step: TeachingStep) -> bool:
    normalized = _normalize_answer(answer)
    if not normalized:
        return False
    if step.match_kind == "method":
        return any(
            _method_matches(normalized, expected)
            for expected in step.expected
        )
    if step.match_kind == "point":
        return _point_matches(normalized, step.expected)
    if step.match_kind == "equation":
        return any(
            _equation_matches(normalized, expected)
            for expected in step.expected
        )

    for expected in step.expected:
        expected_value = _normalize_answer(expected)
        if not expected_value:
            continue
        if normalized == expected_value:
            return True
        if (
            normalized in _NONEXISTENT_ANSWERS
            and expected_value in _NONEXISTENT_ANSWERS
        ):
            return True
        stripped = _INTEGRATION_CONSTANT_PATTERN.sub("", normalized).strip()
        if stripped and stripped == expected_value:
            return True
        if _math_equal(normalized, expected_value):
            return True
        if stripped and _math_equal(stripped, expected_value):
            return True
    return False


def _point_matches(answer: str, expected: tuple[str, ...]) -> bool:
    if len(expected) < 2:
        return False
    text = answer.strip().strip("()（）[]【】")
    x_match = re.search(r"x=([^,，;；]+)", text)
    y_match = re.search(r"y=([^,，;；]+)", text)
    if x_match and y_match:
        x_value = x_match.group(1).strip()
        y_value = y_match.group(1).strip()
    else:
        parts = re.split(r"[,，]", text, maxsplit=1)
        if len(parts) != 2:
            return False
        x_value, y_value = (part.strip() for part in parts)
    return _math_equal(x_value, expected[0]) and _math_equal(y_value, expected[1])


def _equation_matches(answer: str, expected: str) -> bool:
    answer_text = unicodedata.normalize("NFKC", str(answer or ""))
    expected_text = unicodedata.normalize("NFKC", str(expected or ""))
    answer_text = _ANSWER_PREFIX_PATTERN.sub("", answer_text).strip()
    expected_text = _ANSWER_PREFIX_PATTERN.sub("", expected_text).strip()
    if not answer_text or not expected_text:
        return False

    expected_parts = expected_text.split("=", 1)
    if len(expected_parts) != 2:
        return _math_equal(answer_text, expected_text)

    expected_left, expected_right = (
        part.strip() for part in expected_parts
    )
    answer_parts = answer_text.split("=", 1)
    if len(answer_parts) == 1:
        return _math_equal(answer_parts[0].strip(), expected_right)

    answer_left, answer_right = (
        part.strip() for part in answer_parts
    )
    try:
        answer_residual = simplify(
            parse_math_expression(answer_left)
            - parse_math_expression(answer_right)
        )
        expected_residual = simplify(
            parse_math_expression(expected_left)
            - parse_math_expression(expected_right)
        )
    except Exception:
        return False

    if answer_residual == 0 or expected_residual == 0:
        return answer_residual == expected_residual

    try:
        ratio = simplify(answer_residual / expected_residual)
    except Exception:
        return False
    if ratio.free_symbols or ratio.is_zero is not False:
        return False
    try:
        numeric_ratio = abs(float(ratio))
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(numeric_ratio) and numeric_ratio > 1e-12


def teaching_response(turn: TeachingTurn) -> dict[str, Any]:
    snapshot = turn.snapshot
    public = public_teaching(snapshot, turn)
    if snapshot.phase == "complete":
        if not is_verified_solution(snapshot.solution):
            failed_public = {
                **public,
                "active": False,
                "phase": "error",
                "step_title": "教学结果未通过验证",
                "prompt": (
                    "本次教学结果未通过统一验算，已停止展示完整答案和知识点。"
                    "请重新提交题目。"
                ),
                "feedback": "教学结果未通过验证。",
                "feedback_state": "wrong",
                "can_skip": False,
            }
            return {
                "status": "error",
                "intent": "teaching_failed",
                "reply": (
                    "教学结果未通过统一验算，系统已停止展示完整答案、"
                    "知识点和错题本入口。请重新提交题目。"
                ),
                "formula_latex": "",
                "formula_text": "",
                "calculation": None,
                "knowledge_points": [],
                "verified": False,
                "suggestions": [],
                "mode": "teach",
                "teaching": failed_public,
            }
        response = copy.deepcopy(snapshot.solution)
        response["mode"] = "teach"
        response["teaching"] = public
        response["reply"] = (
            f"{turn.feedback}\n\n{response.get('reply', '')}".strip()
        )
        return response

    step = snapshot.steps[snapshot.current_index]
    feedback = turn.feedback.strip()
    reply_parts = [part for part in (feedback, step.prompt) if part]
    return {
        "status": "ok",
        "intent": "teaching_step",
        "reply": "\n\n".join(reply_parts),
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": [],
        "mode": "teach",
        "teaching": public,
    }


def public_teaching(
    snapshot: TeachingSnapshot,
    turn: TeachingTurn | None = None,
) -> dict[str, Any]:
    complete = snapshot.phase == "complete"
    total = len(snapshot.steps)
    current = min(snapshot.current_index + 1, total)
    if complete:
        step_title = "本题完成"
        prompt = "所有步骤已完成。下面是完整解题过程和最终答案。"
    else:
        step = snapshot.steps[snapshot.current_index]
        step_title = step.title
        prompt = step.prompt
    return {
        "active": not complete,
        "phase": snapshot.phase,
        "question": snapshot.question,
        "current": current,
        "total": total,
        "step_title": step_title,
        "prompt": prompt,
        "attempts": snapshot.attempts,
        "can_skip": not complete,
        "can_restart": True,
        "hint": (
            snapshot.steps[snapshot.current_index].hint
            if not complete and snapshot.hint_visible
            else ""
        ),
        "explanation": (
            snapshot.steps[snapshot.current_index].explanation
            if not complete and snapshot.explanation_visible
            else ""
        ),
        "feedback": turn.feedback if turn is not None else "",
        "feedback_state": (
            "correct"
            if turn is not None and turn.event in {"correct", "complete"}
            else "wrong"
            if turn is not None and turn.event == "wrong"
            else "neutral"
        ),
        "review_title": turn.review_title if turn is not None else "",
        "review_explanation": (
            turn.review_explanation if turn is not None else ""
        ),
    }


def _integral_bounds(
    calculation: dict[str, Any],
) -> tuple[str, str] | None:
    lower = calculation.get("lower")
    upper = calculation.get("upper")
    if lower is not None and upper is not None:
        return str(lower).strip(), str(upper).strip()
    formula_text = str(calculation.get("formula_text") or "")
    match = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+?)\s*=", formula_text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None


def _limit_answer(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text in {"nan", "zoo"}:
        return "不存在"
    return text


def _method_aliases(method: str) -> tuple[str, ...]:
    aliases = [method]
    aliases.extend(
        part.strip()
        for part in re.split(r"[、,/和与]", method)
        if part.strip()
    )
    return tuple(dict.fromkeys(aliases))


def _method_matches(answer: str, expected: str) -> bool:
    compact_answer = re.sub(r"[\s，。；;、/（）()]", "", answer)
    compact_expected = re.sub(r"[\s，。；;、/（）()]", "", expected)
    if not compact_answer or not compact_expected:
        return False
    return (
        compact_answer == compact_expected
        or compact_expected in compact_answer
        or (
            len(compact_answer) >= 2
            and compact_answer in compact_expected
        )
    )


def _normalize_answer(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = _ANSWER_PREFIX_PATTERN.sub("", text)
    text = text.strip().strip("。；;")
    return re.sub(r"\s+", "", text).lower()


def _math_equal(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        left_expression = parse_math_expression(left)
        right_expression = parse_math_expression(right)
        if left_expression == right_expression:
            return True
        difference = simplify(left_expression - right_expression)
        if difference == 0:
            return True
        if getattr(difference, "is_number", False):
            return math.isclose(float(difference), 0.0, abs_tol=1e-10)
    except Exception:
        return False
    return False


def _math_text(value: Any) -> str:
    text = str(value)
    try:
        return f"${latex(parse_math_expression(text))}$"
    except Exception:
        return f"${text.replace('**', '^')}$"


teaching_sessions = TeachingSessionStore(
    ttl_seconds=_SESSION_TTL_SECONDS,
    max_sessions=_MAX_SESSIONS,
)
