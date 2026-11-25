#!/usr/bin/env python3
"""Run P0 acceptance checks against a live Zhiwei math demo server."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PARAMETRIC_QUESTION = (
    "求曲线 {x = sin(t), y = cos(2*t)} 在当 t = pi/4 "
    "处的切线方程和法线方程。"
)
PARAMETRIC_NO_STAR_QUESTION = (
    "求曲线 {x = sin(t), y = cos(2t)} 在当 t = pi/4 "
    "处的切线方程和法线方程。"
)
PARAMETRIC_TEACHING_ANSWERS = (
    "cos(t)",
    "-2*sin(2*t)",
    "(sqrt(2)/2, 0)",
    "-2*sqrt(2)",
    "sqrt(2)/4",
    "2√2x + y - 2 = 0",
    "4y = √2x - 1",
)
MISSING_CONDITION_QUESTIONS = (
    "求参数方程 x=sin(t), y=cos(2t) 的切线方程和法线方程",
    "求 z=x^2*y 在点 (1) 处对 x 的偏导数",
    "求函数的极值",
    "求函数的最大值",
    "求积分",
    "求微分方程的通解",
    "求极限",
)
INFINITY_QUESTIONS = (
    "求极限 x趋于正无穷时 1/x",
    "求极限 x趋于∞时 1/x",
    "求极限 x趋于无穷大时 1/x",
)
EXPLICIT_TANGENT_CASES = (
    ("求曲线 y=x^2 在 x=1 处的切线方程", "Eq(y, 2*x - 1)"),
    ("求曲线 y=x^2 在点 x=1 处的切线", "Eq(y, 2*x - 1)"),
    ("求 y=x^2 在 x=-1 处的切线方程", "Eq(y, -2*x - 1)"),
)
NATURAL_LANGUAGE_CASES = (
    (
        "当 x 从 0 到 pi 时 sin(x) 的定积分",
        "integrate",
        "integral",
        "2",
    ),
    (
        "x平方在0到1上的定积分",
        "integrate",
        "integral",
        "1/3",
    ),
    (
        "求 x平方 的导数",
        "verify",
        "derivative",
        "2*x",
    ),
    (
        "求 x立方 的导数",
        "verify",
        "derivative",
        "3*x**2",
    ),
    (
        "x平方的积分",
        "integrate",
        "integral",
        "x**3/3",
    ),
    (
        "sin(x)/x 在 x趋于0 时的极限",
        "limit",
        "limit",
        "1",
    ),
    (
        "y的导数减y等于0",
        "solve",
        "result",
        "C1*exp(x)",
    ),
    (
        "一般项 1/n^2 是否收敛",
        "solve",
        "result",
        "收敛",
    ),
    (
        "求 z=x^2*y 在点 (1,2) 处对 x 的偏导数",
        "solve",
        "result",
        "4",
    ),
)


class Acceptance:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.checks: list[dict[str, Any]] = []
        self.sections: dict[str, Any] = {}

    def check(
        self,
        name: str,
        passed: bool,
        *,
        actual: Any = None,
        expected: Any = None,
    ) -> bool:
        item = {
            "name": name,
            "passed": bool(passed),
        }
        if actual is not None:
            item["actual"] = actual
        if expected is not None:
            item["expected"] = expected
        self.checks.append(item)
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {name}")
        return bool(passed)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        session: str = "",
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if session:
            headers["X-Demo-Session"] = session
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        for attempt in range(1, 5):
            try:
                with urlopen(request, timeout=timeout) as response:
                    status = response.status
                    raw = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 and attempt < 4:
                    retry_after = exc.headers.get("Retry-After", "")
                    try:
                        wait_seconds = max(1.0, float(retry_after))
                    except (TypeError, ValueError):
                        wait_seconds = 61.0
                    print(
                        f"[WAIT] {method} {path} hit the real rate limit; "
                        f"retrying after {wait_seconds:.0f}s "
                        f"(attempt {attempt}/3)"
                    )
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(
                    f"{method} {path} returned HTTP {exc.code}: {raw[:500]}"
                ) from exc
            except URLError as exc:
                raise RuntimeError(f"{method} {path} failed: {exc}") from exc
        else:
            raise RuntimeError(f"{method} {path} exhausted request retries")
        if status != 200:
            raise RuntimeError(
                f"{method} {path} returned HTTP {status}: {raw[:500]}"
            )
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError(f"{method} {path} did not return a JSON object")
        return data

    def request_text(
        self,
        path: str,
        *,
        timeout: float = 30.0,
    ) -> tuple[int, str]:
        request = Request(
            f"{self.base_url}{path}",
            headers={"Accept": "text/html"},
            method="GET",
        )
        for attempt in range(1, 5):
            try:
                with urlopen(request, timeout=timeout) as response:
                    return response.status, response.read().decode("utf-8")
            except HTTPError as exc:
                if exc.code == 429 and attempt < 4:
                    retry_after = exc.headers.get("Retry-After", "")
                    try:
                        wait_seconds = max(1.0, float(retry_after))
                    except (TypeError, ValueError):
                        wait_seconds = 61.0
                    print(
                        f"[WAIT] GET {path} hit the real rate limit; "
                        f"retrying after {wait_seconds:.0f}s "
                        f"(attempt {attempt}/3)"
                    )
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(
                    f"GET {path} returned HTTP {exc.code}"
                ) from exc
            except URLError as exc:
                raise RuntimeError(f"GET {path} failed: {exc}") from exc
        raise RuntimeError(f"GET {path} exhausted request retries")

    def chat(
        self,
        message: str,
        *,
        session: str,
        mode: str = "qa",
        source: str = "text",
        teaching_action: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "mode": mode,
            "source": source,
        }
        if teaching_action is not None:
            payload["teaching_action"] = teaching_action
        return self.request_json(
            "POST",
            "/demo/api/chat",
            payload=payload,
            session=session,
        )

    def final_result(self, started_at: str) -> dict[str, Any]:
        failed = [item for item in self.checks if not item["passed"]]
        return {
            "started_at": started_at,
            "finished_at": _now(),
            "base_url": self.base_url,
            "overall_passed": not failed,
            "passed": len(self.checks) - len(failed),
            "failed": len(failed),
            "total": len(self.checks),
            "checks": self.checks,
            "sections": self.sections,
        }


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _solution_fields(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
        payload.get("calculation"),
        payload.get("reply"),
        payload.get("verification"),
        payload.get("knowledge_points", []),
    )


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    calculation = payload.get("calculation")
    teaching = payload.get("teaching")
    return {
        "status": payload.get("status"),
        "intent": payload.get("intent"),
        "mode": payload.get("mode"),
        "verified": payload.get("verified"),
        "verification_kind": (
            payload.get("verification", {}).get("kind")
            if isinstance(payload.get("verification"), dict)
            else None
        ),
        "has_calculation": isinstance(calculation, dict),
        "calculation_topic": (
            calculation.get("topic") if isinstance(calculation, dict) else None
        ),
        "knowledge_count": len(payload.get("knowledge_points") or []),
        "teaching_current": (
            teaching.get("current") if isinstance(teaching, dict) else None
        ),
        "teaching_total": (
            teaching.get("total") if isinstance(teaching, dict) else None
        ),
        "teaching_phase": (
            teaching.get("phase") if isinstance(teaching, dict) else None
        ),
        "teaching_feedback_state": (
            teaching.get("feedback_state")
            if isinstance(teaching, dict)
            else None
        ),
        "teaching_explanation": (
            teaching.get("explanation") if isinstance(teaching, dict) else None
        ),
        "reply_chars": len(str(payload.get("reply") or "")),
    }


def _is_verified_success(payload: dict[str, Any]) -> bool:
    verification = payload.get("verification")
    return bool(
        payload.get("status") == "ok"
        and payload.get("verified") is True
        and isinstance(verification, dict)
        and verification.get("passed") is True
        and verification.get("checks")
        and all(check.get("passed") is True for check in verification["checks"])
        and isinstance(payload.get("calculation"), dict)
    )


def _assert_blocked(
    runner: Acceptance,
    label: str,
    payload: dict[str, Any],
    *,
    teaching: bool = False,
) -> None:
    runner.check(
        f"{label}: status is not ok",
        payload.get("status") != "ok",
        actual=payload.get("status"),
        expected="needs_input/error",
    )
    runner.check(
        f"{label}: no calculation leak",
        payload.get("calculation") is None,
        actual=payload.get("calculation"),
        expected=None,
    )
    runner.check(
        f"{label}: not marked verified",
        payload.get("verified") is not True,
        actual=payload.get("verified"),
        expected="not true",
    )
    runner.check(
        f"{label}: no knowledge leak",
        not payload.get("knowledge_points"),
        actual=payload.get("knowledge_points"),
        expected="empty",
    )
    runner.check(
        f"{label}: no final answer section",
        "**最终答案**" not in str(payload.get("reply") or ""),
    )
    if teaching:
        runner.check(
            f"{label}: teaching steps blocked",
            "teaching" not in payload,
            actual=payload.get("teaching"),
            expected="absent",
        )


def verify_page_gates(runner: Acceptance) -> None:
    status, html = runner.request_text("/demo")
    required_markers = {
        "dual_mode_selector": 'id="composerMode"',
        "input_guide": 'id="inputGuide"',
        "input_guide_text": 'id="inputGuideText"',
        "input_guide_example_integral": (
            'data-input-example="当 x 从 0 到 pi 时 sin(x) 的定积分"'
        ),
        "input_guide_example_limit": (
            'data-input-example="极限 x→0 sin(x)/x"'
        ),
        "input_guide_example_partial": (
            'data-input-example="求 z=x^2*y 在点 (1,2) 处对 x 的偏导数"'
        ),
        "input_guide_example_ode": (
            'data-input-example="y的导数减y等于0"'
        ),
        "input_guide_example_series": (
            'data-input-example="一般项 1/n^2 是否收敛"'
        ),
        "input_guide_click_handler": "function fillInputExample(button)",
        "frontend_solution_gate": "function isVerifiedSolutionMessage(message)",
        "frontend_verified_required": "if (message.verified !== true)",
        "frontend_verification_required": "verification.passed !== true",
        "wrongbook_ai_copy": "确认这是一道需要收录的错题吗？",
        "wrongbook_storage": 'const WRONG_BOOK_KEY = "zhiwei-demo-wrong-book-v1"',
    }
    runner.check(
        "page: /demo returns HTTP 200",
        status == 200,
        actual=status,
        expected=200,
    )
    for name, marker in required_markers.items():
        runner.check(
            f"page: {name} marker present",
            marker in html,
            actual=f"html length={len(html)}",
            expected=marker,
        )
    runner.sections["page"] = {
        "status": status,
        "html_chars": len(html),
        "required_markers": required_markers,
    }


def verify_math_normalization(runner: Acceptance) -> dict[str, Any]:
    star = runner.chat(
        PARAMETRIC_QUESTION,
        session="p0-http-normalize-star",
    )
    no_star = runner.chat(
        PARAMETRIC_NO_STAR_QUESTION,
        session="p0-http-normalize-no-star",
    )
    for label, payload in (("star", star), ("no-star", no_star)):
        runner.check(
            f"normalize {label}: verified parametric solution",
            _is_verified_success(payload),
            actual=_summary(payload),
        )
    runner.check(
        "normalize: cos(2t) and cos(2*t) produce the same solution",
        _solution_fields(star) == _solution_fields(no_star),
        actual={
            "star": _summary(star),
            "no_star": _summary(no_star),
        },
        expected="same calculation, reply, verification and knowledge",
    )

    infinity_payloads = [
        runner.chat(
            question,
            session=f"p0-http-infinity-{index}",
        )
        for index, question in enumerate(INFINITY_QUESTIONS, start=1)
    ]
    baseline = infinity_payloads[0]
    runner.check(
        "normalize: first infinity form solves",
        _is_verified_success(baseline),
        actual=_summary(baseline),
    )
    for question, payload in zip(INFINITY_QUESTIONS[1:], infinity_payloads[1:]):
        runner.check(
            f"normalize: {question} solves",
            _is_verified_success(payload),
            actual=_summary(payload),
        )
        runner.check(
            f"normalize: {question} matches infinity baseline",
            _solution_fields(payload) == _solution_fields(baseline),
            actual={
                "expected": _summary(baseline),
                "actual": _summary(payload),
            },
        )

    runner.sections["math_normalization"] = {
        "parametric": {
            "star": _summary(star),
            "no_star": _summary(no_star),
        },
        "infinity": [
            {
                "question": question,
                "response": _summary(payload),
            }
            for question, payload in zip(INFINITY_QUESTIONS, infinity_payloads)
        ],
    }
    return star


def verify_missing_conditions(runner: Acceptance) -> None:
    qa_records = []
    for index, question in enumerate(MISSING_CONDITION_QUESTIONS, start=1):
        payload = runner.chat(
            question,
            session=f"p0-http-negative-qa-{index}",
        )
        _assert_blocked(runner, f"negative QA {index}: {question}", payload)
        qa_records.append({"question": question, "response": _summary(payload)})

    teaching_records = []
    for index, question in enumerate(MISSING_CONDITION_QUESTIONS, start=1):
        payload = runner.chat(
            question,
            session=f"p0-http-negative-teaching-{index}",
            mode="teach",
        )
        _assert_blocked(
            runner,
            f"negative teaching {index}: {question}",
            payload,
            teaching=True,
        )
        teaching_records.append(
            {"question": question, "response": _summary(payload)}
        )

    runner.sections["missing_conditions"] = {
        "qa": qa_records,
        "teaching": teaching_records,
    }


def verify_natural_language_inputs(
    runner: Acceptance,
) -> dict[str, dict[str, Any]]:
    records = []
    baselines: dict[str, dict[str, Any]] = {}
    for case_index, (
        question,
        expected_intent,
        result_key,
        expected_result,
    ) in enumerate(NATURAL_LANGUAGE_CASES, start=1):
        payloads = [
            runner.chat(
                question,
                session=f"p0-http-natural-{case_index}-{repeat}",
            )
            for repeat in range(1, 3)
        ]
        baseline = payloads[0]
        baselines[question] = baseline
        calculation = baseline.get("calculation")
        result_value = (
            calculation.get(result_key)
            if isinstance(calculation, dict)
            else None
        )
        runner.check(
            f"natural input {case_index}: intent is {expected_intent}",
            baseline.get("intent") == expected_intent,
            actual=baseline.get("intent"),
            expected=expected_intent,
        )
        runner.check(
            f"natural input {case_index}: solution is verified",
            _is_verified_success(baseline),
            actual=_summary(baseline),
        )
        runner.check(
            f"natural input {case_index}: result contains expected value",
            isinstance(result_value, str)
            and expected_result in result_value,
            actual=result_value,
            expected=expected_result,
        )
        for repeat_index, payload in enumerate(payloads[1:], start=2):
            runner.check(
                f"natural input {case_index}: repeat {repeat_index} is stable",
                _solution_fields(payload) == _solution_fields(baseline),
                actual={
                    "baseline": _summary(baseline),
                    "repeat": _summary(payload),
                },
            )
        records.append(
            {
                "question": question,
                "expected_intent": expected_intent,
                "expected_result": expected_result,
                "responses": [_summary(payload) for payload in payloads],
                "stable": all(
                    _solution_fields(payload) == _solution_fields(baseline)
                    for payload in payloads
                ),
            }
        )

    runner.sections["natural_language_inputs"] = records
    return baselines


def verify_solver_regressions(runner: Acceptance) -> None:
    tangent_records = []
    for index, (question, expected) in enumerate(
        EXPLICIT_TANGENT_CASES,
        start=1,
    ):
        payload = runner.chat(
            question,
            session=f"p0-http-explicit-tangent-{index}",
        )
        calculation = payload.get("calculation")
        topic = (
            calculation.get("topic")
            if isinstance(calculation, dict)
            else None
        )
        result = (
            calculation.get("result")
            if isinstance(calculation, dict)
            else None
        )
        reply = str(payload.get("reply") or "")
        runner.check(
            f"solver: tangent natural language {index} is verified",
            _is_verified_success(payload),
            actual=_summary(payload),
        )
        runner.check(
            f"solver: tangent natural language {index} has expected result",
            topic == "tangent" and result == expected,
            actual={"topic": topic, "result": result},
            expected={"topic": "tangent", "result": expected},
        )
        runner.check(
            f"solver: tangent natural language {index} shows derivation",
            "一阶导数" in reply and "切线斜率" in reply,
            actual=reply[:500],
        )
        tangent_records.append(
            {
                "question": question,
                "response": _summary(payload),
                "result": result,
            }
        )

    normal_payload = runner.request_json(
        "POST",
        "/demo/api/solve",
        payload={
            "chapter": "derivatives",
            "topic": "normal",
            "inputs": {
                "expression": "x^2",
                "variable": "x",
                "point": "0",
            },
        },
    )
    runner.check(
        "solver: horizontal tangent produces vertical normal",
        normal_payload.get("status") == "ok"
        and normal_payload.get("verified") is True
        and normal_payload.get("result") == "Eq(x, 0)"
        and normal_payload.get("verification", {}).get("passed") is True,
        actual={
            "status": normal_payload.get("status"),
            "verified": normal_payload.get("verified"),
            "result": normal_payload.get("result"),
            "verification": normal_payload.get("verification"),
        },
        expected="verified result Eq(x, 0)",
    )

    runner.sections["solver_regressions"] = {
        "explicit_tangent": tangent_records,
        "horizontal_tangent_vertical_normal": {
            "result": normal_payload.get("result"),
            "verified": normal_payload.get("verified"),
        },
    }


def verify_repeated_submissions(
    runner: Acceptance,
    baseline: dict[str, Any],
) -> None:
    payloads = [
        runner.chat(
            PARAMETRIC_QUESTION,
            session=f"p0-http-repeat-{index}",
        )
        for index in range(1, 6)
    ]
    first = payloads[0]
    runner.check(
        "repeat: first of five is verified",
        _is_verified_success(first),
        actual=_summary(first),
    )
    for index, payload in enumerate(payloads[1:], start=2):
        runner.check(
            f"repeat: submission {index} is verified",
            _is_verified_success(payload),
            actual=_summary(payload),
        )
        runner.check(
            f"repeat: submission {index} matches baseline",
            _solution_fields(payload) == _solution_fields(baseline),
            actual={
                "baseline": _summary(baseline),
                "actual": _summary(payload),
            },
        )
    runner.check(
        "repeat: five new sessions are stable",
        all(
            _solution_fields(payload) == _solution_fields(payloads[0])
            for payload in payloads
        ),
        actual=[_summary(payload) for payload in payloads],
    )
    runner.sections["repeatability"] = {
        "count": len(payloads),
        "responses": [_summary(payload) for payload in payloads],
        "stable": all(
            _solution_fields(payload) == _solution_fields(payloads[0])
            for payload in payloads
        ),
    }


def verify_ocr_confirmation_path(
    runner: Acceptance,
    manual: dict[str, Any],
    natural_manual: dict[str, Any],
) -> None:
    cases = (
        ("parametric", PARAMETRIC_QUESTION, manual),
        (
            "natural_integral",
            "x平方在0到1上的定积分",
            natural_manual,
        ),
    )
    records = []
    for case_index, (label, question, manual_payload) in enumerate(
        cases,
        start=1,
    ):
        session = f"p0-http-ocr-confirmation-{case_index}"
        confirmation = runner.chat(
            question,
            session=session,
            source="ocr",
        )
        runner.check(
            f"ocr confirmation path {label}: awaits confirmation",
            confirmation.get("intent") == "ocr_confirm"
            and confirmation.get("calculation") is None,
            actual=_summary(confirmation),
            expected="intent=ocr_confirm and no calculation",
        )
        confirmed = runner.chat(
            "确认",
            session=session,
            source="ocr",
        )
        runner.check(
            f"ocr confirmation path {label}: confirmed question is verified",
            _is_verified_success(confirmed),
            actual=_summary(confirmed),
        )
        runner.check(
            f"ocr confirmation path {label}: matches manual input",
            _solution_fields(manual_payload) == _solution_fields(confirmed),
            actual={
                "manual": _summary(manual_payload),
                "confirmed": _summary(confirmed),
            },
            expected="same calculation, reply, verification and knowledge",
        )
        records.append(
            {
                "label": label,
                "confirmation": _summary(confirmation),
                "confirmed": _summary(confirmed),
                "matches_manual": (
                    _solution_fields(manual_payload)
                    == _solution_fields(confirmed)
                ),
            }
        )
    runner.sections["ocr_confirmation_path"] = {
        "cases": records,
        "scope_note": (
            "This verifies the post-OCR confirmation and solve path. "
            "It does not invoke a cloud OCR model on an image."
        ),
    }


def verify_teaching_flow(
    runner: Acceptance,
    manual: dict[str, Any],
) -> None:
    session = "p0-http-teaching-full"
    started = runner.chat(
        PARAMETRIC_QUESTION,
        session=session,
        mode="teach",
        teaching_action="start",
    )
    teaching = started.get("teaching")
    runner.check(
        "teaching: starts with seven steps",
        started.get("status") == "ok"
        and started.get("intent") == "teaching_step"
        and isinstance(teaching, dict)
        and teaching.get("current") == 1
        and teaching.get("total") == 7,
        actual=_summary(started),
        expected="teaching_step 1/7",
    )
    runner.check(
        "teaching: start does not expose calculation",
        started.get("calculation") is None,
        actual=started.get("calculation"),
    )
    runner.check(
        "teaching: start does not include final solution text",
        "**最终答案**" not in str(started.get("reply") or ""),
    )

    wrong = runner.chat(
        "not-a-step-answer",
        session=session,
        mode="teach",
        teaching_action="answer",
    )
    wrong_teaching = wrong.get("teaching") or {}
    runner.check(
        "teaching: wrong answer keeps current step",
        wrong_teaching.get("current") == 1
        and wrong_teaching.get("feedback_state") == "wrong"
        and wrong_teaching.get("attempts") == 1,
        actual=_summary(wrong),
    )
    runner.check(
        "teaching: wrong answer does not reveal dx/dt",
        "cos(t)" not in json.dumps(wrong, ensure_ascii=False),
    )

    hint = runner.chat(
        "提示",
        session=session,
        mode="teach",
        teaching_action="hint",
    )
    hint_teaching = hint.get("teaching") or {}
    runner.check(
        "teaching: hint stays on current step",
        hint_teaching.get("current") == 1 and bool(hint_teaching.get("hint")),
        actual=_summary(hint),
    )
    runner.check(
        "teaching: hint does not reveal dx/dt",
        "cos(t)" not in json.dumps(hint, ensure_ascii=False),
    )

    explain = runner.chat(
        "解析",
        session=session,
        mode="teach",
        teaching_action="explain",
    )
    explain_teaching = explain.get("teaching") or {}
    explanation = str(explain_teaching.get("explanation") or "")
    runner.check(
        "teaching: explain shows only current-step explanation",
        explain_teaching.get("current") == 1
        and "cos" in explanation.lower()
        and "t" in explanation
        and "dy/dt" not in explanation
        and "sin(2*t)" not in explanation
        and "-2*sin(2*t)" not in explanation,
        actual=_summary(explain),
        expected=(
            "current-step dx/dt explanation containing cos and t; "
            "no next-step dy/dt disclosure"
        ),
    )

    skipped = runner.chat(
        "跳过",
        session=session,
        mode="teach",
        teaching_action="skip",
    )
    runner.check(
        "teaching: skip advances to step 2",
        (skipped.get("teaching") or {}).get("current") == 2,
        actual=_summary(skipped),
    )

    restarted = runner.chat(
        "重新开始",
        session=session,
        mode="teach",
        teaching_action="restart",
    )
    restarted_teaching = restarted.get("teaching") or {}
    runner.check(
        "teaching: restart returns to step 1",
        restarted_teaching.get("current") == 1
        and restarted_teaching.get("attempts") == 0,
        actual=_summary(restarted),
    )

    answers: list[dict[str, Any]] = []
    completed: dict[str, Any] = {}
    for index, answer in enumerate(PARAMETRIC_TEACHING_ANSWERS, start=1):
        completed = runner.chat(
            answer,
            session=session,
            mode="teach",
            teaching_action="answer",
        )
        answers.append(_summary(completed))
        runner.check(
            f"teaching: correct answer {index} accepted",
            (completed.get("teaching") or {}).get("feedback_state") == "correct",
            actual=_summary(completed),
        )
        if index < len(PARAMETRIC_TEACHING_ANSWERS):
            runner.check(
                f"teaching: answer {index} does not expose calculation",
                completed.get("calculation") is None,
                actual=completed.get("calculation"),
            )

    completed_teaching = completed.get("teaching") or {}
    runner.check(
        "teaching: all steps complete",
        completed.get("intent") == "solve"
        and completed_teaching.get("phase") == "complete"
        and completed_teaching.get("active") is False,
        actual=_summary(completed),
        expected="solve with teaching phase complete",
    )
    runner.check(
        "teaching: completed solution is verified",
        _is_verified_success(completed),
        actual=_summary(completed),
    )
    runner.check(
        "teaching: completed calculation matches QA",
        completed.get("calculation") == manual.get("calculation"),
        actual={
            "teaching_topic": (
                completed.get("calculation") or {}
            ).get("topic"),
            "qa_topic": (manual.get("calculation") or {}).get("topic"),
        },
    )
    runner.check(
        "teaching: completed knowledge matches QA",
        completed.get("knowledge_points") == manual.get("knowledge_points"),
        actual={
            "teaching": completed.get("knowledge_points"),
            "qa": manual.get("knowledge_points"),
        },
    )

    switched_qa = runner.chat(
        PARAMETRIC_QUESTION,
        session=session,
        mode="qa",
    )
    runner.check(
        "teaching: switching back to QA answers directly",
        _is_verified_success(switched_qa)
        and switched_qa.get("mode") == "qa"
        and switched_qa.get("calculation") == manual.get("calculation"),
        actual=_summary(switched_qa),
    )

    runner.sections["teaching"] = {
        "started": _summary(started),
        "wrong": _summary(wrong),
        "hint": _summary(hint),
        "explain": _summary(explain),
        "skipped": _summary(skipped),
        "restarted": _summary(restarted),
        "answers": answers,
        "completed": _summary(completed),
        "switched_qa": _summary(switched_qa),
    }


def render_markdown(result: dict[str, Any]) -> str:
    status = "通过" if result["overall_passed"] else "未通过"
    lines = [
        "# 知微高数 P0 真实 HTTP 验收记录",
        "",
        f"- 开始时间：`{result['started_at']}`",
        f"- 结束时间：`{result['finished_at']}`",
        f"- 服务地址：`{result['base_url']}`",
        f"- 总体结果：**{status}**",
        f"- 断言统计：`{result['passed']}/{result['total']}` 通过，"
        f"`{result['failed']}` 失败",
        "",
        "## 断言明细",
        "",
        "| 编号 | 结果 | 断言 |",
        "| --- | --- | --- |",
    ]
    for index, item in enumerate(result["checks"], start=1):
        marker = "PASS" if item["passed"] else "FAIL"
        name = str(item["name"]).replace("|", "\\|")
        lines.append(f"| {index} | {marker} | {name} |")

    ocr_note = result.get("sections", {}).get("ocr_confirmation_path", {}).get(
        "scope_note",
        "",
    )
    if ocr_note:
        lines.extend(
            [
                "",
                "## 测试范围说明",
                "",
                f"- {ocr_note}",
                "- 真实云端图片 OCR 与公网部署不在本次本地 HTTP 验收范围内。",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real HTTP P0 acceptance checks against the local demo.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8012",
        help="Demo server base URL.",
    )
    parser.add_argument(
        "--json-output",
        default="work/p0-http-acceptance.json",
        help="Path for the complete JSON record.",
    )
    parser.add_argument(
        "--markdown-output",
        default="work/p0-http-acceptance.md",
        help="Path for the Markdown summary.",
    )
    args = parser.parse_args()

    started_at = _now()
    runner = Acceptance(args.base_url)
    try:
        verify_page_gates(runner)
        manual = verify_math_normalization(runner)
        natural_payloads = verify_natural_language_inputs(runner)
        verify_missing_conditions(runner)
        verify_solver_regressions(runner)
        verify_repeated_submissions(runner, manual)
        verify_ocr_confirmation_path(
            runner,
            manual,
            natural_payloads["x平方在0到1上的定积分"],
        )
        verify_teaching_flow(runner, manual)
    except Exception as exc:
        runner.check(
            "unexpected request or assertion failure",
            False,
            actual=f"{type(exc).__name__}: {exc}",
        )

    result = runner.final_result(started_at)
    json_path = Path(args.json_output)
    markdown_path = Path(args.markdown_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(result), encoding="utf-8")

    print(
        f"\nP0 HTTP acceptance: {result['passed']}/{result['total']} passed, "
        f"{result['failed']} failed"
    )
    print(f"JSON: {json_path.resolve()}")
    print(f"Markdown: {markdown_path.resolve()}")
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
